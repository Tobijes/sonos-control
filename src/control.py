from fastapi import FastAPI
import httpx

from src.auth import get_authorized_headers
from src.models import Group

# SONOS API URLs
CONTROL_URL_BASE = "https://api.ws.sonos.com/control/api/v1/"

def get_household_id(app: FastAPI):
    if app.state.household_id is not None:
        return app.state.household_id
    
    headers = get_authorized_headers(app)
    
    params = {
        "connectedOnly": True
    }
    response = httpx.get(f"{CONTROL_URL_BASE}/households", params=params, headers=headers)
    data = response.json()
    
    households = data["households"]
    if len(households) == 0:
        return None
    
    household_id = households[0]["id"]
    app.state.household_id = household_id
    return household_id

def get_groups(app: FastAPI, household_id: str) -> list[Group]:   
    headers = get_authorized_headers(app)

    response = httpx.get(f"{CONTROL_URL_BASE}/households/{household_id}/groups", headers=headers)
    data = response.json()
    groups = data["groups"]
    if len(groups) == 0:
        return None
    groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"]) for g in groups]
    print(groups)

    return groups

def group_play(app: FastAPI, group: Group):
    headers = get_authorized_headers(app)
    response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/playback/play", headers=headers)
    
def group_pause(app: FastAPI, group: Group):
    headers = get_authorized_headers(app)
    response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/playback/pause", headers=headers)