# main.py -- Run on Raspberry Pi Pico W under MicroPython - MQTT Logging Only

import time
import gc
import math
import urequests
import os
import network # Added for WiFi
import ssl     # Added for secure MQTT
from machine import Pin
from umqtt.simple import MQTTClient

# --- Initial Prints (Will still appear on Terminal) ---
print("--- Pico W Script Starting ---")

# -----------------------------------------------------------------------------
# 1) IMPORT YOUR MODEL
# -----------------------------------------------------------------------------
predict_function = None
model_module_name = 'mlp_et0_predictotr'

try:
    model_module = __import__(model_module_name)
    print(f"✅ {model_module_name}.py imported successfully.") # Initial Print

    if hasattr(model_module, 'predict_et0'):
        predict_function = model_module.predict_et0
        print(f"   Using 'predict_et0' function from {model_module_name}.") # Initial Print
    else:
        print(f"⚠️ ERROR: {model_module_name}.py found, but 'predict_et0' function is missing!") # Initial Print
        raise ImportError

except ImportError as e:
    print(f"⚠️ {model_module_name}.py not found or error during import: {e}.") # Initial Print
    print("   Using dummy model which returns 0.0 for ET0 prediction.") # Initial Print
    def dummy_predict_et0(feats):
        # This print will only happen if dummy is called, indicating an issue.
        print("   WARNING: Dummy predict_et0 called, returning 0.0") # Keep this local print!
        return 0.0
    predict_function = dummy_predict_et0

except Exception as e:
     print(f"❌ An unexpected error occurred during model import: {e}") # Initial Print
     print("   Halting execution as model cannot be loaded.") # Initial Print
     raise SystemExit

# -----------------------------------------------------------------------------
# 2) NURSERY PROFILES & INTERPOLATION (Unchanged)
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
    if not profile: return 0.0
    if day <= profile[0][0]: return profile[0][1]
    if day >= profile[-1][0]: return profile[-1][1]
    for (d0,v0),(d1,v1) in zip(profile, profile[1:]):
        if d0 <= day <= d1:
            return v0 + (v1-v0)*(day-d0)/(d1-d0) if (d1-d0) != 0 else v0
    return profile[-1][1]

