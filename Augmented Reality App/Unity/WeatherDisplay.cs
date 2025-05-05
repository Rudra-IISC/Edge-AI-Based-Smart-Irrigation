using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using TMPro;

public class WeatherDisplay : MonoBehaviour
{
    public TMP_Text weatherText;
    [Tooltip("City to fetch weather for")]
    public string city = "Bangalore";
    [Tooltip("Your OpenWeatherMap API key")]
    public string apiKey = "9813dbed0947722bd5a944487eeebb62"; // Replace with your actual API key
    [Tooltip("Units for temperature (metric, imperial)")]
    public string units = "metric";
    [Tooltip("Text to display while loading")]
    public string loadingText = "Fetching Weather...";
    [Tooltip("Number of retry attempts on failure")]
    public int retryAttempts = 3;
    [Tooltip("Delay between retry attempts in seconds")]
    public float retryDelay = 2f;

    private const string ApiBaseUrl = "https://api.openweathermap.org/data/2.5/weather";
    private const string QueryParam = "q";
    private const string AppIdParam = "appid";
    private const string UnitsParam = "units";

    private int _currentRetry = 0;

    void Start()
    {
        FetchWeatherWithLoading();
    }

    private void FetchWeatherWithLoading()
    {
        if (weatherText != null)
        {
            weatherText.text = loadingText;
            weatherText.color = Color.black; // Reset color
        }
        StartCoroutine(FetchWeather());
    }

    IEnumerator FetchWeather()
    {
        string url = $"{ApiBaseUrl}?{QueryParam}={city}&{AppIdParam}={apiKey}&{UnitsParam}={units}";

        using (UnityWebRequest request = UnityWebRequest.Get(url))
        {
            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"Weather fetch failed for {city}: {request.error}");
                if (_currentRetry < retryAttempts)
                {
                    _currentRetry++;
                    if (weatherText != null)
                    {
                        weatherText.text = $"⚠️ Fetch failed. Retrying in {retryDelay}s... ({_currentRetry}/{retryAttempts})";
                        weatherText.color = Color.yellow;
                    }
                    yield return new WaitForSeconds(retryDelay);
                    StartCoroutine(FetchWeather()); // Retry
                }
                else
                {
                    if (weatherText != null)
                    {
                        weatherText.text = $"⚠️ Could not fetch weather after {retryAttempts} retries:\n{request.error}";
                        weatherText.color = Color.red;
                    }
                }
                yield break; // Exit the coroutine on final failure
            }
            else
            {
                _currentRetry = 0; // Reset retry count on success
                var json = request.downloadHandler.text;
                try
                {
                    var data = JsonUtility.FromJson<WeatherWrapper>(json);
                    UpdateWeatherDisplay(data);
                }
                catch (Exception e)
                {
                    Debug.LogError($"Error parsing weather JSON: {e.Message}\nRaw JSON: {json}");
                    if (weatherText != null)
                    {
                        weatherText.text = "⚠️ Error parsing weather data.";
                        weatherText.color = Color.red;
                    }
                }
            }
        }
    }

    void UpdateWeatherDisplay(WeatherWrapper data)
    {
        // Time conversion
        int timezoneOffset = data.timezone;
        DateTime localTime = UnixTimeToLocal(data.dt, timezoneOffset);
        DateTime sunrise = UnixTimeToLocal(data.sys.sunrise, timezoneOffset);
        DateTime sunset = UnixTimeToLocal(data.sys.sunset, timezoneOffset);

        // Emoji and color selection using a dictionary for better organization
        string emoji = "🌤";
        Color color = Color.black;
        string main = data.weather[0].main.ToLower();

        var weatherEmojis = new Dictionary<string, (string, Color)>
        {
            {"rain", ("🌧", Color.blue)},
            {"storm", ("⛈", Color.red)},
            {"thunder", ("⛈", Color.red)},
            {"cloud", ("☁️", Color.gray)},
            {"clear", ("☀️", new Color(1f, 0.64f, 0f))},
            {"snow", ("❄️", Color.cyan)},
            {"mist", ("🌫", Color.gray)},
            {"fog", ("🌫", Color.gray)}
        };

        foreach (var pair in weatherEmojis)
        {
            if (main.Contains(pair.Key))
            {
                emoji = pair.Value.Item1;
                color = pair.Value.Item2;
                break; // Exit on the first match
            }
        }

        string description = data.weather[0].description;

        string text = $"{emoji} {description}\n" +
                      $"🌡️ Temp: {data.main.temp}°C\n" +
                      $"💧 Humidity: {data.main.humidity}%\n" +
                      $"🔽 Pressure: {data.main.pressure} hPa\n" +
                      $"🌬 Wind: {data.wind.speed} m/s\n\n" +
                      $"📅 Date: {localTime:yyyy-MM-dd}\n" +
                      $"⏰ Time: {localTime:HH:mm:ss}\n" +
                      $"🌅 Sunrise: {sunrise:HH:mm:ss}\n" +
                      $"🌇 Sunset: {sunset:HH:mm:ss}";

        if (weatherText != null)
        {
            weatherText.text = text;
            weatherText.color = color;
        }
    }

    DateTime UnixTimeToLocal(long unixTime, int timezoneOffset)
    {
        DateTime utc = DateTimeOffset.FromUnixTimeSeconds(unixTime).UtcDateTime;
        return utc.AddSeconds(timezoneOffset);
    }
}

[System.Serializable]
public class WeatherWrapper
{
    public Weather[] weather;
    public Main main;
    public Wind wind;
    public Sys sys;
    public long dt;
    public int timezone;
}

[System.Serializable]
public class Weather
{
    public string main;
    public string description;
}

[System.Serializable]
public class Main
{
    public float temp;
    public int humidity;
    public int pressure;
}

[System.Serializable]
public class Wind
{
    public float speed;
}

[System.Serializable]
public class Sys
{
    public long sunrise;
    public long sunset;
}