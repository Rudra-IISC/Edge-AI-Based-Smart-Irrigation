# main.py -- Run on Raspberry Pi Pico W under MicroPython

import time
import gc
import math
import urequests
import os
import network # Added for WiFi
import ssl     # Added for secure MQTT
from machine import Pin
from umqtt.simple import MQTTClient

# -----------------------------------------------------------------------------
# 1) IMPORT YOUR MLP MODEL (INSTEAD OF RANDOM FOREST)
# -----------------------------------------------------------------------------
MLP_MODEL_FILENAME = 'mlp_model.py' # <<< Make sure your MLP file is named this
try:
    # Try importing the specific file containing your MLP functions/params
    import mlp_model
    print(f"✅ {MLP_MODEL_FILENAME} imported successfully.")
    # Check if the expected prediction function exists
    if hasattr(mlp_model, 'predict_et0'):
        print("   Found 'predict_et0' function.")
        # We will call mlp_model.predict_et0 directly later
    else:
        print(f"⚠️ WARNING: 'predict_et0' function not found in {MLP_MODEL_FILENAME}!")
        raise ImportError # Force fallback to dummy if function missing
except ImportError:
    print(f"⚠️ {MLP_MODEL_FILENAME} not found or missing 'predict_et0'! Using dummy model.")
    class DummyModel:
        # Define the same function name expected by the main code
        def predict_et0(self, feats):
            print("   DEBUG: Using DummyModel predict_et0") # Add debug print
            return 0.0
    # Create an instance of the dummy model using the same variable name
    # This way, the rest of the code doesn't need to know if it's the real or dummy model
    mlp_model = DummyModel()
except Exception as e:
     print(f"⚠️ An error occurred importing {MLP_MODEL_FILENAME}: {e}. Using dummy model.")
     class DummyModel:
         def predict_et0(self, feats):
             print("   DEBUG: Using DummyModel predict_et0 (due to import error)")
             return 0.0
     mlp_model = DummyModel()

# -----------------------------------------------------------------------------
# 2) NURSERY PROFILES & INTERPOLATION
# -----------------------------------------------------------------------------
crop_kc_profile = {
    'onion': [(0,0.7),(15,0.7),(21,0.8),(24,0.9),(29,0.94),(33,1.0),(82,1.1),(106,0.8)],
    'maize': [(0,0.3),(20,0.3),(40,0.7),(60,1.0),(80,0.8),(100,0.6)]
}
crop_root_profile = {
    'onion': [(0,0.05),(18,0.25),(38,0.43),(73,0.60),(106,0.60)],
    'maize': [(0,0.30),(20,0.50),(40,0.80),(60,1.20),(80,1.50)]
}

def linear_interpolate(day, profile):
    if day <= profile[0][0]: return profile[0][1]
    if day >= profile[-1][0]: return profile[-1][1]
    for (d0,v0),(d1,v1) in zip(profile, profile[1:]):
        if d0 <= day <= d1:
            return v0 + (v1-v0)*(day-d0)/(d1-d0)
    return profile[-1][1]

