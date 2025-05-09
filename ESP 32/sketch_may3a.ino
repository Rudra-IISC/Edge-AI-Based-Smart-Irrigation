#include <WiFi.h>
#include <WiFiClientSecure.h> // For secure TLS/SSL connection
#include <PubSubClient.h>     // For MQTT communication

// --- WiFi Credentials ---
const char* ssid = "wifi";         // Your WiFi network name
const char* password = "pwd"; // Your WiFi password

// --- HiveMQ Cloud MQTT Credentials ---
const char* mqtt_server = "Your HiveMQ Cloud URL"; // Your HiveMQ Cloud URL
const int mqtt_port = 8883;                                                     // Secure MQTT port (TLS/SSL)
const char* mqtt_user = "user";                                           // Your HiveMQ Cloud username
const char* mqtt_password = "pwd";                                       // Your HiveMQ Cloud password
const char* mqtt_topic_sensor = "esp32/soilMoisture";                          // Topic to publish sensor data to
const char* mqtt_topic_relay_on = "Relay/on";                                  // Topic to publish when relay is ON
const char* mqtt_topic_relay_off = "Relay/off";                                 // Topic to publish when relay is OFF
const char* mqtt_command_topic = "esp32/pump/control";                         // Topic to subscribe for commands

// --- Pin Definitions ---
const int sensor_pin = A0; // Analog sensor connected to GPIO 34 (ADC1_CH6 recommended for WiFi use)
#define RELAY_PIN 26      // *** GPIO 26 connected to relay module ***

// --- Relay Logic --- (ADJUST IF YOUR MODULE IS DIFFERENT)
#define RELAY_ON LOW   // Set to LOW if your relay module is Active LOW (most common)
#define RELAY_OFF HIGH // Set to HIGH if your relay module is Active LOW
// --- OR --- Uncomment below if your module is Active HIGH
// #define RELAY_ON HIGH
// #define RELAY_OFF LOW

// --- Global Variables ---
int sensorValue = 0;     // Stores raw ADC reading
int moisturePercent = 0; // Stores calculated moisture percentage
bool relayState = false; // Stores the current state of the relay

// --- Client Objects ---
WiFiClientSecure secureClient; // Use secure client for TLS/SSL
PubSubClient client(secureClient); // MQTT client using the secure WiFi client

// --- WiFi Connection Function ---
void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Connecting to WiFi [");
  Serial.print(ssid);
  Serial.print("]...");
  WiFi.mode(WIFI_STA); // Set WiFi mode to Station (client)
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

// --- MQTT Reconnection Function ---
void reconnect() {
  // Loop until we're reconnected
  while (!client.connected()) {
    Serial.print("Attempting MQTT connection...");
    // Create a unique client ID (e.g., based on ESP32 MAC address) or use a fixed one
    String clientId = "ESP32Client-";
    clientId += String(random(0xffff), HEX);
    // Attempt to connect
    if (client.connect(clientId.c_str(), mqtt_user, mqtt_password)) {
      Serial.println("connected");
      // You can subscribe to topics here if needed, e.g.:
      client.subscribe(mqtt_topic_sensor);    // Subscribe to the sensor data topic
      client.subscribe(mqtt_command_topic);   // Subscribe to the command topic
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state()); // Print the reason for failure
      Serial.println(" try again in 5 seconds");
      // Wait 5 seconds before retrying
      delay(5000);
    }
  }
}

