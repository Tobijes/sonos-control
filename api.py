import base64
import os
import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
import urllib.parse
import httpx

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

from dotenv import load_dotenv

@dataclass
class Authorization:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    scope: str
    last_refreshed: datetime = datetime.now()

@dataclass
class Group:
    id: str
    name: str
    playback_state: str

# SONOS API URLs
ACCESS_URL = "https://api.sonos.com/login/v3/oauth/access"
HOUSEHOLDS_URL = "https://api.ws.sonos.com/control/api/v1/households"
GROUPS_URL = "https://api.ws.sonos.com/control/api/v1/groups"

# Save paths
AUTHORIZATION_FILE = Path("authorization.json")

# Get environment variables
load_dotenv()
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run initialzation
    app.state.authorization = load_authorization()
    print(app.state.authorization)
    app.state.household_id = None
    loop = asyncio.get_running_loop()
    loop.create_task(task_refresh_authorization())
    yield
    # Run cleanup
    # ...

app = FastAPI(lifespan=lifespan)

def get_credentials_headers():
    credentials = base64.b64encode((CLIENT_ID + ":" + CLIENT_SECRET).encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}"
    }
    return headers

def get_authorized_headers():
    if app.state.authorization is None:
        raise NotAuthorizedError
    
    authorization: Authorization = app.state.authorization
    headers = {
        "Authorization": f"Bearer {authorization.access_token}"
    }
    return headers

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)

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

async def task_refresh_authorization():
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


def get_household_id():
    if app.state.household_id is not None:
        return app.state.household_id
    
    headers = get_authorized_headers()
    
    params = {
        "connectedOnly": True
    }
    response = httpx.get(HOUSEHOLDS_URL, params=params, headers=headers)
    data = response.json()
    
    households = data["households"]
    if len(households) == 0:
        return None
    
    household_id = households[0]["id"]
    app.state.household_id = household_id
    return household_id

def get_groups(household_id) -> list[Group]:   
    headers = get_authorized_headers()

    response = httpx.get(f"{HOUSEHOLDS_URL}/{household_id}/groups", headers=headers)
    data = response.json()
    groups = data["groups"]
    if len(groups) == 0:
        return None
    groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"]) for g in groups]
    print(groups)

    return groups

@app.get("/")
async def root():
    household_id = get_household_id()
    groups = get_groups(household_id)
    return {
        "message": "Welcome to the Sonos API Service", 
        "household_id":household_id, 
        "groups": groups
    }

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
    token_data = {
        'grant_type': 'authorization_code',
        'code': authorization_code,
        'redirect_uri': REDIRECT_URI
    }

    headers = get_credentials_headers()

    token_response = httpx.post(ACCESS_URL, data=token_data, headers=headers)
    print(token_response.text)

    token_json = token_response.json()
    request.app.state.authorization = Authorization(**token_json)
    print(request.app.state.authorization)
    save_authorization(request.app.state.authorization)

    household_id = get_household_id()
    return RedirectResponse("/")

@app.get("/play")
async def play(request: Request):
    pass

@app.get("/pause")
async def pause():
    
    household_id = get_household_id()
    groups: list[Group] = get_groups(household_id)

    headers = get_authorized_headers()
    for group in groups:
        pause_url = f"{GROUPS_URL}/{group.id}/playback/pause"
        response = httpx.post(pause_url, headers=headers)

    return "Ok"

class NotAuthorizedError(Exception):
    pass

@app.exception_handler(NotAuthorizedError)
async def not_authorized_handler(request: Request, exc: NotAuthorizedError):
    return JSONResponse(
        status_code=401,
        content={"message": f"Missing authorization, go to /login"},
    )