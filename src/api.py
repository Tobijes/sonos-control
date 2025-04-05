import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager

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

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    household_id = get_household_id(app)
    groups = get_groups(app, household_id)
    return {
        "message": "Welcome to the Sonos API Service", 
        "household_id":household_id, 
        "groups": groups
    }

@app.get("/login")
async def login():
    auth_url = get_oauth_link()
    return RedirectResponse(auth_url)

@app.get("/callback")
async def callback(request: Request):
    # Handle the callback from Sonos after the user authorizes the app
    authorization_code = request.query_params.get('code')

    authorization = get_access_token(authorization_code)
    app.state.authorization = authorization

    get_household_id(app)
    return RedirectResponse("/")

@app.get("/play")
async def pause():
    
    household_id = get_household_id(app)
    groups: list[Group] = get_groups(app, household_id)

    for group in groups:
        group_play(app, group)

    return "Ok"

@app.get("/pause")
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