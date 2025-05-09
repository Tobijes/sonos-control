import os
import asyncio
from typing import Annotated
import base64

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from src.models import APIHandledError
from src.auth import SonosAuth
from src.control import SonosControl

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tasks
    loop = asyncio.get_running_loop()
    loop.create_task(sonos_auth.task_refresh_authorization())
    yield
    # Run cleanup
    # ...

load_dotenv()
SERVICE_PASSWORD = os.getenv("SERVICE_PASSWORD")

sonos_auth = SonosAuth()
sonos_control = SonosControl(sonos_auth)
app = FastAPI(lifespan=lifespan)

def check_permission(method, path, auth):
    # The following paths are always allowed:
    if method == 'GET' and path in ['/', '/docs', '/openapi.json', '/favicon.ico']:
        return True
    
    # Parse auth header and check scheme, username and password
    scheme, data = (auth or ' ').split(' ', 1)
    
    if scheme != 'Basic': 
        return False
    
    username, password = base64.b64decode(data).decode().split(':', 1)

    if username == '' and password == SERVICE_PASSWORD:
        return True


@app.middleware("http")
async def check_authentication(request: Request, call_next):
    auth = request.headers.get('Authorization')        
    if not check_permission(request.method, request.url.path, auth):
        return JSONResponse(None, 401, {"WWW-Authenticate": "Basic"})
    return await call_next(request)

@app.get("/", tags=["Speakers"])
async def root():
    household_id = sonos_control.get_household_id()
    groups = sonos_control.get_groups()
    favorites = sonos_control.get_favorites()

    return {
        "message": "Welcome to the Sonos API Service", 
        "household_id":household_id, 
        "groups": groups,
        "favorites": favorites 
    }

@app.get("/login", summary="Endpoint for authenticating with Sonos account", tags=["Auth"])
async def login():
    auth_url = sonos_auth.get_oauth_link()
    return RedirectResponse(auth_url)

@app.get("/callback", summary="Endpoint for receiving the authorization code from Sonos after login", tags=["Auth"])
async def callback(request: Request):
    # Handle the callback from Sonos after the user authorizes the app
    authorization_code = request.query_params.get('code')
    state = request.query_params.get("state")

    sonos_auth.get_access_token(authorization_code, state)

    sonos_control.get_household_id()

    return RedirectResponse("/")

@app.get("/play", summary="Endpoint for triggering Play action: Group all speakers, set volume to 15%, start playback", tags=["Speakers"])
async def play():
    sonos_control.play_all_groups()
    return "Ok"

@app.get("/pause", summary="Endpoint for triggering Pause action: Pause each group", tags=["Speakers"])
async def pause():
    sonos_control.pause_all_groups()
    return "Ok"

@app.get("/toggle", summary="Endpoint for triggering play or pause depending on state", tags=["Speakers"])
async def toggle():
    sonos_control.group_toggle()
    return "Ok"

@app.exception_handler(APIHandledError)
async def not_authorized_handler(request: Request, exc: APIHandledError):
    return JSONResponse(status_code=exc.status_code, content={"message": exc.message})
