# Documentation

This script, MQTTManager, facilitates communication between a Unity application and an MQTT broker (specifically configured for HiveMQ in this case). It enables the Unity application to receive soil moisture data from an ESP32 device and to send commands to control a pump connected to the ESP32.

## Overview

The script performs the following key actions:

1.  **Connects to an MQTT Broker:** Establishes a secure (TLS) connection to a specified HiveMQ broker using provided credentials.
2.  **Subscribes to MQTT Topics:** Subscribes to two topics:
    * `esp32/soilMoisture`: To receive soil moisture readings from the ESP32.
    * `esp32/pump/control`: To receive updates on the pump's status from the ESP32.
3.  **Receives and Processes MQTT Messages:** Handles incoming messages on the subscribed topics.
    * Parses the soil moisture value from the `esp32/soilMoisture` topic and updates the corresponding UI element.
    * Parses the pump status from the `esp32/pump/control` topic and updates the corresponding UI element.
4.  **Sends MQTT Messages:** Allows the user to send commands (`PUMP_ON` and `PUMP_OFF`) to the `esp32/pump/control` topic by interacting with UI buttons.
5.  **Updates Unity UI:** Uses the `UnityMainThreadDispatcher` to ensure that UI updates from MQTT message callbacks are performed on the main Unity thread, preventing cross-thread issues.

## Script Properties (Inspector Settings)

The following properties can be configured directly in the Unity Inspector:

### HiveMQ Settings

* **Broker Host:** The hostname or IP address of the HiveMQ MQTT broker. **Default:** `"b1ef2a417ef147adad7b7222eacb6052.s1.eu.hivemq.cloud"`. **Important:** Replace this with your specific HiveMQ hostname.
* **Username:** The username for authenticating with the HiveMQ broker. **Default:** `"Rudra_123"`. **Important:** Replace this with your HiveMQ username.
* **Password:** The password for authenticating with the HiveMQ broker. **Default:** `"RudrA@123"`. **Important:** Replace this with your HiveMQ password.

### Unity UI

* **Moisture Text:** A `UnityEngine.UI.Text` component in your scene that will display the received soil moisture percentage. Drag and drop the Text UI object here in the Inspector.
* **Pump Status Text:** A `UnityEngine.UI.Text` component that will display the current status of the pump (e.g., "Pump is ON", "Pump is OFF"). Drag and drop the Text UI object here.
* **Pump On Button:** A `UnityEngine.UI.Button` component that, when clicked, will send the `PUMP_ON` command to the ESP32. Drag and drop the Button UI object here.
* **Pump Off Button:** A `UnityEngine.UI.Button` component that, when clicked, will send the `PUMP_OFF` command to the ESP32. Drag and drop the Button UI object here.

## Script Methods

### `async void Start()`

* This asynchronous method is called once when the script starts.
* It calls `ConnectToMqttBroker()` to establish the MQTT connection.
* It adds listeners to the `onClick` events of the `pumpOnButton` and `pumpOffButton`. When these buttons are clicked, the `SendPumpCommand()` method is called with the respective command ("PUMP\_ON" or "PUMP\_OFF").

### `private async Task ConnectToMqttBroker()`

* This asynchronous method handles the connection to the MQTT broker.
* It creates an `MqttFactory` and an `IMqttClient`.
* It builds `MqttClientOptions` to configure the connection:
    * Sets a unique client ID.
    * Specifies the TCP server address and port (8883 for secure MQTT).
    * Provides the username and password for authentication.
    * Configures TLS (Transport Layer Security) for a secure connection. It's set to use TLS and disallows untrusted certificates for security.
    * Sets a clean session flag.
* It attaches handlers for connection, disconnection, and message reception events:
    * `UseConnectedHandler`: Logs a message upon successful connection and subscribes to the `esp32/soilMoisture` and `esp32/pump/control` topics.
    * `UseDisconnectedHandler`: Logs a message upon disconnection.
    * `UseApplicationMessageReceivedHandler`: This crucial handler is called when a new MQTT message is received. It extracts the topic and payload, logs the received message, and then processes the payload based on the topic:
        * If the topic is `esp32/soilMoisture`, it attempts to parse the payload as a float and updates the `moistureText` UI element using the `UpdateMoistureUI()` method via the `UnityMainThreadDispatcher`.
        * If the topic is `esp32/pump/control`, it updates the pump status UI using the `UpdatePumpStatusBasedOnMessage()` method via the `UnityMainThreadDispatcher`.
* Finally, it attempts to connect to the broker using `mqttClient.ConnectAsync(options)` and logs any connection exceptions.

### `private void UpdateMoistureUI(float value)`

* This method takes a float `value` representing the soil moisture and updates the `Text` component assigned to `moistureText` to display this value as a percentage (formatted to one decimal place).

### `private void UpdatePumpStatus(string status)`

* This method takes a string `status` (e.g., "Pump is ON", "Pump is OFF") and updates the `Text` component assigned to `pumpStatusText` to display this status.

### `private void UpdatePumpStatusBasedOnMessage(string payload)`

* This method is called when a message is received on the `esp32/pump/control` topic.
* It checks the `payload`:
    * If the payload is `"PUMP_ON"`, it logs the status and calls `UpdatePumpStatus("Pump is ON")`.
    * If the payload is `"PUMP_OFF"`, it logs the status and calls `UpdatePumpStatus("Pump is OFF")`.
    * If the payload is any other value, it logs a warning about an unknown pump status.

### `private async void SendPumpCommand(string command)`

* This asynchronous method is called when the "Pump On" or "Pump Off" button is clicked.
* It checks if the `mqttClient` is currently connected to the broker.
* If connected, it creates an `MqttApplicationMessage` with the specified `command` as the payload and publishes it to the `esp32/pump/control` topic with `ExactlyOnceQoS` (Quality of Service level 2, ensuring the message is delivered exactly once).
* It logs a message indicating the command sent.
* It includes error handling for potential exceptions during the publishing process.
* If the client is not connected, it logs a warning.

## Important Notes

* **MQTTnet Library:** This script relies on the `MQTTnet` library for MQTT communication. Make sure you have installed this library in your Unity project (via the Package Manager).
* **UnityMainThreadDispatcher:** The script uses the `PimDeWitte.UnityMainThreadDispatcher` to safely update Unity UI elements from asynchronous MQTT callbacks. You need to have this utility script in your project. You can typically find this on GitHub or as a Unity asset.
* **HiveMQ Configuration:** Ensure that your HiveMQ broker is set up correctly and that the provided hostname, username, and password are accurate.
* **ESP32 Firmware:** The ESP32 device needs to be programmed to publish soil moisture readings to the `esp32/soilMoisture` topic and to listen for commands on the `esp32/pump/control` topic to control the pump. It should also publish its current pump status to the `esp32/pump/control` topic.
* **Topic Consistency:** The MQTT topics used in this script (`esp32/soilMoisture` and `esp32/pump/control`) must match the topics used in your ESP32 firmware.
* **Error Handling:** The script includes basic error logging for connection and publishing failures. You might want to implement more robust error handling for production environments.
* **UI Element Assignment:** Ensure that you have correctly assigned the Text and Button UI elements in the Unity Inspector for the script to function properly.
