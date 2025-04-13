import os

import httpx

from src.auth import SonosAuth
from src.models import Group, Favorite

# SONOS API URLs
CONTROL_URL_BASE = "https://api.ws.sonos.com/control/api/v1/"

ALLOW_WRITE = bool(os.getenv("ALLOW_WRITE", False))
print("Allow write to Sonos", ALLOW_WRITE, flush=True)

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
        
        groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"], player_ids=g["playerIds"]) for g in groups]
        print(groups, flush=True)

        return groups
    
    def get_favorites(self) -> list:   
        headers = self.sonos_auth.get_authorized_headers()

        household_id = self.get_household_id()
        response = httpx.get(f"{CONTROL_URL_BASE}/households/{household_id}/favorites", headers=headers)
        data = response.json()
        print(data)
        favorites = data["items"]
        if len(favorites) == 0:
            return None

        favorites = [Favorite(favorite_id=f["id"], name=f["name"], description=f["description"]) for f in favorites]

        return favorites
    

    def group_play(self):
        headers = self.sonos_auth.get_authorized_headers()
        household_id = self.get_household_id()
        groups: list[Group] = self.get_groups()
        favorites: list[Favorite] = self.get_favorites()

        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return
        
        # Set all players volume to standard level
        player_ids = [player_id for group in groups for player_id in group.player_ids]
        for player_id in player_ids:
            response = httpx.post(f"{CONTROL_URL_BASE}/players/{player_id}/playerVolume", headers=headers, json={
                "volume": 15
            })
            if response.status_code != 200:
                raise Exception("Player Volume API status code:" + str(response.status_code))
            
        # Create a single group of the players
        response = httpx.post(f"{CONTROL_URL_BASE}/households/{household_id}/groups/createGroup", headers=headers, json={
            "playerIds": player_ids
        })
        if response.status_code != 200:
            raise Exception("Groups Create API status code:" + str(response.status_code))
        new_group_json = response.json()
        g = new_group_json["group"]
        group = Group(id=g["id"], name=g["name"], playback_state="", player_ids=g["playerIds"])
        print(group, flush=True)

        # Load first favorite onto the group with playback if possible, otherwise just play
        if len(favorites) > 0:
            # Load favorite onto group
            response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/favorites", headers=headers, json={
                "favoriteId": favorites[0].favorite_id,
                "playOnCompletion": True
            })
            if response.status_code != 200:
                raise Exception("Groups Favorites API status code:" + str(response.status_code))
        else:
            # Activate "play" on all groups
            response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/playback/play", headers=headers)
            
            if response.status_code != 200:
                raise Exception("Playback API status code:" + str(response.status_code))
        
        
    def group_pause(self):
        headers = self.sonos_auth.get_authorized_headers()
        groups: list[Group] = self.get_groups()

        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return

        for group in groups:

            response = httpx.post(f"{CONTROL_URL_BASE}/groups/{group.id}/playback/pause", headers=headers)
            
            if response.status_code != 200:
                raise Exception("Playback API status code:" + str(response.status_code))