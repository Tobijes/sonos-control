import os
import json
from pathlib import Path
import base64
from dataclasses import asdict
from datetime import datetime, timedelta
import asyncio
import urllib

import httpx
from fastapi import FastAPI
from dotenv import load_dotenv

from src.models import Authorization, DateTimeEncoder
from src.models import  NotAuthorizedError

# SONOS API URLs
ACCESS_URL = "https://api.sonos.com/login/v3/oauth/access"

# Save paths
AUTHORIZATION_FILE = Path("authorization.json")

# Get environment variables
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
print("Redirect URL", REDIRECT_URI)

def get_credentials_headers():
    credentials = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}"
    }
    return headers

def get_authorized_headers(app: FastAPI):
    if app.state.authorization is None:
        raise NotAuthorizedError
    
    authorization: Authorization = app.state.authorization
    headers = {
        "Authorization": f"Bearer {authorization.access_token}"
    }
    return headers

def get_oauth_link():
    # Construct the Sonos authorization URL
    auth_url = (
        f"https://api.sonos.com/login/v3/oauth?client_id={CLIENT_ID}"
        f"&response_type=code&state=testState&scope=playback-control-all&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    )

    return auth_url

def get_access_token(authorization_code):
     # Step 2: Exchange the authorization code for an access token
    token_data = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': REDIRECT_URI
    }

    headers = get_credentials_headers()

    token_response = httpx.post(ACCESS_URL, data=token_data, headers=headers)
    print(token_response.text)

    token_json = token_response.json()
    authorization = Authorization(**token_json)

    save_authorization(authorization)

    return authorization

def save_authorization(authorization: Authorization):
    json_str = json.dumps(asdict(authorization), cls=DateTimeEncoder)
    with open(AUTHORIZATION_FILE, "w") as f:
        f.write(json_str)
    print("Authorization saved")

def load_authorization(validate=True):
    if not AUTHORIZATION_FILE.is_file():
        return None
    
    with open(AUTHORIZATION_FILE, "r") as f:
        json_str = f.read()
    json_dict = json.loads(json_str)
    json_dict["last_refreshed"] = datetime.fromisoformat(json_dict["last_refreshed"])
    authorization = Authorization(**json_dict)

    if validate:
        if authorization.last_refreshed + timedelta(seconds=authorization.expires_in) < datetime.now():
            print("Authorization loaded, but invalid")
            return None
        
    print("Authorization loaded from file")
    return authorization

async def task_refresh_authorization(app: FastAPI):
    while True:
        if app.state.authorization is None:
            await asyncio.sleep(5)
            continue
        authorization: Authorization = app.state.authorization
        refresh_time = authorization.last_refreshed + timedelta(seconds=authorization.expires_in, hours=-1)
        sleep_time = refresh_time - datetime.now()
        print(f"Sleeping for {sleep_time.seconds} seconds")
        await asyncio.sleep(sleep_time.seconds)

        print("Refreshing token...")
        headers = get_credentials_headers()
        url_params = {
            "grant_type": "refresh_token",
            "refresh_token" : authorization.refresh_token
        }

        token_response = httpx.post(ACCESS_URL, params=url_params, headers=headers)
        print(token_response.text)

