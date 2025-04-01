from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
import urllib.parse
import httpx
import base64

import os
from dotenv import load_dotenv

load_dotenv()


app = FastAPI()
app.state.ACCESS_TOKEN = None
# Replace with your actual client ID and redirect URI
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

@app.get("/")
async def root():
    return {"message": "Welcome to the Sonos OAuth Redirect App"}

@app.get("/login")
async def login():
    # Construct the Sonos authorization URL
    auth_url = (
        f"https://api.sonos.com/login/v3/oauth?client_id={CLIENT_ID}"
        f"&response_type=code&state=testState&scope=playback-control-all&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    )
    return RedirectResponse(auth_url)

@app.get("/callback")
async def callback(request: Request):
    # Handle the callback from Sonos after the user authorizes the app
    authorization_code = request.query_params.get('code')

    # Step 2: Exchange the authorization code for an access token
    token_url = "https://api.sonos.com/login/v3/oauth/access"
    token_data = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': REDIRECT_URI
    }

    authorization_secret = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode()).decode()

    headers = {
        "Authorization": f"Basic {authorization_secret}",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8"
    }
    print(headers)

    token_response = httpx.post(token_url, data=token_data, headers=headers)
    print(token_response.text)

    token_json = token_response.json()
    access_token = token_json['access_token']
    request.app.state.ACCESS_TOKEN = access_token

@app.get("/play")
async def play(request: Request):
    if request.app.state.ACCESS_TOKEN is None:
        return "No Access Token"
    access_token = request.app.state.ACCESS_TOKEN
    headers = {
        "Authorization" : "Bearer " + access_token
    }

    play_url = "https://api.ws.sonos.com/control/api/v1/groups/<groupId>/playback/play"
    response = httpx.post(play_url, headers=headers)
    return response.text