def get_days_after_planting(Y, M, D):
    try:
        sow = time.mktime((Y,M,D,0,0,0,0,0))
        # Get current time using localtime() for correct offset handling on Pico W RTC
        now_tuple = time.localtime()
        now = time.mktime(now_tuple)
        # Ensure non-negative days
        days = max(0, int((now - sow)//86400))
        return days
    except OverflowError:
        print("⚠️ Error calculating days: Date might be out of range.")
        return 0 # Return 0 days if date is invalid
    except Exception as e:
        print(f"⚠️ Error in get_days_after_planting: {e}")
        return 0

# -----------------------------------------------------------------------------
# 3) TEMPORARY & DAILY LOGGING (Optional: Temp file not strictly needed now)
# -----------------------------------------------------------------------------
LOG_FILE  = 'daily_log.csv' # Keep if you want daily summaries

def get_today_str():
    t = time.localtime()
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"

# -----------------------------------------------------------------------------
# 4) MQTT CONFIGURATION (SOIL VWC & PUMP COMMAND)
# -----------------------------------------------------------------------------
MQTT_BROKER     = b"b1ef2a417ef147adad7b7222eacb6052.s1.eu.hivemq.cloud"
MQTT_PORT       = 8883
MQTT_USER       = b"Rudra_123"
MQTT_PASSWORD   = b"RudrA@123"
MQTT_CLIENT_ID  = b"pico_w_eto_predictor_v5" # Incremented version again
TOPIC_SOIL_SUB  = b"esp32/soilMoisture"
TOPIC_PUMP_CMD  = b"esp32/pump/control"

soil_buffer     = []
sampling_active = False

# MQTT callback for incoming messages
def sub_cb(topic, msg):
    global soil_buffer
    topic_str = topic.decode('utf-8')
    msg_str = msg.decode('utf-8')
    # print(f"DEBUG MQTT Recv | Topic: {topic_str}, Msg: {msg_str}, Sampling: {sampling_active}") # Uncomment for verbose debug

    if topic == TOPIC_SOIL_SUB and sampling_active:
        try:
            vwc = float(msg_str)
            # Add validation? e.g., if 0 < vwc < 100:
            if 0.0 <= vwc <= 100.0:
                soil_buffer.append(vwc)
            else:
                print(f"Warning: Received out-of-range soil VWC: {vwc}")
        except ValueError:
            print(f"Error: Received non-numeric soil data on {topic_str}: {msg_str}")
        except Exception as e:
            print(f"Error processing message: {e}")

# Initialize and connect MQTT client
def connect_mqtt():
    print("Attempting to connect to MQTT broker...")
    client = None # Initialize client to None
    try:
        broker_str = MQTT_BROKER.decode('utf-8')
        client = MQTTClient(
            client_id=MQTT_CLIENT_ID, server=MQTT_BROKER, port=MQTT_PORT,
            user=MQTT_USER, password=MQTT_PASSWORD, keepalive=7200, ssl=True,
            ssl_params={'server_hostname': broker_str} # Pass broker string here
        )
        client.connect()
        print(f"✅ MQTT Connected to {broker_str}!")
        client.set_callback(sub_cb)
        client.subscribe(TOPIC_SOIL_SUB)
        print(f"✅ Subscribed to {TOPIC_SOIL_SUB.decode()}")
        return client
    except OSError as e:
        # Specific handling for network/socket errors during connection
        print(f"❌ MQTT OSError during connection: {e}")
        if client: # Try to clean up if object was created
            try: client.disconnect()
            except: pass
        return None
    except Exception as e:
        print(f"❌ Failed to connect to MQTT Broker: {e}")
        if client: # Try to clean up if object was created
            try: client.disconnect()
            except: pass
        return None

# Helper function to safely publish MQTT messages
def publish_message(client, topic, message):
    if not client:
        print(f"❌ Cannot publish to {topic.decode()}: MQTT client not connected.")
        return False
    try:
        client.publish(topic, message)
        print(f"⬆ Published '{message}' to {topic.decode()}")
        return True
    except OSError as e:
        print(f"⚠ MQTT connection error during publish to {topic.decode()}: {e}.")
        return False # Indicate publish failed, let main loop handle reconnect
    except Exception as e:
        print(f"⚠ Failed to publish to {topic.decode()}: {e}")
        return False

# -----------------------------------------------------------------------------
# 5) WIFI & WEATHER API CONFIG
# -----------------------------------------------------------------------------
WIFI_SSID   = 'Ss'      # replace if needed
WIFI_PASS   = 'surya0123' # replace if needed
OWM_API_KEY = 'e3c83dbd059965f25b4d7ddb8b31622d' # Replace with your key
LAT, LON    = 13.0192526, 77.5630184           # Replace with your location
OWM_URL     = (
    # Consider potential issues with http vs https if connectivity problems arise
    f"http://api.openweathermap.org/data/2.5/weather"
    f"?lat={LAT}&lon={LON}&appid={OWM_API_KEY}&units=metric"
)

# WiFi Connection function
def connect_wifi(ssid, pwd):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f'Connecting to WiFi ({ssid})...')
        wlan.connect(ssid, pwd)
        max_wait = 20 # Increased wait time slightly
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3: break
            max_wait -= 1
            print('.', end='')
            time.sleep(1)
        print()

    if wlan.isconnected():
        print('✅ WiFi connected!')
        print('   Network config:', wlan.ifconfig())
        # Set RTC from NTP after WiFi connection
        try:
            import ntptime
            #ntptime.host = "pool.ntp.org" # Default should be fine
            print("   Synchronizing RTC with NTP...")
            ntptime.settime()
            print(f"   RTC synchronized. Current time: {time.localtime()}")
        except ImportError:
            print("   Warning: 'ntptime' module not found. Cannot sync RTC.")
        except Exception as e:
            print(f"   Error synchronizing RTC: {e}")
        return wlan
    else:
        print('❌ WiFi connection failed! Status:', wlan.status())
        return None

# -----------------------------------------------------------------------------
# 6) UTILITY FUNCTIONS (Daylight, Weather, Soil)
# -----------------------------------------------------------------------------
def potential_daylight_hours(lat_deg, doy):
    phi  = math.radians(lat_deg)
    doy = max(1, min(doy, 366)) # Ensure DOY is valid
    # Formula for declination angle (delta)
    decl = math.radians(-23.45) * math.cos(2 * math.pi * (doy + 10) / 365)
    # Hour angle (omega_s)
    cos_omega_s = -math.tan(phi) * math.tan(decl)
    # Clamp cos value to avoid domain errors due to floating point inaccuracies
    cos_omega_s = max(-1.0, min(1.0, cos_omega_s))
    omega_s = math.acos(cos_omega_s)
    # Daylight hours (N)
    N = (24 / math.pi) * omega_s
    # Handle polar day/night cases
    if cos_omega_s >= 1.0:  # Sun always below horizon
        return 0.0
    elif cos_omega_s <= -1.0: # Sun always above horizon
        return 24.0
    else:
        return N

WH_TO_MJ = 0.0036

# --- Enhanced fetch_weather with more debugging ---
def fetch_weather():
    print("Fetching weather data...")
    print(f"  URL: {OWM_URL}") # Print the URL being used
    response = None
    weather_data = {} # Use a dict to store extracted data

    # Check WiFi status before attempting request
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("❌ Cannot fetch weather: WiFi is not connected.")
        return None

    try:
        response = urequests.get(OWM_URL, timeout=25) # Increased timeout
        status_code = response.status_code
        print(f"  HTTP Status Code: {status_code}")

        # Try to get raw text first for debugging non-JSON responses
        raw_text = response.text
        # print(f"  Raw Response Text: {raw_text}") # Uncomment for very verbose debugging

        if status_code != 200:
            print(f"❌ Weather API Error: Status Code {status_code}")
            print(f"   Response Body: {raw_text}") # Print raw text on error
            return None

        # If status is OK, try parsing JSON
        resp_json = response.json()
        # print(f"  Parsed JSON: {resp_json}") # Uncomment for verbose debugging
        d = resp_json
        print("✅ Weather data received and parsed.")

    except OSError as e:
        # Handle network-related errors during the request
        print(f"❌ Network Error during weather fetch: {e}")
        return None
    except Exception as e:
        print(f"❌ Failed to fetch or parse weather data: {e}")
        # Print raw text if available even on exception
        if response and hasattr(response, 'text'):
             print(f"   Response text (on error): {response.text}")
        return None
    finally:
        if response:
            response.close() # Ensure connection is closed

    # Safely extract data with defaults, store in the dict
    main_data = d.get('main', {})
    wind_data = d.get('wind', {})
    clouds_data = d.get('clouds', {})

    weather_data['temp'] = main_data.get('temp', 25.0)
    weather_data['tmax'] = main_data.get('temp_max', weather_data['temp']) # Use temp if max missing
    weather_data['tmin'] = main_data.get('temp_min', weather_data['temp']) # Use temp if min missing
    weather_data['rh'] = main_data.get('humidity', 60)
    weather_data['clouds'] = clouds_data.get('all', 50) # Cloudiness %
    weather_data['wind_spd'] = wind_data.get('speed', 2.0) # Wind speed m/s
    weather_data['pressure'] = main_data.get('pressure', 1013) # Pressure hPa
    weather_data['timestamp'] = d.get('dt', int(time.time()))

    # Calculate derived values
    try:
        # Use gmtime for DOY calculation as it's timezone independent
        time_tuple = time.gmtime(weather_data['timestamp'])
        weather_data['doy'] = time_tuple[7] # Day of the year (1-366)
    except Exception as e:
        print(f"Warning: Could not get DOY from timestamp {weather_data['timestamp']}: {e}. Using default DOY=180")
        weather_data['doy'] = 180

    weather_data['N'] = potential_daylight_hours(LAT, weather_data['doy']) # Potential daylight hours

    # Estimate Solar Radiation (Rs) using a simplified approach if not directly available
    # This is a very rough estimate, replace if better data (e.g., from 'solar_rad' field if API provides) is available
    # Angstrom-Prescott type estimation (needs calibration with Ra - extraterrestrial radiation)
    # For simplicity, using the cloud cover approach used before, but acknowledge its limitations.
    F = min(1, max(0, weather_data['clouds'] / 100)) # Cloud fraction
    # Simplified approach: Assume max possible clear sky radiation (P) is reduced by clouds
    # P value (e.g., 990 Wh/m2/day avg) is highly location/season dependent. Use with caution.
    # A better approach would use Ra calculation based on lat/doy.
    P = 990 # Very rough average max clear sky radiation Wh/m2/day
    E_wh_m2 = P * (1 - 0.75 * (F**3)) * weather_data['N'] / 12 # Scale by daylight fraction (approx)
    weather_data['E_mj_m2_day'] = round(E_wh_m2 * WH_TO_MJ, 2)

    # Extract the specific features needed for the MLP model
    tmax_out = weather_data['tmax']
    rh_out = weather_data['rh']
    energy_out = weather_data['E_mj_m2_day']

    print(f"   Weather Parsed: Tmax={tmax_out}, RH={rh_out}, Clouds={weather_data['clouds']}, DOY={weather_data['doy']}, N={weather_data['N']:.2f}h, Est. E={energy_out} MJ/m^2/day")
    # Return only the features required by the ET0 model in the correct order
    return tmax_out, rh_out, energy_out # Return the tuple [Tmax, RH, Energy]

# Soil available water (mm)
def soil_available_water_depth(vwc_pct, rz_depth_mm, fc_pct=42.0, pwp_pct=15.0):
    if vwc_pct is None:
        # print("Warning: VWC is None, cannot calculate available water.") # Reduce verbosity
        return 0.0
    # Ensure inputs are floats
    vwc_pct = float(vwc_pct)
    rz_depth_mm = float(rz_depth_mm)
    fc_pct = float(fc_pct)
    pwp_pct = float(pwp_pct)

    if rz_depth_mm <= 0: return 0.0

    θ    = vwc_pct / 100.0 # Current VWC fraction
    fc   = fc_pct / 100.0  # Field Capacity fraction
    pwp  = pwp_pct / 100.0 # Permanent Wilting Point fraction

    if fc <= pwp:
        print(f"Warning: Field Capacity ({fc_pct}%) <= PWP ({pwp_pct}%). Check soil params.")
        return 0.0 # Cannot hold water

    # Total Available Water capacity (TAW) in the root zone depth
    taw_fraction = fc - pwp
    taw_mm = taw_fraction * rz_depth_mm

    # Current water content above PWP
    current_water_above_pwp_fraction = max(0.0, θ - pwp)
    current_water_above_pwp_mm = current_water_above_pwp_fraction * rz_depth_mm

    # Available water is the current water above PWP, but capped by TAW
    available_mm = min(current_water_above_pwp_mm, taw_mm)

    return round(available_mm, 2)

# Pump time & ETc
def irrigation_time(Kc, ET0, area_m2, flow_lph=9.0):
    # ET0 should be the reference evapotranspiration for the day (mm)
    # Kc is the crop coefficient for the day
    # avail_mm is current available water, not directly used here but calculated before calling
    # area_m2 is the total nursery area
    # flow_lph is the pump flow rate in Liters Per Hour

    if ET0 < 0: ET0 = 0.0 # Ensure ET0 isn't negative
    if Kc < 0: Kc = 0.0   # Ensure Kc isn't negative

    ETc = ET0 * Kc # Crop Evapotranspiration (mm/day) - Water need for the day

    # Convert water need from mm depth to Liters for the given area
    # req_mm is the depth of water needed today
    req_mm = max(0.0, ETc)
    # Volume = Depth (m) * Area (m^2)
    # Depth (m) = req_mm / 1000.0
    # Volume (m^3) = (req_mm / 1000.0) * area_m2
    # Volume (Liters) = Volume (m^3) * 1000.0
    req_liters = req_mm * area_m2

    if flow_lph <= 0:
        print("Error: Pump flow rate must be positive.")
        return 0.0, ETc # Return 0 time, but still return calculated ETc

    # Time (hours) = Total Liters / Liters Per Hour
    # Time (seconds) = Time (hours) * 3600
    time_seconds = (req_liters / flow_lph) * 3600.0 if req_liters > 0 else 0.0

    return time_seconds, ETc

# -----------------------------------------------------------------------------
# 7) INTERACTIVE NURSERY SETUP
# -----------------------------------------------------------------------------
print("\n▶ Nursery setup:")
# Crop Selection
while True:
    crop = input("  Crop (onion/maize): ").strip().lower()
    if crop in crop_kc_profile: break
    print("⚠ Unsupported crop. Please choose 'onion' or 'maize'.")
# Planting Date
while True:
    date_str = input("  Planting date (YYYY MM DD): ").strip()
    parts = date_str.split()
    if len(parts) == 3:
        try:
            Y, Mo, Da = map(int, parts)
            # Basic validation for month and day
            if not (1 <= Mo <= 12 and 1 <= Da <= 31):
                 print("⚠ Invalid month or day number.")
                 continue
            # Attempt to create a time tuple to check validity further (catches invalid dates like Feb 30)
            # Use a fixed time to avoid potential DST issues if relevant
            time.mktime((Y, Mo, Da, 0, 0, 0, 0, 0))
            print(f"   Planting date set to: {Y:04d}-{Mo:02d}-{Da:02d}")
            break # Date seems valid
        except ValueError:
            print("⚠ Enter numeric values for YYYY MM DD.")
        except OverflowError:
            print("⚠ Date is out of range for this system.")
        except Exception as e:
            print(f"⚠ Invalid date: {e}")
    else:
        print("⚠ Invalid format. Use YYYY MM DD (e.g., 2024 04 15)")
# Nursery Dimensions and Pump
while True:
    try:
        n_plants = int(input("  Number of plants: "))
        if n_plants <= 0: print("⚠ Number of plants must be positive."); continue

        ps_cm = float(input("  Plant spacing (cm): "))
        if ps_cm <= 0: print("⚠ Plant spacing must be positive."); continue

        rs_cm = float(input("  Row spacing (cm): "))
        if rs_cm <= 0: print("⚠ Row spacing must be positive."); continue

        pump_flow_lph = float(input("  Pump flow rate (Liters/Hour): "))
        if pump_flow_lph <= 0: print("⚠ Pump flow rate must be positive."); continue

        break # All inputs are valid numbers > 0
    except ValueError:
        print("⚠ Please enter valid numeric values.")
    except Exception as e:
        print(f"⚠ Invalid input: {e}")

# Calculate derived parameters after setup
plant_spacing_m = ps_cm / 100.0
row_spacing_m = rs_cm / 100.0
area_per_plant = plant_spacing_m * row_spacing_m # Area allocated per plant in m^2
total_area_m2  = area_per_plant * n_plants     # Total nursery area in m^2

# Initialize dynamic parameters (will be updated daily)
days = get_days_after_planting(Y, Mo, Da)
Kc_today = linear_interpolate(days, crop_kc_profile[crop])
rz_m = linear_interpolate(days, crop_root_profile[crop])
rz_mm = rz_m * 1000.0

print(f"\n→ Initial Days after planting: {days}")
print(f"→ Initial Kc = {Kc_today:.3f}, Initial Root-zone Depth = {rz_mm:.1f} mm")
print(f"→ Total Area = {total_area_m2:.3f} m²")
print(f"→ Pump Flow Rate = {pump_flow_lph} L/h\n")


# -----------------------------------------------------------------------------
# 8) CONNECT & INITIALIZE
# -----------------------------------------------------------------------------
print("Initializing connections...")
wlan = connect_wifi(WIFI_SSID, WIFI_PASS)
if not wlan or not wlan.isconnected():
    # Consider maybe trying to reconnect or enter a limited mode?
    # For now, halt execution.
    print("❌ Halting execution due to WiFi connection failure.")
    # Optional: blink LED or other indication of permanent failure
    raise SystemExit("WiFi connection failed")

client = connect_mqtt()
if not client:
    # Consider fallback or retry logic here too?
    print("❌ Halting execution due to MQTT connection failure.")
    raise SystemExit("MQTT connection failed")

gc.enable()
print(f"Garbage Collection Enabled. Initial free memory: {gc.mem_free()} bytes")
last_date_processed = "" # Force initial run of daily logic

# --- Initialize State Variables (using None where value not yet known) ---
mean_vwc = None    # Average Volumetric Water Content from daily sample (%)
avail_mm = 0.0     # Calculated available water in root zone (mm)
etc_val = 0.0      # Calculated daily Crop Evapotranspiration (mm)
pump_time_s = 0.0  # Calculated required pump duration for the day (seconds)

# --- Weather State Variables ---
# Store the last successfully retrieved weather components
last_tmax = None     # Last valid Tmax (°C)
last_rh = None       # Last valid RH (%)
last_energy = None   # Last valid Energy (MJ/m2/day)
last_et0 = 0.0       # Last calculated ET0 (mm/day), defaults to 0

# --- Pump State Variables ---
pump_running = False           # Is the pump currently supposed to be ON?
pump_start_time = 0            # Timestamp when the pump was turned ON (time.time())
current_pump_run_duration = 0.0 # Target duration for the current pump run (seconds)

# --- Helper for formatting status output ---
def format_value(val, precision=1, unit=""):
     if val is None: return "N/A"
     try:
         return f"{val:.{precision}f}{unit}"
     except (TypeError, ValueError): # Handle potential non-numeric values
         return "Error"

# -----------------------------------------------------------------------------
# 9) MAIN LOOP
# -----------------------------------------------------------------------------
print(f"\n{'='*15} Starting Main Loop {'='*15}")
loop_count = 0
while True:
    loop_count += 1
    current_time_check = time.time()
    now_local = time.localtime(current_time_check)
    print(f"\n--- Loop {loop_count} | Time: {now_local[0]}-{now_local[1]:02d}-{now_local[2]:02d} {now_local[3]:02d}:{now_local[4]:02d}:{now_local[5]:02d} ---")

    # --- Check WiFi Status & Reconnect ---
    if not wlan or not wlan.isconnected():
        print("⚠ WiFi connection lost! Attempting to reconnect...")
        wlan = connect_wifi(WIFI_SSID, WIFI_PASS)
        if not wlan or not wlan.isconnected():
            print("❌ WiFi reconnect failed. Waiting before next attempt...")
            time.sleep(60)
            continue # Skip the rest of this loop iteration

    # --- MQTT Message Check & Reconnect Logic ---
    mqtt_connection_ok = False
    if client:
        try:
            # Check for incoming messages (like soil moisture)
            client.check_msg()
            # Also send a PING periodically if keepalive isn't sufficient?
            # Simple check: if client is not None, assume connection is okay unless check_msg fails
            mqtt_connection_ok = True
        except OSError as e:
            print(f"⚠ MQTT connection error during check_msg: {e}. Attempting reconnect...")
            mqtt_connection_ok = False
            if client:
                try: client.disconnect()
                except: pass
            client = None # Mark client as disconnected
        except Exception as e:
            print(f"⚠ Unexpected error during check_msg: {e}")
            # Decide how to handle - maybe wait and retry?
            time.sleep(5) # Wait a bit after unexpected error
            # Keep mqtt_connection_ok as True if it was before? Or set False?
            # Setting False to be safe and force reconnect attempt
            mqtt_connection_ok = False
            if client:
                 try: client.disconnect()
                 except: pass
            client = None
    else:
        # Client was already None, definitely not connected
        mqtt_connection_ok = False

    # Attempt MQTT reconnect if needed
    if not mqtt_connection_ok:
        print("Attempting MQTT reconnect...")
        time.sleep(5) # Wait before retrying connection
        client = connect_mqtt()
        if not client:
            print("❌ MQTT reconnect failed. Will retry next loop.")
            # Optional: Add a longer sleep here if reconnects fail repeatedly
            time.sleep(30)
            gc.collect()
            # Continue to next loop iteration to avoid running logic without MQTT
            # But maybe allow pump OFF check to run? Needs careful thought.
            # For now, skipping the rest of the loop seems safer.
            continue
        else:
            print("✅ MQTT reconnected successfully.")

    # --- Daily Rollover Logic ---
    today_str = get_today_str()
    if today_str != last_date_processed:
        print(f"\n{'='*10} New Day Detected: {today_str} {'='*10}")

        # --- Actions to perform ONCE per day ---

        # 1. --- Soil Moisture Sampling (e.g., 5 minutes) ---
        print("   Starting daily soil moisture sampling...")
        sampling_active = True # Enable MQTT callback to store readings
        soil_buffer.clear()    # Clear buffer from previous day/samples
        start_sample_time = time.time()
        sample_duration_seconds = 300 # 5 minutes

        # Keep checking messages during the sampling period
        while time.time() - start_sample_time < sample_duration_seconds:
            if client:
                try:
                    client.check_msg()
                    time.sleep(0.1) # Brief pause to prevent busy-waiting
                except OSError as e:
                    print(f"   ⚠ MQTT connection error during sampling: {e}. Aborting sampling.")
                    mqtt_connection_ok = False # Mark connection as bad
                    if client: try: client.disconnect(); except: pass
                    client = None
                    break # Exit sampling loop, main loop will handle reconnect
                except Exception as e:
                    print(f"   ⚠ Unexpected error during sampling check_msg: {e}")
                    time.sleep(0.5) # Pause after error
            else:
                # Client became None (disconnected) during sampling
                print("   ❌ MQTT client lost during sampling. Aborting sampling.")
                break # Exit sampling loop

        sampling_active = False # Disable MQTT callback storage after duration
        print(f"   ⌛ Sampling complete. Received {len(soil_buffer)} readings.")

        # If MQTT disconnected during sampling, attempt reconnect immediately *before* calculations
        if not client:
            print("   Attempting MQTT reconnect after sampling failure...")
            time.sleep(5)
            client = connect_mqtt()
            if not client:
                print("   ❌ MQTT reconnect failed after sampling. Daily calculations might be affected.")
                # Decide whether to proceed with potentially stale VWC data or skip

        # 2. --- Calculate Mean VWC ---
        if soil_buffer:
            current_mean_vwc = sum(soil_buffer) / len(soil_buffer)
            mean_vwc = current_mean_vwc # Update the state variable
            print(f"   ✅ Mean VWC for {today_str}: {mean_vwc:.1f}%")
        else:
            print(f"   ⚠ No soil moisture data received during sampling for {today_str}.")
            if mean_vwc is not None:
                print(f"     Reusing previous day's VWC: {mean_vwc:.1f}% for calculations.")
            else:
                # No previous data either, critical issue? Use a default?
                mean_vwc = 25.0 # Example default VWC - SET APPROPRIATELY FOR YOUR SOIL
                print(f"     Using default VWC: {mean_vwc:.1f}% for calculations.")

        # 3. --- Recalculate daily crop parameters ---
        print("   Recalculating daily crop parameters...")
        days = get_days_after_planting(Y, Mo, Da) # Update days count based on current time
        Kc_today = linear_interpolate(days, crop_kc_profile[crop])
        rz_m = linear_interpolate(days, crop_root_profile[crop])
        rz_mm = rz_m * 1000.0
        print(f"   Day {days}: Kc = {Kc_today:.3f}, RZ = {rz_mm:.1f} mm")

        # 4. --- Fetch Weather & Update State (Once per day) ---
        print("   Attempting to fetch daily weather data...")
        weather_data_tuple = fetch_weather() # Fetch new data

        if weather_data_tuple:
            # Weather fetch succeeded, update state
            last_tmax, last_rh, last_energy = weather_data_tuple
            print(f"   Weather fetch successful: Tmax={last_tmax}, RH={last_rh}, E={last_energy}")
            try:
                # --- PREDICT ET0 using the imported model ---
                features = [last_tmax, last_rh, last_energy]
                print(f"     DEBUG: Calling predict_et0 with features: {features}")

                # Call the prediction function from the imported mlp_model (or DummyModel)
                raw_et0 = mlp_model.predict_et0(features)
                print(f"     DEBUG: Raw predicted ET0 from model: {raw_et0:.4f}")

                # Ensure ET0 is not negative (physical constraint)
                last_et0 = max(0.0, raw_et0)
                print(f"   ✅ Calculated ET0 = {last_et0:.2f} mm/day (Raw={raw_et0:.2f})")

            except Exception as e:
                print(f"   ❌ Error predicting ET0 from new weather data: {e}")
                print(f"     Keeping previous ET0 value: {last_et0:.2f} mm/day")
        else:
            # Fetch failed, keep using previous values stored in last_tmax etc.
            print("   ⚠ Weather fetch failed for today.")
            if last_tmax is None or last_rh is None or last_energy is None:
                # Critical: No valid weather data *ever* fetched or model failed previously
                 print("     WARNING: No valid weather data available. Using ET0 = 0.0 for safety.")
                 last_et0 = 0.0 # Force ET0 to 0 if weather is unknown
            else:
                 print(f"     Using previous day's weather data to calculate ET0.")
                 try:
                     # Retry prediction with OLD data
                     features = [last_tmax, last_rh, last_energy]
                     print(f"     DEBUG: Retrying predict_et0 with OLD features: {features}")
                     raw_et0 = mlp_model.predict_et0(features)
                     print(f"     DEBUG: Raw predicted ET0 from OLD model: {raw_et0:.4f}")
                     last_et0 = max(0.0, raw_et0)
                     print(f"   ✅ Calculated ET0 = {last_et0:.2f} mm/day (using old weather)")
                 except Exception as e:
                     print(f"   ❌ Error predicting ET0 even from old weather data: {e}")
                     print(f"     Using previous ET0 value: {last_et0:.2f} mm/day")

        # 5. --- Calculate Available Water & Required Pump Time ---
        print("   Calculating available water and irrigation needs...")
        if mean_vwc is None:
            print("   ⚠ Cannot calculate irrigation: Mean VWC is unknown.")
            avail_mm = 0.0
            pump_time_s = 0.0
            etc_val = 0.0
        else:
            avail_mm = soil_available_water_depth(mean_vwc, rz_mm)
            # Use the ET0 calculated (either from new weather, old weather, or default 0)
            pump_time_s, etc_val = irrigation_time(Kc_today, last_et0, total_area_m2, flow_lph=pump_flow_lph)
            print(f"   Calculated: Avail Water={avail_mm:.1f} mm")
            print(f"   Calculated: ETc={etc_val:.2f} mm (using ET0={last_et0:.2f})")
            print(f"   Required Pump Time for today: {pump_time_s:.1f} seconds")

        # 6. --- Decide and Send PUMP Command (Once per day) ---
        # Basic logic: Irrigate if ETc > 0 (water needed). More complex logic could consider avail_mm threshold.
        if pump_time_s > 1.0: # Use a small threshold to avoid tiny runs
            if not pump_running:
                print(f"   Irrigation required ({pump_time_s:.1f}s). Turning pump ON.")
                publish_success = publish_message(client, TOPIC_PUMP_CMD, "PUMP_ON")
                if publish_success:
                    pump_running = True
                    pump_start_time = time.time()
                    current_pump_run_duration = pump_time_s # Store the target duration
                else:
                    print("   Failed to send PUMP ON command. Will retry check later.")
                    # State remains OFF, maybe retry sending ON next loop?
            else:
                # Pump is already running from a previous calculation? Should not happen with daily logic.
                # This might indicate an issue. Let's just log it.
                print(f"   WARNING: Daily calculation requires pump ON ({pump_time_s:.1f}s), but pump is already running.")
                # Optionally: Update the target duration?
                # current_pump_run_duration = pump_time_s # Update with new time? Or let old one finish?
                # pump_start_time = time.time() # Reset start time? Needs careful thought.
        else:
            # No irrigation needed today based on calculations
            print("   No irrigation required today.")
            if pump_running:
                # This case is odd - calculation says OFF, but state is ON. Turn it OFF.
                print("   WARNING: Calculation requires pump OFF, but pump is currently ON. Sending PUMP_OFF.")
                publish_success = publish_message(client, TOPIC_PUMP_CMD, "PUMP_OFF")
                if publish_success:
                    pump_running = False
                    current_pump_run_duration = 0.0
                else:
                     print("   Failed to send PUMP OFF command. State remains ON, will retry check.")
            else:
                # Pump is OFF and calculation says OFF - correct state.
                pass


        # 7. --- Log Daily Summary (Optional) ---
        log_line = (f"{today_str},"
                    f"{format_value(mean_vwc, 1)},"
                    f"{format_value(last_et0, 2)},"
                    f"{format_value(etc_val, 2)},"
                    f"{format_value(pump_time_s, 1)},"
                    f"{format_value(avail_mm, 1)},"
                    f"{format_value(rz_mm, 1)},"
                    f"{format_value(Kc_today, 3)}\n")
        print(f"   Daily Log Data: {log_line.strip()}")
        try:
            # Check if header needed
            header_needed = False
            try:
                os.stat(LOG_FILE)
            except OSError:
                header_needed = True # File doesn't exist

            with open(LOG_FILE, 'a') as f:
                 if header_needed:
                     f.write("Date,MeanVWC_pct,ET0_mm,ETc_mm,PumpTime_s,AvailWater_mm,RZ_mm,Kc\n")
                     print(f"   Created log file {LOG_FILE} with header.")
                 f.write(log_line)
                 # print(f"   Logged daily summary to {LOG_FILE}") # Reduce verbosity
        except Exception as e:
            print(f"   ⚠ Error writing to daily log file ({LOG_FILE}): {e}")

        # 8. --- Update Date Marker & Cleanup ---
        last_date_processed = today_str
        gc.collect() # Collect garbage after daily intensive tasks
        print(f"   Free Memory after daily tasks: {gc.mem_free()} bytes")
        print(f"--- Finished Daily Logic for {today_str} ---")
        # --- End Daily Rollover Logic ---

    # --- Pump OFF Check (Run Every Loop Iteration) ---
    if pump_running:
        elapsed_time = time.time() - pump_start_time
        if elapsed_time >= current_pump_run_duration:
            print(f"   Pump run time ({current_pump_run_duration:.1f}s) elapsed (Actual: {elapsed_time:.1f}s). Turning pump OFF.")
            publish_success = publish_message(client, TOPIC_PUMP_CMD, "PUMP_OFF")
            if publish_success:
                pump_running = False
                current_pump_run_duration = 0.0 # Reset duration
            else:
                 print("   Failed to send PUMP OFF command. Will retry check next loop.")
                 # Pump state remains ON in our variable, but hopefully it stops eventually or gets turned off next loop.

    # --- Periodic Status Print (Uses latest state variables) ---
    # Print status less frequently to avoid flooding console? e.g. every 5 loops
    status_print_interval = 5 # Print every 5 loops (approx 5 mins if wait_interval is 60s)
    if loop_count % status_print_interval == 0:
        print("\n--- Status Update ---")
        # Use the state variables (last_tmax, etc.) for printing
        print(f"  Weather (last valid): Tmax={format_value(last_tmax, 1, 'C')}, RH={format_value(last_rh, 0, '%')}, E={format_value(last_energy, 2, 'MJ')}, ET0={format_value(last_et0, 2, 'mm')}")
        # Show mean_vwc from last successful sample
        mean_vwc_print = format_value(mean_vwc, 1, '%') if mean_vwc is not None else "N/A (waiting for daily sample)"
        print(f"  Soil: Mean VWC={mean_vwc_print} -> Avail={format_value(avail_mm, 1, 'mm')} (RZ={format_value(rz_mm, 1, 'mm')})")
        print(f"  Crop (Day {days}): Kc={format_value(Kc_today, 3)}, ETc={format_value(etc_val, 2, 'mm')}")
        # Show pump state and remaining time if running
        pump_state_str = 'ON' if pump_running else 'OFF'
        if pump_running:
            remaining_time = max(0, current_pump_run_duration - (time.time() - pump_start_time))
            pump_state_str += f" (Target: {format_value(current_pump_run_duration, 1, 's')}, Remaining: {format_value(remaining_time, 0, 's')})"
        else:
            pump_state_str += f" (Target: {format_value(current_pump_run_duration, 1, 's')})" # Show 0 target when off
        print(f"  Pump State: {pump_state_str}")
        print(f"  WiFi State: {'Connected' if wlan and wlan.isconnected() else 'Disconnected'}")
        print(f"  MQTT Client State: {'Connected' if client else 'Disconnected'}")
        print(f"  Free Memory: {gc.mem_free()} bytes")
        print("---------------------")

    # --- Wait Before Next Cycle ---
    wait_interval = 60 # seconds
    #print(f"Sleeping for {wait_interval} seconds...") # Reduce verbosity
    time.sleep(wait_interval)
    # gc.collect() # Optional: Collect garbage every loop? Might not be needed if daily collect is enough.

# [End of file] - Loop should ideally never exit 