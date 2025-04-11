# Sonos Control
The purpose of this project is to define custom actions wrt. the Sonos API.

The use case is physical buttons in my house that can trigger actions such as pausing all speakers when leaving the house, or turning them all on when coming home.

## Software 
This is a small web API written in Python using FastAPI. 

The API handles authentication and authorization with the Sonos API, through a Sonos account sign in.

The API is packaged in a Docker container running on a Virtual Private Server, which is accessed through the connected domain.

## Hardware
The hardware client is an ESP32 device that is powered from the wall with buttons that can be pressed. The device is configured when setup with 
- WiFi credentials
- Base url for the API
- The required password for the API 