// --- Arduino Setup Function ---
void setup() {
  Serial.begin(115200); // Start serial communication for debugging
  while (!Serial);     // Wait for serial connection (optional, useful for some boards)
  Serial.println("Booting...");

  // Configure Relay Pin (GPIO 26)
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, RELAY_OFF); // Ensure relay is OFF initially
  relayState = false;
  Serial.println("Relay Pin (GPIO 26) Initialized.");

  // Configure Sensor Pin (strictly optional for analogRead)
  // pinMode(sensor_pin, INPUT);

  // Connect to WiFi
  setup_wifi();

  // Configure MQTT secure client
  // !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  // !! WARNING: setInsecure() disables certificate validation.                     !!
  // !! This is INSECURE and only suitable for initial testing.                  !!
  // !! For production, use setCACert() or other validation methods.            !!
  // !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  secureClient.setInsecure();
  // Optional: If you have issues, you might need to increase MQTT buffer size
  // client.setBufferSize(1024); // Uncomment if needed for larger messages

  // Set MQTT server details
  client.setServer(mqtt_server, mqtt_port);
  // Optional: Set a callback function for incoming MQTT messages
  client.setCallback(callback); // Define a 'callback' function if you need to receive messages

  Serial.println("Setup complete.");
}

// --- Arduino Loop Function ---
void loop() {
  // Ensure MQTT client is connected
  if (!client.connected()) {
    reconnect();
  }
  client.loop(); // Allow the MQTT client to process incoming messages and maintain connection

  // --- Read Soil Moisture Sensor ---
  sensorValue = analogRead(sensor_pin); // Read from GPIO 34

  // --- Calculate Moisture Percentage ---
  // Map the raw ADC value to a percentage.
  // COMMON BEHAVIOUR: Lower ADC reading means WETTER soil. Higher reading means DRIER.
  // Adjust the range (4095, 0) based on your sensor's readings in fully dry and fully wet conditions for calibration.
  // Example mapping: Dry (e.g., 3000+) -> 0%, Wet (e.g., 1000-) -> 100%
  // Simple linear map from 4095 (Assumed Dry) to 0 (Assumed Wet):
  moisturePercent = map(sensorValue, 4095, 1000, 0, 30);
  moisturePercent = constrain(moisturePercent, 0, 30); // Ensure value stays within 0-100%

  // --- Print Sensor Data to Serial Monitor ---
  Serial.print("Raw ADC: ");
  Serial.print(sensorValue);
  Serial.print(" | Moisture: ");
  Serial.print(moisturePercent);
  Serial.println("%");

  // --- Publish Sensor Data via MQTT ---
  char payload[10];                                       // Buffer to hold string representation of percentage
  snprintf(payload, sizeof(payload), "%d", moisturePercent); // Convert integer percentage to string
  if (client.publish(mqtt_topic_sensor, payload)) {
    // Serial.println("Published moisture data."); // Optional success message
  } else {
    Serial.println("Failed to publish moisture data.");
  }

  // --- Relay Control Logic (Using RELAY_PIN which is GPIO 26) ---
  // The pump control based on moisture level has been REMOVED.
  // The relay will now ONLY be controlled by MQTT commands.

  // --- Delay ---
  // Wait before next loop iteration (e.g., 5 seconds)
  delay(5000);
}

// --- Optional: MQTT Message Callback Function ---
// Define this function if you subscribe to topics and need to handle incoming messages
void callback(char* topic, byte* payload, unsigned int length) {
  Serial.print("Message arrived [");
  Serial.print(topic);
  Serial.print("] ");
  payload[length] = '\0'; // Null-terminate the payload
  String message = String((char*)payload);
  Serial.println(message);

  // Add logic here to handle commands received via MQTT
  if (String(topic) == mqtt_command_topic) {
    if (message == "PUMP_ON") {
      Serial.println("Received PUMP_ON command. Turning pump ON (GPIO 26).");
      digitalWrite(RELAY_PIN, RELAY_ON); // RELAY_PIN is GPIO 26
      client.publish(mqtt_topic_relay_on, "ON");
      relayState = true;
    } else if (message == "PUMP_OFF") {
      Serial.println("Received PUMP_OFF command. Turning pump OFF (GPIO 26).");
      digitalWrite(RELAY_PIN, RELAY_OFF); // RELAY_PIN is GPIO 26
      client.publish(mqtt_topic_relay_off, "OFF");
      relayState = false;
    }
  }
}
