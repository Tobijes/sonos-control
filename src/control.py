import os

import httpx

from src.auth import SonosAuth
from src.models import Group, Favorite

# SONOS API URLs
CONTROL_URL_BASE = "https://api.ws.sonos.com/control/api/v1/"

ALLOW_WRITE = bool(os.getenv("ALLOW_WRITE", False))
print("Allow write to Sonos", ALLOW_WRITE, flush=True)

# SONOS CONSTANTS
STATE_PLAYING = "PLAYBACK_STATE_PLAYING"
STATE_IDLE= "PLAYBACK_STATE_IDLE"

class SonosControl:
    sonos_auth: SonosAuth
    household_id: str = None

    def __init__(self, sonos_auth):
        self.sonos_auth = sonos_auth

    def get(self, url: str, params=None):
        """ Standardized GET REST call"""
        headers = self.sonos_auth.get_authorized_headers()
        response = httpx.get(url, headers=headers, params=params)

        if response.status_code != 200:
            raise Exception(f"Got {response.status_code=} with error: {response.text}\n {url=} {params=}")
        
        return response.json()    
    
    def post(self, url: str, json=None):
        """ Standardized POST REST call"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return
        
        headers = self.sonos_auth.get_authorized_headers()
        response = httpx.post(url, headers=headers, json=json)

        if response.status_code != 200:
            raise Exception(f"Got {response.status_code=} with error: {response.text}\n {url=} {json=}")
        
        return response.json()

    def get_household_id(self):
        """Get the Household ID using the auth headers. Cached if possible"""
        if self.household_id is not None:
            return self.household_id

        data = self.get(url=f"{CONTROL_URL_BASE}/households", params={
            "connectedOnly": True
        })
        
        households = data["households"]
        if len(households) == 0:
            return None
        
        self.household_id = households[0]["id"]
        return self.household_id

    def get_groups(self) -> list[Group]:   
        """Get the Groups"""
        household_id = self.get_household_id()
        data = self.get(url=f"{CONTROL_URL_BASE}/households/{household_id}/groups")

        groups = data["groups"]
        if len(groups) == 0:
            return None
        
        groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"], player_ids=g["playerIds"]) for g in groups]
        print(groups, flush=True)

        return groups
    
    def get_favorites(self) -> list: 
        """Get the Favorites"""  
        household_id = self.get_household_id()
        data = self.get(url=f"{CONTROL_URL_BASE}/households/{household_id}/favorites")
        
        favorites = data["items"]
        if len(favorites) == 0:
            return None

        favorites = [Favorite(favorite_id=f["id"], name=f["name"], description=f["description"]) for f in favorites]

        return favorites

    def group_toggle(self):
        """Toggles between playing and pausing based on previous state"""
        groups = self.get_groups()
    
        if any(group.playback_state == STATE_PLAYING for group in groups):
            self.pause_all_groups()
        else:
            self.play_all_groups()

    def play_all_groups(self):
        """Runs *Play Procedure*: Group all speakers, set volume to 15%, start playback"""
        groups = self.get_groups()
        favorites = self.get_favorites()

        # Set all players volume to standard level
        player_ids = [player_id for group in groups for player_id in group.player_ids]
        for player_id in player_ids:
            self.set_player_volume(player_id=player_id, volume=15)
            
        # Create a single group of the players
        group = self.create_group(player_ids=player_ids)
        print(group, flush=True)

        # Load first favorite onto the group with playback if possible, otherwise just play
        if len(favorites) > 0:
            # Load favorite onto group
            self.play_favorite(group=group, favorite_id=favorites[0].favorite_id)
        else:
            # Play last played content
            self.play_group(group)
        
        
    def pause_all_groups(self):
        """Pauses all groups"""
        groups = self.get_groups()

        for group in groups:
            if group.playback_state == STATE_PLAYING:
                self.pause_group(group)


    def create_group(self, player_ids: list[str]):
        """Groups the **player_ids** into a single group"""
        household_id = self.get_household_id()
        new_group_json = self.post(
            url=f"{CONTROL_URL_BASE}/households/{household_id}/groups/createGroup",
            json={ "playerIds": player_ids }
        )
        g = new_group_json["group"]
        group = Group(id=g["id"], name=g["name"], playback_state="", player_ids=g["playerIds"])
        return group

    def pause_group(self, group: Group):
        """Pause a single group"""
        self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/playback/pause"
        )

    def play_group(self, group: Group):
        """Play a single group"""
        self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/playback/play"
        )
        
    def set_player_volume(self, player_id: str, volume: int):
        """Sets the volume on an individual player"""
        self.post(
            url=f"{CONTROL_URL_BASE}/players/{player_id}/playerVolume",
            json={ "volume": volume }
        )

    def play_favorite(self, group: Group, favorite_id: str):
        """Play a favorite on a group"""
        self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/favorites",
            json={
                "favoriteId": favorite_id,
                "playOnCompletion": True
            }
        )