def get_days_after_planting(Y, M, D):
    try:
        if not (1 <= M <= 12 and 1 <= D <= 31):
             raise ValueError("Invalid Month or Day provided")
        sow_tuple = (Y, M, D, 0, 0, 0, 0, 0)
        sow = time.mktime(sow_tuple)
        now = time.mktime(time.localtime())
        days = max(0, int((now - sow)//86400))
        return days
    except Exception as e:
        # This error happens before logging is fully set up, keep local print
        print(f"⚠️ Error in get_days_after_planting ({Y}-{M}-{D}): {e}")
        return -1

# -----------------------------------------------------------------------------
# 3) LOGGING (Optional file logging - unchanged)
# -----------------------------------------------------------------------------
LOG_FILE  = 'daily_log.csv'

def get_today_str():
    t = time.localtime()
    return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"

def ensure_log_header():
    header = "Date,MeanVWC,ET0,ETc,PumpTimeS,AvailWaterMM,RootZoneMM,Kc\n"
    try:
        size = os.stat(LOG_FILE)[6] if LOG_FILE in os.listdir() else 0
        if size == 0:
            with open(LOG_FILE, 'w') as f: f.write(header)
            print(f"Created log file '{LOG_FILE}' with header.") # Initial Print
    except Exception as e: print(f"Error checking/creating log file: {e}") # Initial Print

# -----------------------------------------------------------------------------
# 4) MQTT CONFIGURATION & STATE
# -----------------------------------------------------------------------------
MQTT_BROKER     = b"MQTT WEB"
MQTT_PORT       = 8883
MQTT_USER       = b"USER"
MQTT_PASSWORD   = b"PWD"
MQTT_CLIENT_ID  = b"pico_w_eto_predictor_v7_mqtt_log_only" # Unique ID

# Topics
TOPIC_SOIL_SUB  = b"esp32/soilMoisture"
TOPIC_PUMP_CMD  = b"esp32/pump/control"
TOPIC_LOG_PUB   = b"RPi/Pico/Log" # Topic for publishing logs
TOPIC_PUMP_REMAINING_TIME_PUB=b"RPi/Pico/PumpRemainingTime"

# Config topics (unchanged)
TOPIC_CONFIG_BASE = "User/Input/"; TOPIC_CONFIG_CROP = TOPIC_CONFIG_BASE + "Crop"
TOPIC_CONFIG_PLANTING_DATE = TOPIC_CONFIG_BASE + "Planting/Date"; TOPIC_CONFIG_PLANTS_NUMBER = TOPIC_CONFIG_BASE + "Plants/Number"
TOPIC_CONFIG_PLANTS_SPACING = TOPIC_CONFIG_BASE + "Plants/Spacing"; TOPIC_CONFIG_ROW_SPACING = TOPIC_CONFIG_BASE + "Row/Spacing"
TOPIC_CONFIG_PUMP_FLOWRATE = TOPIC_CONFIG_BASE + "Pump/Flowrate"

# State Variables (unchanged)
soil_buffer = []; sampling_active = False; config_params = {}
required_configs = {'crop', 'planting_date', 'plants_number', 'plant_spacing_cm', 'row_spacing_cm', 'pump_flow_lph'}

# Global MQTT Client Reference
client = None

# --- MQTT Logging Function (MODIFIED) ---
def log_message(message, level="INFO"):
    """Formats a message and publishes ONLY to MQTT log topic."""
    global client # Access the global client object
    try:
        # Get timestamp
        t = time.localtime()
        timestamp_str = f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        # Format log entry
        log_entry = f"{timestamp_str} [{level}] {message}"

        # --- LOCAL PRINT REMOVED ---
        # print(log_entry) # <--- REMOVED

        # Publish to MQTT (if client is connected)
        if client:
            try:
                log_bytes = log_entry.encode('utf-8')
                client.publish(TOPIC_LOG_PUB, log_bytes)
            except OSError as e:
                # Keep local print ONLY for failure to publish log message
                print(f"{timestamp_str} [ERROR] MQTT connection error publishing log: {e}")
            except Exception as e:
                # Keep local print ONLY for failure to publish log message
                print(f"{timestamp_str} [ERROR] Failed to publish log message: {e}")
        # else: Client not connected, log is skipped

    except Exception as e:
        # Keep local print ONLY for errors within the logging function itself
        print(f"!!! ERROR IN log_message FUNCTION: {e} !!!")
        print(f"    Original message: {message}")


# --- MQTT Helper Functions (MODIFIED publish_message) ---
def publish_message(client_obj, topic, message):
    """Publishes an MQTT message and logs status/errors via log_message."""
    if not client_obj:
        # Log error via log_message (which will attempt MQTT publish if possible)
        log_message(f"Cannot publish to {topic.decode()}: MQTT client not connected.", level="ERROR")
        return False
    try:
        msg_bytes = message.encode('utf-8') if isinstance(message, str) else message
        client_obj.publish(topic, msg_bytes)
        # Only log success confirmation for non-log topics
        if topic != TOPIC_LOG_PUB:
             log_message(f"Published '{message}' to {topic.decode()}", level="INFO") # Use log_message
        return True
    except OSError as e:
        log_message(f"MQTT connection error during publish to {topic.decode()}: {e}.", level="ERROR")
        return False
    except Exception as e:
        log_message(f"Failed to publish to {topic.decode()}: {e}", level="ERROR")
        return False

# --- MQTT Callback (Uses log_message - unchanged from previous) ---
def sub_cb(topic_b, msg_b):
    global soil_buffer, config_params
    try:
        topic_str = topic_b.decode('utf-8')
        msg_str = msg_b.decode('utf-8').strip()
        log_message(f"MQTT Recv | Topic: {topic_str}, Msg: '{msg_str}'", level="DEBUG")

        if topic_b == TOPIC_SOIL_SUB:
            if sampling_active:
                try: soil_buffer.append(float(msg_str))
                except ValueError: log_message(f"Received non-numeric soil data: '{msg_str}'", level="ERROR")
        elif topic_str == TOPIC_CONFIG_CROP:
            crop_name = msg_str.lower()
            if crop_name in crop_kc_profile: config_params['crop'] = crop_name; log_message(f"Config Received: Crop = {crop_name}", level="CONFIG")
            else: log_message(f"Received unsupported crop name '{msg_str}'", level="ERROR")
        elif topic_str == TOPIC_CONFIG_PLANTING_DATE:
            try:
                parts = msg_str.split('-'); y, m, d = map(int, parts)
                if len(parts) == 3 and 1 <= m <= 12 and 1 <= d <= 31: config_params['planting_date'] = msg_str; log_message(f"Config Received: Planting Date = {msg_str}", level="CONFIG")
                else: raise ValueError("Invalid date components")
            except Exception as e: log_message(f"Invalid planting date format '{msg_str}'. Use YYYY-MM-DD. ({e})", level="ERROR")
        elif topic_str == TOPIC_CONFIG_PLANTS_NUMBER:
            try: num = int(msg_str); config_params['plants_number'] = num; log_message(f"Config Received: Plants Number = {num}", level="CONFIG") if num > 0 else log_message("Number of plants must be positive.", level="ERROR")
            except ValueError: log_message(f"Invalid number of plants '{msg_str}'", level="ERROR")
        elif topic_str == TOPIC_CONFIG_PLANTS_SPACING:
            try: spacing = float(msg_str); config_params['plant_spacing_cm'] = spacing; log_message(f"Config Received: Plant Spacing = {spacing} cm", level="CONFIG") if spacing > 0 else log_message("Plant spacing must be positive.", level="ERROR")
            except ValueError: log_message(f"Invalid plant spacing '{msg_str}'", level="ERROR")
        elif topic_str == TOPIC_CONFIG_ROW_SPACING:
            try: spacing = float(msg_str); config_params['row_spacing_cm'] = spacing; log_message(f"Config Received: Row Spacing = {spacing} cm", level="CONFIG") if spacing > 0 else log_message("Row spacing must be positive.", level="ERROR")
            except ValueError: log_message(f"Invalid row spacing '{msg_str}'", level="ERROR")
        elif topic_str == TOPIC_CONFIG_PUMP_FLOWRATE:
            try: flow = float(msg_str); config_params['pump_flow_lph'] = flow; log_message(f"Config Received: Pump Flow Rate = {flow} L/h", level="CONFIG") if flow > 0 else log_message("Pump flow rate must be positive.", level="ERROR")
            except ValueError: log_message(f"Invalid pump flow rate '{msg_str}'", level="ERROR")
    except Exception as e: log_message(f"Error processing MQTT message in sub_cb: {e}", level="ERROR")

# --- MQTT Connection (Uses initial print) ---
def connect_mqtt():
    print("Attempting to connect to MQTT broker...") # Initial Print
    temp_client = MQTTClient(client_id=MQTT_CLIENT_ID, server=MQTT_BROKER, port=MQTT_PORT, user=MQTT_USER, password=MQTT_PASSWORD, keepalive=7200, ssl=True, ssl_params={'server_hostname': MQTT_BROKER.decode('utf-8')})
    try:
        temp_client.set_callback(sub_cb)
        temp_client.connect()
        print(f"✅ MQTT Connected to {MQTT_BROKER.decode('utf-8')}!") # Initial Print
        temp_client.subscribe(TOPIC_SOIL_SUB)
        print(f"✅ Subscribed to Data: {TOPIC_SOIL_SUB.decode()}") # Initial Print
        # Subscribe to Config Topics
        config_topics_bytes = [ t.encode('utf-8') for t in [ TOPIC_CONFIG_CROP, TOPIC_CONFIG_PLANTING_DATE, TOPIC_CONFIG_PLANTS_NUMBER, TOPIC_CONFIG_PLANTS_SPACING, TOPIC_CONFIG_ROW_SPACING, TOPIC_CONFIG_PUMP_FLOWRATE ]]
        for topic_b in config_topics_bytes:
            try: temp_client.subscribe(topic_b); print(f"✅ Subscribed to Config: {topic_b.decode()}") # Initial Print
            except Exception as sub_e: print(f"❌ Failed to subscribe to {topic_b.decode()}: {sub_e}") # Initial Print
        return temp_client
    except Exception as e:
        print(f"❌ Failed to connect or subscribe to MQTT Broker: {e}") # Initial Print
        return None

# --- Wait for Config (Uses log_message) ---
def wait_for_configuration(client_obj):
    # This function will now only log to MQTT
    log_message("Waiting for configuration parameters via MQTT...")
    log_message(f"Required parameters: {', '.join(required_configs)}", level="DEBUG")
    start_wait = time.time(); MAX_WAIT_SECONDS = 600
    last_wait_log_time = 0
    while True:
        missing_configs = required_configs - set(config_params.keys())
        if not missing_configs: log_message("All configuration parameters received!", level="CONFIG"); return True
        if time.time() - start_wait > MAX_WAIT_SECONDS: log_message(f"Timeout waiting for configuration after {MAX_WAIT_SECONDS} seconds.", level="ERROR"); log_message(f"Missing parameters: {', '.join(missing_configs)}", level="ERROR"); return False
        if client_obj:
            try: client_obj.check_msg()
            except OSError as e: log_message(f"MQTT connection error while waiting for config: {e}. Returning False.", level="ERROR"); return False
            except Exception as e: log_message(f"Error during check_msg while waiting for config: {e}", level="ERROR")
        else: log_message("MQTT client lost while waiting for config. Returning False.", level="ERROR"); return False
        if time.time() - last_wait_log_time > 15: log_message(f"Waiting... Received: {', '.join(config_params.keys())}. Missing: {', '.join(missing_configs)}", level="DEBUG"); last_wait_log_time = time.time()
        time.sleep(0.1)

# -----------------------------------------------------------------------------
# 5) WIFI & WEATHER API CONFIG
# -----------------------------------------------------------------------------
WIFI_SSID   = 'USER'
WIFI_PASS   = 'PWD'
OWM_API_KEY = 'API KEY'
LAT, LON    = 13.0192526, 77.5630184
OWM_URL     = (f"http://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OWM_API_KEY}&units=metric")

# WiFi Connection (Uses initial print, then log_message)
def connect_wifi(ssid, pwd):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # wifi_log_func = log_message # Define later after global client might exist
    if not wlan.isconnected():
        print(f'Connecting to WiFi ({ssid})...') # Initial Print
        wlan.connect(ssid, pwd)
        max_wait = 15; print("   ", end="")
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3: break
            max_wait -= 1; print('.', end=''); time.sleep(1)
        print()
    if wlan.isconnected():
        # Now use log_message if available, otherwise print
        log_func = log_message if client else print
        log_func('WiFi connected!')
        log_func(f'Network config: {wlan.ifconfig()}')
        return wlan
    else:
        # Use print as this might happen before MQTT is up
        print('❌ WiFi connection failed!')
        return None

# -----------------------------------------------------------------------------
# 6) UTILITY FUNCTIONS (Uses log_message - unchanged from previous)
# -----------------------------------------------------------------------------
def potential_daylight_hours(lat_deg, doy):
    phi = math.radians(lat_deg); doy = max(1, min(doy, 366))
    decl = 0.409 * math.sin(2*math.pi*doy/365 - 1.39)
    x = max(-1.0, min(1.0, -math.tan(phi)*math.tan(decl)))
    try: return (24/math.pi)*math.acos(x)
    except ValueError: log_message(f"Math domain error in potential_daylight_hours (x={x}).", level="WARNING"); return 12
WH_TO_MJ = 0.0036
def fetch_weather():
    log_message("Fetching weather data...")
    log_message(f"URL: {OWM_URL}", level="DEBUG")
    response = None
    try:
        response = urequests.get(OWM_URL, timeout=20)
        status_code = response.status_code; log_message(f"HTTP Status Code: {status_code}", level="DEBUG")
        raw_text = response.text
        if status_code != 200: log_message(f"Weather API Error: Status Code {status_code}", level="ERROR"); log_message(f"Response Body: {raw_text}", level="ERROR"); return None
        d = response.json(); log_message("Weather data received and parsed.")
    except Exception as e:
        log_message(f"Failed to fetch or parse weather data: {e}", level="ERROR")
        if response and hasattr(response, 'text'):
             try: log_message(f"Response text (on error): {response.text}", level="DEBUG")
             except: pass
        return None
    finally:
        if response: response.close()
    main_data=d.get('main', {}); clouds_data=d.get('clouds', {}); clouds=clouds_data.get('all', 50); tmax=main_data.get('temp_max', main_data.get('temp', 25.0)); rh=main_data.get('humidity', 60); ts=d.get('dt', int(time.time()))
    try: _, _, _, _, _, _, _, yearday = time.gmtime(ts); doy=yearday
    except Exception as e: log_message(f"Could not get DOY from timestamp {ts}: {e}. Using default.", level="WARNING"); doy = 180
    N=potential_daylight_hours(LAT, doy); F=min(1, max(0, clouds/100)); P=990*(1 - 0.75*(F**3)); E_wh_m2=P*N; E_mj_m2_day=round(E_wh_m2*WH_TO_MJ, 2)
    log_message(f"Weather Parsed: Tmax={tmax}, RH={rh}, Clouds={clouds}, DOY={doy}, N={N:.2f}h, E={E_mj_m2_day} MJ/m^2/day", level="DEBUG")
    return tmax, rh, E_mj_m2_day
def soil_available_water_depth(vwc_pct, rz_depth_mm, fc_pct=42.0, pwp_pct=15.0):
    if vwc_pct is None: return 0.0
    try: θ=float(vwc_pct)/100.0; fc=float(fc_pct)/100.0; pwp=float(pwp_pct)/100.0; rz=float(rz_depth_mm)
    except (ValueError, TypeError): log_message("Invalid numeric input to soil_available_water_depth.", level="ERROR"); return 0.0
    if fc <= pwp: log_message(f"Field Capacity ({fc_pct}%) <= PWP ({pwp_pct}%).", level="WARNING"); return 0.0
    taw_fraction=fc-pwp; taw_mm=taw_fraction*rz; current_water_above_pwp_fraction=max(0, θ-pwp); current_water_above_pwp_mm=current_water_above_pwp_fraction*rz; available_mm=min(current_water_above_pwp_mm, taw_mm)
    return round(available_mm, 2)
def irrigation_time(Kc, ET0, avail_mm, area_m2, flow_lph=9.0):
    try: Kc_f=float(Kc); ET0_f=float(ET0); area_f=float(area_m2); flow_f=float(flow_lph)
    except (ValueError, TypeError): log_message("Invalid numeric input to irrigation_time.", level="ERROR"); return 0.0, 0.0
    ETc=ET0_f*Kc_f; req_mm=max(0, ETc); req_liters=(req_mm/1000.0)*area_f*1000.0
    if flow_f <= 0: log_message("Pump flow rate must be positive.", level="ERROR"); return 0.0, ETc
    time_seconds = (req_liters / flow_f) * 3600.0 if req_liters > 0 else 0.0
    return time_seconds, ETc

# -----------------------------------------------------------------------------
# 7) INTERACTIVE NURSERY SETUP (REMOVED)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# 8) CONNECT, CONFIGURE & INITIALIZE (Uses initial prints and log_message)
# -----------------------------------------------------------------------------
print("\n--- Starting Initialization ---") # Initial Print
wlan = connect_wifi(WIFI_SSID, WIFI_PASS)
if not wlan or not wlan.isconnected():
      print("❌ Halting execution due to WiFi connection failure.") # Initial Print
      raise SystemExit

client = connect_mqtt() # Assigns to global client
if not client:
    print("❌ Halting execution due to MQTT connection failure.") # Initial Print
    raise SystemExit

# Wait for config (Uses log_message internally)
if not wait_for_configuration(client):
     log_message("Halting execution: Failed to receive configuration via MQTT.", level="FATAL")
     if client:
          try: client.disconnect()
          except: pass
     raise SystemExit

# Process Config (Uses log_message internally)
log_message("--- Processing Received Configuration ---", level="SYSTEM")
try:
    crop = config_params['crop']; planting_date_str = config_params['planting_date']; n_plants = config_params['plants_number']
    ps_cm = config_params['plant_spacing_cm']; rs_cm = config_params['row_spacing_cm']; pump_flow_lph = config_params['pump_flow_lph']
    Y, Mo, Da = map(int, planting_date_str.split('-')); days = get_days_after_planting(Y, Mo, Da)
    if days == -1: raise ValueError("Invalid planting date.")
    if crop not in crop_kc_profile or crop not in crop_root_profile: raise ValueError(f"Crop '{crop}' profile not found.")
    Kc_today = linear_interpolate(days, crop_kc_profile[crop]); rz_m = linear_interpolate(days, crop_root_profile[crop]); rz_mm = rz_m * 1000.0
    area_per_plant_m2 = (ps_cm / 100.0) * (rs_cm / 100.0); total_area_m2 = area_per_plant_m2 * n_plants
    log_message("Configuration processed successfully:", level="CONFIG"); log_message(f"Crop: {crop}", level="CONFIG"); log_message(f"Planting Date: {planting_date_str} (-> {days} days ago)", level="CONFIG")
    log_message(f"Plants: {n_plants}, Plant Spacing: {ps_cm}cm, Row Spacing: {rs_cm}cm", level="CONFIG"); log_message(f"Calculated Total Area: {total_area_m2:.3f} m²", level="CONFIG")
    log_message(f"Pump Flow Rate: {pump_flow_lph} L/h", level="CONFIG"); log_message(f"Initial Derived: Kc = {Kc_today:.3f}, RZ = {rz_mm:.1f} mm", level="CONFIG")
except KeyError as ke: log_message(f"Error processing configuration: Missing parameter {ke}", level="FATAL"); raise SystemExit
except ValueError as ve: log_message(f"Error processing configuration: Invalid value - {ve}", level="FATAL"); raise SystemExit
except Exception as e: log_message(f"Unexpected error during configuration processing: {e}", level="FATAL"); raise SystemExit

# Init Runtime State
ensure_log_header()
gc.enable(); log_message("Garbage Collection Enabled.")
last_date = ""
mean_vwc = None; avail_mm = 0.0; etc_val = 0.0; pump_time_s = 0.0
last_tmax = None; last_rh = None; last_energy = None; last_et0 = 0.0
pump_running = False; pump_start_time = 0; current_pump_run_duration = 0.0
last_status_print_time = 0 # Initialize status print timer

def format_value(val, precision=1, unit=""):
    if val is None: return "N/A"
    try: return f"{val:.{precision}f}{unit}"
    except (TypeError, ValueError): return "Error"

# -----------------------------------------------------------------------------
# 9) MAIN LOOP (Uses log_message)
# -----------------------------------------------------------------------------
log_message("--- Starting Main Loop ---", level="SYSTEM")
while True:
    current_time_check = time.time()
    # MQTT Check & Reconnect (Uses log_message)
    mqtt_connection_ok = True
    if client:
        try: client.check_msg()
        except OSError as e: log_message(f"MQTT connection error during check_msg: {e}.", level="ERROR"); mqtt_connection_ok = False
        except Exception as e: log_message(f"Unexpected error during check_msg: {e}", level="ERROR"); time.sleep(5)
    else: mqtt_connection_ok = False
    if not mqtt_connection_ok:
        if client:
            try: client.disconnect()
            except: pass
        client = None; log_message("Attempting MQTT reconnect...")
        time.sleep(5); client = connect_mqtt()
        if not client: log_message("Reconnect failed. Waiting...", level="WARNING"); time.sleep(60); gc.collect(); continue
        else: log_message("MQTT reconnected successfully.")

    # Daily Rollover Logic (Uses log_message)
    today = get_today_str()
    if today != last_date:
        log_message(f"--- New Day: {today} ---", level="SYSTEM")
        # 1. Soil Sampling
        log_message("Sampling soil moisture..."); sampling_active = True; soil_buffer.clear(); start_sample_time = time.time(); sample_duration_seconds = 300
        while time.time() - start_sample_time < sample_duration_seconds:
            if client:
                try: client.check_msg(); time.sleep(0.1)
                except OSError as e: log_message(f"MQTT error during sampling: {e}. Aborting.", level="ERROR"); sampling_active = False; break
                except Exception as e: log_message(f"Unexpected error during sampling: {e}", level="ERROR"); time.sleep(0.5)
            else: log_message("MQTT client lost during sampling. Aborting.", level="ERROR"); sampling_active = False; break
        sampling_active = False; log_message(f"Sampling complete. Samples: {len(soil_buffer)}.")
        # 2. Calculate Mean VWC
        if soil_buffer: mean_vwc = sum(soil_buffer) / len(soil_buffer); log_message(f"Mean VWC for {today}: {mean_vwc:.1f}%")
        else:
            log_message(f"No soil samples received for {today}.", level="WARNING")
            if mean_vwc is None: mean_vwc = 25.0; log_message(f"Using default VWC: {mean_vwc:.1f}%", level="WARNING")
            else: log_message(f"Reusing previous VWC: {mean_vwc:.1f}%", level="WARNING")
        # 3. Recalculate daily params
        log_message("Recalculating daily parameters..."); current_days = get_days_after_planting(Y, Mo, Da)
        if current_days != -1: days=current_days; Kc_today=linear_interpolate(days, crop_kc_profile[crop]); rz_m=linear_interpolate(days, crop_root_profile[crop]); rz_mm=rz_m*1000.0
        else: log_message("Error recalculating days, using previous.", level="WARNING")
        log_message(f"Day {days}: Kc={Kc_today:.3f}, RZ={rz_mm:.1f} mm")
        # 4. Fetch Weather & Update State
        log_message("Attempting daily weather fetch...") ; weather_data_tuple = fetch_weather()
        if weather_data_tuple:
            last_tmax, last_rh, last_energy = weather_data_tuple
            try:
                log_message(f"DEBUG: Predicting with: T={last_tmax}, RH={last_rh}, E={last_energy}", level="DEBUG")
                if predict_function: last_et0 = predict_function([last_tmax, last_rh, last_energy])
                else: log_message("Predict function N/A", level="ERROR"); last_et0 = 0.0
                if not isinstance(last_et0, (float, int)): log_message(f"Pred returned non-numeric: {last_et0}", level="WARNING"); last_et0 = 0.0
                log_message(f"Updated Daily Weather: Tmax={last_tmax}, RH={last_rh}, E={last_energy}, ET0={last_et0:.2f}")
            except Exception as e: log_message(f"Error predicting ET0: {e}", level="ERROR"); log_message(f"Keeping previous ET0: {last_et0:.2f}", level="WARNING")
        else:
            log_message("Daily weather fetch failed. Using last known values.", level="WARNING")
            if last_tmax is None: log_message("No valid weather ever fetched. Using ET0=0.0.", level="ERROR"); last_et0 = 0.0
        # 5. Calculate Irrigation Need
        if mean_vwc is None: log_message("Cannot calc irrigation: Mean VWC N/A.", level="ERROR"); avail_mm=0.0; pump_time_s=0.0; etc_val=0.0
        else: avail_mm = soil_available_water_depth(mean_vwc, rz_mm); pump_time_s, etc_val = irrigation_time(Kc_today, last_et0, avail_mm, total_area_m2, flow_lph=pump_flow_lph)
        log_message(f"Calculated Daily Need: ETc={etc_val:.2f}mm, Avail={avail_mm:.1f}mm -> Pump Time: {pump_time_s:.1f}s")
        # 6. Send PUMP ON/OFF command (Daily Decision)
        if pump_time_s > 0.5:
            if not pump_running:
                log_message(f"Irrigation required ({pump_time_s:.1f}s). Sending PUMP_ON.")
                if publish_message(client, TOPIC_PUMP_CMD, "PUMP_ON"): pump_running = True; pump_start_time = time.time(); current_pump_run_duration = pump_time_s
                else: log_message("Failed to send PUMP ON.", level="ERROR"); pump_running = False; current_pump_run_duration = 0.0
            else: log_message(f"Daily calc needs pump ({pump_time_s:.1f}s), but pump already running. Updating target.", level="WARNING"); current_pump_run_duration = pump_time_s
        else:
            log_message("No irrigation required today.")
            if pump_running:
                log_message("Calc time is 0, but pump running. Sending PUMP_OFF.")
                if publish_message(client, TOPIC_PUMP_CMD, "PUMP_OFF"): pump_running = False; current_pump_run_duration = 0.0
                else: log_message("Failed to send PUMP OFF.", level="ERROR")
            else: pump_running = False; current_pump_run_duration = 0.0
        # 7. Log Daily Summary
        if mean_vwc is not None:
            try:
                with open(LOG_FILE, 'a') as f: f.write(f"{today},{mean_vwc:.1f},{last_et0:.2f},{etc_val:.2f},{pump_time_s:.1f},{avail_mm:.1f},{rz_mm:.1f},{Kc_today:.3f}\n")
            except Exception as e: log_message(f"Error writing daily log file: {e}", level="ERROR")
        # 8. Update Date Marker
        last_date = today; log_message(f"--- End Daily Logic for {today} ---", level="SYSTEM")

    # Pump OFF Check (Every Loop) (Uses log_message)
    if pump_running:
        elapsed_time = time.time() - pump_start_time
        if elapsed_time >= current_pump_run_duration:
            log_message(f"Pump target time ({current_pump_run_duration:.1f}s) elapsed. Sending PUMP_OFF.")
            if publish_message(client, TOPIC_PUMP_CMD, "PUMP_OFF"): pump_running = False; current_pump_run_duration = 0.0
            else: log_message("Failed to send PUMP OFF. Will retry check.", level="ERROR")

    # Periodic Status Log (Uses log_message)
    status_print_interval = 60
    if time.time() - last_status_print_time >= status_print_interval:
        log_message("--- Status Update ---", level="STATUS"); log_message(f"Weather: T={format_value(last_tmax,1,'°C')}, RH={format_value(last_rh,0,'%')}, E={format_value(last_energy,2,'MJ')}, ET0={format_value(last_et0,2,'mm')}", level="STATUS")
        mean_vwc_print = format_value(mean_vwc, 1, '%') if mean_vwc is not None else "N/A"; log_message(f"Soil: VWC={mean_vwc_print} -> Avail={format_value(avail_mm,1,'mm')} (RZ={format_value(rz_mm,1,'mm')})", level="STATUS")
        log_message(f"Crop (Day {days}): Kc={format_value(Kc_today,3)}, ETc={format_value(etc_val,2,'mm')}", level="STATUS")
        pump_state_str = 'ON' if pump_running else 'OFF'; remaining_time_str = ""
        if pump_running: remaining = max(0, current_pump_run_duration - (time.time() - pump_start_time)); remaining_time_str = f" (Rem: {format_value(remaining,0,'s')})"
        log_message(f"Pump: {pump_state_str} (Target: {format_value(current_pump_run_duration,1,'s')}){remaining_time_str}", level="STATUS"); log_message(f"MQTT: {'Connected' if client else 'Disconnected'}", level="STATUS"); log_message("------------------------", level="STATUS")
        last_status_print_time = time.time()

    # --- >>> ADDED: Publish Remaining Pump Time Periodically <<< ---
    remaining_time = 0.0 # Default to 0 if pump is off
    if pump_running:
        # Calculate elapsed time since pump was commanded ON
        elapsed_time = time.time() - pump_start_time
        # Calculate remaining time, ensuring it's not negative
        remaining_time = max(0.0, current_pump_run_duration - elapsed_time)

    # Format remaining time as string with 1 decimal place
    remaining_time_str = f"{remaining_time:.1f}"
    # Publish the remaining time (will publish "0.0" if pump is off)
    publish_message(client, TOPIC_PUMP_REMAINING_TIME_PUB, remaining_time_str)
    # --- End of Addition ---


    # --- Wait Before Next Cycle ---
    wait_interval = 30;
    # log_message(f"Sleeping for {wait_interval} seconds...", level="DEBUG") # Optional debug log
    time.sleep(wait_interval);
    gc.collect()
    # log_message(f"Free Memory: {gc.mem_free()} bytes", level="DEBUG") # Optional debug log


# [End of file]
