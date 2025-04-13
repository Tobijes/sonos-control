import os

from fastapi import FastAPI
import httpx

from src.auth import SonosAuth
from src.models import Group

# SONOS API URLs
CONTROL_URL_BASE = "https://api.ws.sonos.com/control/api/v1/"

ALLOW_WRITE = bool(os.getenv("ALLOW_WRITE", False))
print("Allow write to Sonos", ALLOW_WRITE)

class SonosControl:
    sonos_auth: SonosAuth
    household_id: str = None

    def __init__(self, sonos_auth):
        self.sonos_auth = sonos_auth


    def get_household_id(self):
        if self.household_id is not None:
            return self.household_id
        
        headers = self.sonos_auth.get_authorized_headers()
        
        params = {
            "connectedOnly": True
        }
        response = httpx.get(f"{CONTROL_URL_BASE}/households", params=params, headers=headers)
        data = response.json()
        
        households = data["households"]
        if len(households) == 0:
            return None
        
        self.household_id = households[0]["id"]
        return self.household_id

    def get_groups(self) -> list[Group]:   
        headers = self.sonos_auth.get_authorized_headers()

        household_id = self.get_household_id()
        response = httpx.get(f"{CONTROL_URL_BASE}/households/{household_id}/groups", headers=headers)
        data = response.json()
        groups = data["groups"]
        if len(groups) == 0:
            return None
        groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"]) for g in groups]
        print(groups)

        return groups

    def group_play(self):
        headers = self.sonos_auth.get_authorized_headers()
        groups: list[Group] = self.get_groups()

        for group in groups:
            if not ALLOW_WRITE:
                continue
            response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/playback/play", headers=headers)
            
            if response.status_code != 200:
                raise Exception("Playback API status code:" + str(response.status_code))
        
        
    def group_pause(self):
        headers = self.sonos_auth.get_authorized_headers()
        groups: list[Group] = self.get_groups()

        for group in groups:
            if not ALLOW_WRITE:
                continue
            response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/playback/pause", headers=headers)
            
            if response.status_code != 200:
                raise Exception("Playback API status code:" + str(response.status_code))