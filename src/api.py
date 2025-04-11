import os
import asyncio
from typing import Annotated
import base64

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from src.models import Group, NotAuthorizedError
from src.auth import get_access_token, get_oauth_link, load_authorization, task_refresh_authorization
from src.control import get_groups, get_household_id, group_pause, group_play

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run initialzation
    # Set state variables
    app.state.authorization = load_authorization()
    app.state.household_id = None
    # Create tasks
    loop = asyncio.get_running_loop()
    loop.create_task(task_refresh_authorization(app))
    yield
    # Run cleanup
    # ...

load_dotenv()
SERVICE_PASSWORD = os.getenv("SERVICE_PASSWORD")
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

@app.get("/")
async def root():
    household_id = get_household_id(app)
    groups = get_groups(app, household_id)
    return {
        "message": "Welcome to the Sonos API Service", 
        "household_id":household_id, 
        "groups": groups
    }

@app.get("/login", summary="Endpoint for authenticating with Sonos account")
async def login():
    auth_url = get_oauth_link()
    return RedirectResponse(auth_url)

@app.get("/callback", summary="Endpoint for receiving the authorization code from Sonos after login")
async def callback(request: Request):
    # Handle the callback from Sonos after the user authorizes the app
    authorization_code = request.query_params.get('code')

    authorization = get_access_token(authorization_code)
    app.state.authorization = authorization

    get_household_id(app)
    return RedirectResponse("/")

@app.get("/play", summary="Endpoint for triggering Play action: Group all speakers, set volume to 15%, start radio")
async def pause():
    
    household_id = get_household_id(app)
    groups: list[Group] = get_groups(app, household_id)

    for group in groups:
        group_play(app, group)

    return "Ok"

@app.get("/pause", summary="Endpoint for triggering Pause action: Pause each group")
async def pause():
    
    household_id = get_household_id(app)
    groups: list[Group] = get_groups(app, household_id)

    for group in groups:
        group_pause(app, group)

    return "Ok"

@app.exception_handler(NotAuthorizedError)
async def not_authorized_handler(request: Request, exc: NotAuthorizedError):
    return JSONResponse(
        status_code=401,
        content={"message": f"Missing authorization, go to /login"},
    )