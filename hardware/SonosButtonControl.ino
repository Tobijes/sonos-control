#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFiClientSecure.h>

// Button pins
const int BUTTON1_PIN = 12;
const int BUTTON2_PIN = 14;

// Button state tracking variables
unsigned long pressStartTime1 = 0;
unsigned long pressStartTime2 = 0;
const unsigned long MIN_PRESS_TIME = 50; // Minimum time in ms for a valid press
bool button1Pressed = false;
bool button2Pressed = false;

// LED pin for status indication
const int STATUS_LED = 2;

// Configuration variables
String wifiSsid = "";
String wifiPass = "";
String baseUrl = "";
String apiKey = "";

// Storage
Preferences preferences;
bool wifiConnected = false;

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  
  // Initialize button pins as input with pull-up resistors
  pinMode(BUTTON1_PIN, INPUT_PULLUP);
  pinMode(BUTTON2_PIN, INPUT_PULLUP);
  
  // Initialize LED pin
  pinMode(STATUS_LED, OUTPUT);
  digitalWrite(STATUS_LED, LOW);
  
  // Initialize preferences
  preferences.begin("esp32app", false);
  
  // Load saved configurations
  loadConfig();
  
  // Attempt to connect to WiFi if credentials exist
  if (wifiSsid.length() > 0 && wifiPass.length() > 0) {
    connectToWifi();
  }
  
  Serial.println("ESP32 Button Controller initialized");
  Serial.println("Available commands:");
  Serial.println("WIFI_SSID <wifi ssid>");
  Serial.println("WIFI_PASS <wifi password>");
  Serial.println("BASE_URL <api base url>");
  Serial.println("API_KEY <basic auth base64 key>");
  Serial.println("FLASH_RESET");
}

void loop() {
  // Check for serial input
  checkSerialInput();
  
  // Check button press and release
  checkButtonPressAndRelease();
  
  // Quick blink LED if WiFi is not connected
  if (!wifiConnected) {
    digitalWrite(STATUS_LED, millis() % 1000 < 50 ? HIGH : LOW);
  }
}

void loadConfig() {
  wifiSsid = preferences.getString("wifiSsid", "");
  wifiPass = preferences.getString("wifiPass", "");
  baseUrl = preferences.getString("baseUrl", "");
  apiKey = preferences.getString("apiKey", "");
  
  Serial.println("Loaded configuration:");
  Serial.println("WIFI_SSID: " + wifiSsid);
  Serial.println("BASE_URL: " + baseUrl);
  
  Serial.print("API_KEY: ");
  Serial.println(apiKey.length() > 0 ? "[SET]" : "[NOT SET]");
}

void saveConfig() {
  preferences.putString("wifiSsid", wifiSsid);
  preferences.putString("wifiPass", wifiPass);
  preferences.putString("baseUrl", baseUrl);
  preferences.putString("apiKey", apiKey);
  
  Serial.println("Configuration saved");
}

void connectToWifi() {
  if (wifiSsid.length() == 0 || wifiPass.length() == 0) {
    Serial.println("WiFi credentials not set");
    return;
  }
  
  Serial.print("Connecting to WiFi: ");
  Serial.println(wifiSsid);
  
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
    
    // Blink LED during connection attempt
    digitalWrite(STATUS_LED, attempts % 2);
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    wifiConnected = true;
    digitalWrite(STATUS_LED, LOW);
  } else {
    Serial.println("\nFailed to connect to WiFi");
    wifiConnected = false;
  }
}

void checkSerialInput() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    Serial.println("Received command: " + command);
    
    if (command.startsWith("WIFI_SSID ")) {
      wifiSsid = command.substring(10);
      Serial.println("WiFi SSID set to: " + wifiSsid);
      saveConfig();
    } 
    else if (command.startsWith("WIFI_PASS ")) {
      wifiPass = command.substring(10);
      Serial.println("WiFi password set");
      saveConfig();
    } 
    else if (command.startsWith("BASE_URL ")) {
      baseUrl = command.substring(9);
      Serial.println("Base URL set to: " + baseUrl);
      saveConfig();
    } 
    else if (command.startsWith("API_KEY ")) {
      apiKey = command.substring(8);
      Serial.println("API key set");
      saveConfig();
    } 
    else if (command == "FLASH_RESET") {
      resetConfig();
    } 
    else {
      Serial.println("Unknown command: " + command);
    }
    
    // Attempt to connect/reconnect to WiFi if credentials have been set
    if ((command.startsWith("WIFI_SSID ") || command.startsWith("WIFI_PASS ")) &&
        wifiSsid.length() > 0 && wifiPass.length() > 0) {
      connectToWifi();
    }
  }
}

