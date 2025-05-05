# Edge AI-Based Smart Irrigation System

## Overview

This project implements an intelligent irrigation system leveraging edge AI to optimize water usage for [mention your target application, e.g., small farms, home gardens, seedling trays]. It utilizes a Raspberry Pi Pico W to host a machine learning model that analyzes soil moisture data from analog sensors and determines the precise irrigation needs. An ESP32 acts as a communication and control unit, receiving commands from the Pico via MQTT to activate a water pump through a relay module.

## Components and Specifications

| Component               | Role/Use                                                                                               | Specifications                                                                 |
|-------------------------|--------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Raspberry Pi Pico W     | Hosts the MLP model and decision logic; reads sensors; computes irrigation volume.                      | RP2040 dual-core 133MHz MCU, 264 KB RAM, Integrated Wi-Fi module                 |
| ESP32                   | Receives MQTT commands from Pico; drives the pump relay for irrigation.                               | Dual-core 240MHz MCU with Wi-Fi/Bluetooth                                      |
| Soil Moisture Sensor (Analog) | Measures volumetric water content (VWC) in soil/seedling trays. Provides real-time soil moisture input for control logic. | Analog output providing VWC readings                                           |
| Relay Module            | Switches power to the water pump under ESP32 control.                                                  | 5V or 12V signal-controlled relay board                                       |
| Water Pump              | Physically delivers water to the crop (through tubing, emitters, etc.).                                | 12V DC submersible or inline pump (flow rate ~ [Your Pump's Flow Rate] L/min) |

## System Architecture

![System architecture diagram](Data/Schematic_Smart_Irrigation_2025-05-04.png)

## Setup and Installation

[Provide detailed instructions on how to set up the hardware and software]

## Usage

[Explain how to operate the smart irrigation system]

## Code Structure

## Software Stack

The software components and tools used in this project are as follows:

| Tool/Language        | Platform | Role/Use                                                                                                                               | Key Libraries/Frameworks                                      |
|----------------------|----------|----------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------|
| Python               | PC       | Data handling and model development; training the machine learning model; exporting/deploying the model to the Pico.                 | pandas, numpy, scikit-learn, Jupyter notebooks               |
| MicroPython          | Pico W   | Edge inference and control logic; running the trained MLP model; interacting with sensors and managing communication.                 | Pico W (built-in), Thonny (IDE), manual matrix operations     |
| ESP32 Firmware       | ESP32    | MQTT-driven control of the water pump relay; subscribing to commands from the Pico and controlling the GPIO pin connected to the relay. | umqtt.simple (for MQTT communication)                         |
| Thonny               | PC       | Flashing MicroPython firmware onto the Raspberry Pi Pico W.                                                                          | (IDE functionality)                                           |
| umqtt.simple         | Pico W / ESP32 | Lightweight MQTT client library used for communication between the Pico W and the ESP32.                                      | (MicroPython library)                                         |
| Jupyter Notebooks/Script | PC       | Development and execution of Python code for data processing, model training, and potentially model export/deployment scripts.        | Jupyter (environment), Python scripts (custom development) |

## Contributing

[Guidelines for potential contributors]

## License

[Your chosen license]

## Conclusion

This project demonstrates a complete Edge AI solution for precision irrigation in nursery crops. By leveraging long-term climate data and an on-device MLP model, the system accurately predicts crop water needs (ETc) in real-time. The integration of crop coefficients (e.g., onion $K_c$) and soil moisture feedback ensures that watering is neither excessive nor insufficient at any stage. In trials, the Pico W's MLP inference achieved approximately 97% accuracy ($R^2 \approx 0.97$) against FAO-56 benchmarks, validating the approach. The edge deployment (MLP code in MicroPython) is lightweight and runs without cloud dependency. Hardware such as the ESP32 pump controller and moisture sensors have been successfully combined with the AI model into a functional prototype.

Moving forward, the system can be extended with a user interface (LCD or app) for monitoring, additional sensors (e.g., temperature probes), or ensemble models for other crops. The modular software and complete documentation on GitHub make it straightforward for technical teams to replicate or customize the system. Overall, this work provides a blueprint for water-efficient, smart irrigation solutions that marry domain knowledge (FAO ET₀, $K_c$) with modern edge AI techniques.
