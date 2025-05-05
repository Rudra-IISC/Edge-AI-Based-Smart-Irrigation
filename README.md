# Edge AI-Based Smart Irrigation System

## Overview

This project implements an intelligent irrigation system leveraging edge AI to optimize water usage for [mention your target application, e.g., small farms, home gardens, seedling trays]. It utilizes a Raspberry Pi Pico W to host a machine learning model that analyzes soil moisture data from analog sensors and determines the precise irrigation needs. An ESP32 acts as a communication and control unit, receiving commands from the Pico via MQTT to activate a water pump through a relay module.

![Smart Irrigation System GUI](Data/Smart Irrigation System GUI.png)

## Components and Specifications

| Component             | Role/Use                                                                             | Specifications                                                        |
|----------------------|--------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| Raspberry Pi Pico W   | Hosts the MLP model and decision logic; reads sensors; computes irrigation volume.    | RP2040 dual-core 133MHz MCU, 264 KB RAM, Integrated Wi-Fi module       |
| ESP32                | Receives MQTT commands from Pico; drives the pump relay for irrigation.              | Dual-core 240MHz MCU with Wi-Fi/Bluetooth                             |
| Soil Moisture Sensor (Analog) | Measures volumetric water content (VWC); provides real-time soil moisture input. | Analog output providing VWC readings                                   |
| Relay Module         | Switches power to the water pump under ESP32 control.                               | 5V or 12V signal-controlled relay board                               |
| Water Pump           | Physically delivers water to the crop.                                               | 12V DC submersible or inline pump (flow rate ~ [Your Pump's Flow Rate] L/min) |

## System Architecture

![System architecture diagram](Data/Schematic_Smart_Irrigation_2025-05-04.png)

## Hardware Setup

This section provides details on how to set up the hardware components of the smart irrigation system.

![Hardware Setup Diagram](Data/Hardware Setup.png)

[Detailed instructions on wiring and connecting the hardware components, e.g., pin assignments, sensor connections, relay control, power supply.]

## Usage

This section describes how to set up and use the Edge AI-Based Smart Irrigation System.

### Initial Setup (Lab Environment)

1.  **Seedling Tray Preparation:** Place your seeds in the seedling trays with the desired soil or growth medium.
2.  **Sensor Placement:** Insert the soil moisture sensors into the seedling trays, ensuring good contact with the soil for accurate readings.
3.  **Hardware Connections:** Connect the soil moisture sensors to the ESP 32 as per your wiring diagram. Connect the relay module to the ESP32, and the water pump to the relay module, ensuring proper power supply for all components.
4.  **Software Deployment:** Flash the MicroPython firmware onto the Raspberry Pi Pico W and the ESP32 firmware onto the ESP32. Ensure the necessary libraries (e.g., `umqtt.simple`) are included.
5.  **Network Configuration:** Configure the Wi-Fi settings on both the Raspberry Pi Pico W and the ESP32 to connect to your local network.
6.  **MQTT Broker Setup):** Connect to external HiveMQ MQTT broker, ensure it is running and the Pico W and ESP32 are configured to connect to it.
7.  **Initial Monitoring:** Once the system is powered on, monitor the moisture levels reported by the sensors through the ESP 32

### Pump Control Interfaces

The water pump can be controlled through three different interfaces:

1.  **Manual On/Off via Node-RED Dashboard:**
    * Access the Node-RED dashboard that you have configured for this project.
    * On the dashboard, you will find controls (e.g., buttons or switches) to manually turn the water pump ON and OFF.
    * Use these controls as needed for manual irrigation.

2.  **Manual On/Off by AR App:**
    * Launch the Augmented Reality (AR) application on your mobile device.
    * Navigate to the pump control interface within the AR app.
    * The app will provide buttons or interactive elements that allow you to manually turn the water pump ON and OFF by interacting with the augmented view of your system.

3.  **Automatic Control by Edge AI Model:**
    * The system will automatically control the water pump based on the predictions of the Edge AI-based irrigation model running on the Raspberry Pi Pico W.
    * The model takes into account real-time soil moisture levels from the sensors and relevant weather data (either historical averages embedded in the model or potentially real-time data fetched if you've implemented that).
    * Based on the predicted crop water needs (ETc) and the current soil moisture, the Pico W will send MQTT commands to the ESP32 to turn the pump ON or OFF for a calculated duration to maintain optimal soil moisture levels.
    * The system operates autonomously once the initial setup is complete and the automatic mode is active.

Ensure all components are powered correctly and the software is running as expected for each control interface to function properly. Monitor the system's behavior during initial testing to verify the correct operation of the sensors, pump control, and the AI-driven automation.

## Code Structure

[Provide a brief overview of the code organization, e.g., folders for ESP32 firmware, Pico code, AI models, utility scripts.]

## Software Stack

| Tool/Language        | Platform      | Role/Use                                                                                                | Key Libraries/Frameworks                 |
|----------------------|---------------|---------------------------------------------------------------------------------------------------------|----------------------------------------|
| Python               | PC            | Data handling, model development, training, export/deployment.                                        | pandas, numpy, scikit-learn, Jupyter   |
| MicroPython          | Pico W        | Edge inference, control logic, sensor interaction, communication.                                      | Pico W (built-in), Thonny, umqtt.simple |
| ESP32 Firmware       | ESP32         | MQTT-driven pump control based on commands from Pico.                                                 | umqtt.simple                           |
| Thonny               | PC            | Flashing MicroPython firmware onto Pico W.                                                              | (IDE functionality)                    |
| umqtt.simple         | Pico W / ESP32 | Lightweight MQTT client for communication.                                                              | (MicroPython library)                  |
| Jupyter Notebooks/Script | PC            | Development/execution of Python code for data processing, model training, deployment.                  | Jupyter, Python scripts                |

## Augmented Reality Based Smart Irrigation

This project incorporates an augmented reality (AR) application to enhance user interaction and understanding. The AR app allows users to visualize sensor data overlaid on the physical system, get real-time moisture readings, control the water pump, and access system status and alerts.

You can access the files and resources for the AR application in the following Google Drive folder:

[AR App Resources](https://drive.google.com/drive/folders/1TpJTIjEVfzm5t6Ri8KKJVAxK5ShAxkX6?usp=drive_link)

The folder contains:

* AR app APK (for Android)
* Unity AR App Source
* Documentation
* [Add any other key files]

Further development of the AR application could include interactive controls and user customization of visualizations.

## Contributing

[Guidelines for potential contributors]

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Conclusion

This project demonstrates a complete Edge AI solution for precision irrigation in nursery crops. By leveraging long-term climate data and an on-device MLP model, the system accurately predicts crop water needs (ETc) in real-time. The integration of crop coefficients (e.g., onion $K_c$) and soil moisture feedback ensures that watering is neither excessive nor insufficient at any stage. In trials, the Pico W's MLP inference achieved approximately 97% accuracy ($R^2 \approx 0.97$) against FAO-56 benchmarks, validating the approach. The edge deployment (MLP code in MicroPython) is lightweight and runs without cloud dependency. Hardware such as the ESP32 pump controller and moisture sensors have been successfully combined with the AI model into a functional prototype.

Moving forward, the system can be extended with a user interface (LCD or app) for monitoring, additional sensors (e.g., temperature probes), or ensemble models for other crops. The modular software and complete documentation on GitHub make it straightforward for technical teams to replicate or customize the system. Overall, this work provides a blueprint for water-efficient, smart irrigation solutions that marry domain knowledge (FAO ET₀, $K_c$) with modern edge AI techniques.