void resetConfig() {
  Serial.println("Resetting all configuration...");
  preferences.clear();
  wifiSsid = "";
  wifiPass = "";
  baseUrl = "";
  apiKey = "";
  
  // Disconnect WiFi
  WiFi.disconnect(true);
  wifiConnected = false;
  
  // Triple blink to indicate reset
  for (int i = 0; i < 3; i++) {
    digitalWrite(STATUS_LED, HIGH);
    delay(100);
    digitalWrite(STATUS_LED, LOW);
    delay(100);
  }
  
  Serial.println("All configuration reset");
}

void checkButtonPressAndRelease() {
  // Read the current button states
  int button1State = digitalRead(BUTTON1_PIN);
  int button2State = digitalRead(BUTTON2_PIN);
  
  // Check button 1 for press
  if (button1State == LOW && !button1Pressed) { // Button is pressed (LOW due to pull-up)
    pressStartTime1 = millis();
    button1Pressed = true;
  }
  
  // Check button 1 for release after minimum press time
  if (button1State == HIGH && button1Pressed) { // Button is released
    if (millis() - pressStartTime1 >= MIN_PRESS_TIME) {
      Serial.println("Button 1 pressed");
      makeApiCall("/play");
    }
    button1Pressed = false;
  }
  
  // Check button 2 for press
  if (button2State == LOW && !button2Pressed) { // Button is pressed (LOW due to pull-up)
    pressStartTime2 = millis();
    button2Pressed = true;
  }
  
  // Check button 2 for release after minimum press time
  if (button2State == HIGH && button2Pressed) { // Button is released
    if (millis() - pressStartTime2 >= MIN_PRESS_TIME) {
      Serial.println("Button 2 pressed");
      makeApiCall("/pause");
    }
    button2Pressed = false;
  }
}

void makeApiCall(String endpoint) {
  if (!wifiConnected || baseUrl.length() == 0) {
    Serial.println("Cannot make API call: WiFi not connected or Base URL not set");
    return;
  }
  
  String url = baseUrl + endpoint;
  Serial.print("Making API call to: ");
  Serial.println(url);
  
  // Check if using HTTPS
  bool isHttps = url.startsWith("https://");
  
  if (isHttps) {
    // Setup for HTTPS
    WiFiClientSecure secureClient;
    // Skip certificate verification (not secure for production)
    secureClient.setInsecure();
    
    HTTPClient https;
    https.begin(secureClient, url);
    
    // Add authorization header if API key is set
    if (apiKey.length() > 0) {
      https.addHeader("Authorization", "Basic " + apiKey);
    }
    
    // Blink LED rapidly during API call
    digitalWrite(STATUS_LED, HIGH);
    
    // Make the GET request
    int httpResponseCode = https.GET();
    
    if (httpResponseCode > 0) {
      String response = https.getString();
      Serial.print("HTTPS Response code: ");
      Serial.println(httpResponseCode);
      Serial.println("Response: " + response);
    } else {
      Serial.print("HTTPS Error code: ");
      Serial.println(httpResponseCode);
    }
    
    digitalWrite(STATUS_LED, LOW);
    https.end();
  } else {
    // Original HTTP code
    HTTPClient http;
    http.begin(url);
    
    // Add authorization header if API key is set
    if (apiKey.length() > 0) {
      http.addHeader("Authorization", "Basic " + apiKey);
    }
    
    // Blink LED rapidly during API call
    digitalWrite(STATUS_LED, HIGH);
    
    // Make the GET request
    int httpResponseCode = http.GET();
    
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("HTTP Response code: ");
      Serial.println(httpResponseCode);
      Serial.println("Response: " + response);
    } else {
      Serial.print("HTTP Error code: ");
      Serial.println(httpResponseCode);
    }
    
    digitalWrite(STATUS_LED, LOW);
    http.end();
  }
}
