using UnityEngine;
using UnityEngine.UI;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Client.Options;
using System;
using System.Text;
using System.Threading.Tasks;
using PimDeWitte.UnityMainThreadDispatcher;

public class MQTTManager : MonoBehaviour
{
    [Header("HiveMQ Settings")]
    public string brokerHost = "b1ef2a417ef147adad7b7222eacb6052.s1.eu.hivemq.cloud"; // Replace with your HiveMQ hostname
    public string username = "Rudra_123"; // Replace with HiveMQ username
    public string password = "RudrA@123"; // Replace with HiveMQ password

    [Header("Unity UI")]
    public Text moistureText;  // Text UI to display moisture value
    public Image dialFill;     // Image representing the dial fill (for the moisture gauge)
    public Text pumpStatusText; // Text UI to display the pump status (ON/OFF)

    private IMqttClient mqttClient;

    async void Start()
    {
        // Ensure the UnityMainThreadDispatcher is initialized.
        if (UnityMainThreadDispatcher.Instance() == null)
        {
            GameObject dispatcherObject = new GameObject("MainThreadDispatcher");
            dispatcherObject.AddComponent<UnityMainThreadDispatcher>();
            //DontDestroyOnLoad(dispatcherObject); // Consider if you need this dispatcher to persist across scene loads
        }
        await ConnectToMqttBroker();
    }

    private async Task ConnectToMqttBroker()
    {
        var factory = new MqttFactory();
        mqttClient = factory.CreateMqttClient();

        var options = new MqttClientOptionsBuilder()
          .WithClientId("UnityClient_" + Guid.NewGuid())
          .WithTcpServer(brokerHost, 8883)
          .WithCredentials(username, password)
          .WithTls(new MqttClientOptionsBuilderTlsParameters
          {
              UseTls = true,
              AllowUntrustedCertificates = false,
              IgnoreCertificateChainErrors = false,
              IgnoreCertificateRevocationErrors = false
          })
          .WithCleanSession()
          .Build();

        mqttClient.UseConnectedHandler(async e =>
        {
            Debug.Log("Connected to MQTT broker.");
            await mqttClient.SubscribeAsync("esp32/soilMoisture");
            Debug.Log("Subscribed to topic: esp32/soilMoisture");

            // Subscribe to pump control topic
            await mqttClient.SubscribeAsync("esp32/pump/control");
            Debug.Log("Subscribed to topic: esp32/pump/control");
        });

        mqttClient.UseDisconnectedHandler(e =>
        {
            Debug.Log("Disconnected from MQTT broker.");
            // Consider adding a reconnect mechanism here.  For example:
            Task.Run(async () => {
                await Task.Delay(5000); // Wait 5 seconds before reconnecting
                await ConnectToMqttBroker();
            });
        });

        mqttClient.UseApplicationMessageReceivedHandler(e =>
        {
            string topic = e.ApplicationMessage.Topic;
            string payload = Encoding.UTF8.GetString(e.ApplicationMessage.Payload);

            Debug.Log($"Received -> Topic: {topic}, Payload: {payload}");

            if (topic == "esp32/soilMoisture")
            {
                if (float.TryParse(payload, out float moistureValue))
                {
                    Debug.Log($"Soil Moisture: {moistureValue}%");

                    // Use UnityMainThreadDispatcher to safely update the UI from the MQTT callback
                    UnityMainThreadDispatcher.Instance().Enqueue(() =>
                    {
                        UpdateMoistureUI(moistureValue);
                    });
                }
                else
                {
                    Debug.LogWarning("Invalid moisture payload: " + payload);
                }
            }

            // Check if the message is for the pump control topic
            if (topic == "esp32/pump/control")
            {
                if (payload == "PUMP_ON")
                {
                    Debug.Log("Pump is ON");

                    // Use UnityMainThreadDispatcher to update the pump status on the UI
                    UnityMainThreadDispatcher.Instance().Enqueue(() =>
                    {
                        UpdatePumpStatus("Pump is ON");
                    });
                }
                else if (payload == "PUMP_OFF")
                {
                    Debug.Log("Pump is OFF");

                    // Use UnityMainThreadDispatcher to update the pump status on the UI
                    UnityMainThreadDispatcher.Instance().Enqueue(() =>
                    {
                        UpdatePumpStatus("Pump is OFF");
                    });
                }
                else
                {
                    Debug.LogWarning("Unknown pump control message: " + payload);
                }
            }
        });

        try
        {
            await mqttClient.ConnectAsync(options);
        }
        catch (Exception ex)
        {
            Debug.LogError("MQTT connection failed: " + ex.Message);
            // Consider adding retry logic here.
        }
    }

    private void UpdateMoistureUI(float value)
    {
        // Update the Moisture text
        if (moistureText != null)
        {
            moistureText.text = $"{value:F1}%";  // Update percentage text
        }

        // Update the Dial Fill
        if (dialFill != null)
        {
            // Fill Amount ranges from 0 to 1 (0% to 100%)
            dialFill.fillAmount = value / 100f;  // Normalize to 0 to 1 range
        }
    }

    private void UpdatePumpStatus(string status)
    {
        // Update the Pump status text
        if (pumpStatusText != null)
        {
            pumpStatusText.text = status;
        }
    }

    private void OnDestroy()
    {
        if (mqttClient != null)
        {
            if (mqttClient.IsConnected)
            {
                mqttClient.DisconnectAsync().Wait(); // Use Wait() for synchronous disconnect on application quit
            }
            mqttClient.Dispose();
            mqttClient = null;
        }
    }
}
