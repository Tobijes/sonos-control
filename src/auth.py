import os
import json
from pathlib import Path
import base64
from datetime import datetime, timedelta, timezone
import asyncio
import urllib
from secrets import token_urlsafe

import httpx

from src.models import Authorization
from src.models import  NotAuthorizedError, OAuthStateMismatchError

# SONOS API URLs
ACCESS_URL = "https://api.sonos.com/login/v3/oauth/access"

# Save paths
AUTHORIZATION_FILE = Path("data/authorization.json")

# Get environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
print("Redirect URL", REDIRECT_URI, flush=True)

class SonosAuth():
    authorization: Authorization = None
    last_oath_link_state: str = None

    def __init__(self):
        AUTHORIZATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.load_authorization()

    def get_credentials_headers(self):
        credentials = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}"
        }
        return headers

    def get_authorized_headers(self):
        if self.authorization is None:
            raise NotAuthorizedError
        
        headers = {
            "Authorization": f"Bearer {self.authorization.access_token}"
        }
        return headers

    def get_oauth_link(self):
        # Construct the Sonos authorization URL
        self.last_oath_link_state = token_urlsafe(16)
        auth_url = (
            f"https://api.sonos.com/login/v3/oauth?client_id={CLIENT_ID}"
            f"&response_type=code"
            f"&state={self.last_oath_link_state}"
            f"&scope=playback-control-all"
            f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        )

        return auth_url

    def get_access_token(self, authorization_code, state):
        # Validate state
        if state != self.last_oath_link_state:
            raise OAuthStateMismatchError()
        
        # Exchange the authorization code for an access token
        token_data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'redirect_uri': REDIRECT_URI
        }

        headers = self.get_credentials_headers()

        token_response = httpx.post(ACCESS_URL, data=token_data, headers=headers)
        print(token_response.text, flush=True)

        token_json = token_response.json()
        self.authorization = Authorization.from_api(token_json)
        self.save_authorization()


    def save_authorization(self):
        json_str = self.authorization.to_json_str()
        with open(AUTHORIZATION_FILE, "w") as f:
            f.write(json_str)
        print("Authorization saved", flush=True)

    def load_authorization(self):
        if not AUTHORIZATION_FILE.is_file():
            return None
        
        with open(AUTHORIZATION_FILE, "r") as f:
            json_dict = json.load(f)
        
        self.authorization = Authorization.from_file(json_dict)
        print("Authorization loaded from file", flush=True)
        
        self.refresh_token()


    def refresh_token(self):
        print("Refreshing token...", flush=True)
        headers = self.get_credentials_headers()
        url_params = {
            "grant_type": "refresh_token",
            "refresh_token" : self.authorization.refresh_token
        }

        token_response = httpx.post(ACCESS_URL, params=url_params, headers=headers)
        print(token_response.text, flush=True)
        token_json = token_response.json()
        self.authorization = Authorization.from_api(token_json)
        self.save_authorization()


    async def task_refresh_authorization(self):
        while True:
            if self.authorization is None:
                await asyncio.sleep(5)
                continue

            
            refresh_time = self.authorization.expires_at + timedelta(hours=-1)
            now = datetime.now(timezone.utc)
            sleep_time = refresh_time - now
            print(f"Now is {now}, refreshing at {refresh_time}. Sleeping for {sleep_time.seconds} seconds", flush=True)
            await asyncio.sleep(sleep_time.seconds)
            self.refresh_token()

