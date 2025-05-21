import asyncio
import os
from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo

import httpx

from src.auth import SonosAuth
from src.models import Group, Favorite

# SONOS API URLs
CONTROL_URL_BASE = "https://api.ws.sonos.com/control/api/v1"

ALLOW_WRITE = bool(os.getenv("ALLOW_WRITE", False))
print("Allow write to Sonos", ALLOW_WRITE, flush=True)

# SONOS CONSTANTS
STATE_PLAYING = "PLAYBACK_STATE_PLAYING"
STATE_IDLE= "PLAYBACK_STATE_IDLE"
STATE_PAUSED = "PLAYBACK_STATE_PAUSED"

PLAYBACK_STATE_HDMI = "linein.homeTheater.hdmi"
PLAYBACK_STATE_STATION = "station"
PLAYBACK_STATE_SPOTIFY = ""

def millis(delta: timedelta):
    return math.ceil(delta.microseconds/1000)

class SonosControl:
    sonos_auth: SonosAuth
    client: httpx.AsyncClient
    household_id: str = None

    def __init__(self, sonos_auth, client):
        self.sonos_auth = sonos_auth
        self.client = client

    async def get(self, url: str, params=None, tries=3):
        """ Standardized GET REST call """
        headers = self.sonos_auth.get_authorized_headers()
        for i in range(tries):
            try:
                response = await self.client.get(url, headers=headers, params=params)
                print(f"GET {millis(response.elapsed)}ms {url=}", flush=True)
                break
            except httpx.ConnectTimeout as exc:
                print(f"GET {url=} failed. Retrying...", flush=True)
                if i == tries-1: # No more tries
                    raise Exception(f"GET {url=} Exceeded retries") from exc
                await asyncio.sleep((i+1)*(50/1000)) # Specify milliseconds
                
        if response.status_code != 200:
            raise Exception(f"Got {response.status_code=} with error: {response.text}\n {url=} {params=}")
        
        return response.json()    
    
    async def post(self, url: str, json=None, tries=3):
        """ Standardized POST REST call """
        headers = self.sonos_auth.get_authorized_headers()

        for i in range(tries):
            try:
                response = await self.client.post(url, headers=headers, json=json)
                print(f"POST {millis(response.elapsed)}ms {url=}", flush=True)
                break
            except httpx.ConnectTimeout as exc:
                print(f"POST {url=} failed. Retrying...", flush=True)
                if i == tries-1: # No more tries
                    raise Exception(f"POST {url=} Exceeded retries") from exc
                await asyncio.sleep((i+1)*(50/1000))

        if response.status_code != 200:
            raise Exception(f"Got {response.status_code=} with error: {response.text}\n {url=} {json=}")
        
        return response.json()
    
    async def delete(self, url: str, params=None, tries=3):
        """ Standardized DELETE REST call """
        headers = self.sonos_auth.get_authorized_headers()

        for i in range(tries):
            try:
                response = await self.client.delete(url, headers=headers, params=params)
                print(f"DELETE {millis(response.elapsed)}ms {url=}", flush=True)
                break
            except httpx.ConnectTimeout as exc:
                print(f"DELETE {url=} failed. Retrying...", flush=True)
                if i == tries-1: # No more tries
                    raise Exception(f"DELETE {url=} Exceeded retries") from exc
                await asyncio.sleep((i+1)*(50/1000))

        if response.status_code != 200:
            raise Exception(f"Got {response.status_code=} with error: {response.text}\n {url=} {params=}")
        
        return response.json()

    async def get_household_id(self):
        """Get the Household ID using the auth headers. Cached if possible"""
        if self.household_id is not None:
            return self.household_id

        data = await self.get(url=f"{CONTROL_URL_BASE}/households", params={
            "connectedOnly": True
        })
        
        households = data["households"]
        if len(households) == 0:
            return None
        
        self.household_id = households[0]["id"]
        return self.household_id

    async def get_groups(self) -> list[Group]:   
        """Get the Groups"""
        household_id = await self.get_household_id()
        data = await self.get(url=f"{CONTROL_URL_BASE}/households/{household_id}/groups")

        groups = data["groups"]
        if len(groups) == 0:
            return None
        
        groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"], player_ids=g["playerIds"]) for g in groups]

        for group in groups:
            if group.playback_state == STATE_PLAYING:
                data = await self.get_playback_metadata(group)
                group.playback_type = data["container"]["type"]

        return groups

    async def get_playback_metadata(self, group: Group) -> dict:   
        """Get the Group's metadata and playback state"""
        data = await self.get(url=f"{CONTROL_URL_BASE}/groups/{group.id}/playbackMetadata")
        return data

    
    async def get_favorites(self) -> list: 
        """Get the Favorites"""  
        household_id = await self.get_household_id()
        data = await self.get(url=f"{CONTROL_URL_BASE}/households/{household_id}/favorites")
        
        favorites = data["items"]
        if len(favorites) == 0:
            return None

        favorites = [Favorite(favorite_id=f["id"], name=f["name"], description=f["description"]) for f in favorites]

        return favorites

    async def group_toggle(self):
        """Toggles between playing and pausing based on previous state"""
        groups = await self.get_groups()

        if all(group.playback_state in [STATE_IDLE, STATE_PAUSED] or (group.playback_state == STATE_PLAYING and group.playback_type == PLAYBACK_STATE_HDMI) for group in groups):
            await self.play_all_groups(groups)
        else:
            await self.pause_all_groups(groups)

    async def play_all_groups(self, groups=None):
        """Runs *Play Procedure*: Group all speakers, set volume to 15% or 20% based on hour, start playback"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return
        favorites_coroutine = self.get_favorites()
        if groups is None:
            groups = await self.get_groups()

        # Determine volume level based on time
        now = datetime.now(ZoneInfo("Europe/Copenhagen"))
        volume = 20 if now.hour >= 8 and now.hour < 22 else 15

        # Set all players volume to standard level. Kick off REST calls and await later    
        player_ids = [player_id for group in groups for player_id in group.player_ids]
        print(f"Setting players volume to {volume}", flush=True)
        set_player_volume_coroutines = [self.set_player_volume(player_id=player_id, volume=volume) for player_id in player_ids]

        # Gather all players in a single group. If already a single group, just reuse.
        if len(groups) > 1:
            group = await self.create_group(player_ids=player_ids)
            print("Created group:", group, flush=True)
        else:
            group = groups[0]
            print("Reusing group:", group, flush=True)
        
        # Await all volumes to be set (call started off earlier)
        await asyncio.gather(*set_player_volume_coroutines)

        # Load first favorite onto the group with playback if possible, otherwise just play
        favorites = await favorites_coroutine
        if len(favorites) > 0:
            # Load favorite onto group
            await self.play_favorite(group=group, favorite_id=favorites[0].favorite_id)
        else:
            # Play last played content
            await self.play_group(group)
        
        
    async def pause_all_groups(self, groups=None):
        """Pauses all groups"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return
        if groups is None:
            groups = await self.get_groups()
        await asyncio.gather(*[self.pause_group(group) for group in groups if group.playback_state == STATE_PLAYING])

    async def create_group(self, player_ids: list[str]):
        """Groups the **player_ids** into a single group"""
        household_id = await self.get_household_id()
        new_group_json = await self.post(
            url=f"{CONTROL_URL_BASE}/households/{household_id}/groups/createGroup",
            json={ "playerIds": player_ids }
        )
        g = new_group_json["group"]
        group = Group(id=g["id"], name=g["name"], playback_state="", player_ids=g["playerIds"])
        return group

    async def pause_group(self, group: Group):
        """Pause a single group"""
        # Check that we don't command pause on a HDMI playing session
        if group.playback_type == PLAYBACK_STATE_HDMI:
            return 
        await self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/playback/pause"
        )

    async def play_group(self, group: Group):
        """Play a single group"""
        # Check that we don't command play on a HDMI playing session
        if group.playback_type == PLAYBACK_STATE_HDMI:
            return 
        await self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/playback/play"
        )
        
    async def set_player_volume(self, player_id: str, volume: int):
        """Sets the volume on an individual player"""
        await self.post(
            url=f"{CONTROL_URL_BASE}/players/{player_id}/playerVolume",
            json={ "volume": volume }
        )

    async def play_favorite(self, group: Group, favorite_id: str):
        """Play a favorite on a group"""
        await self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/favorites",
            json={
                "favoriteId": favorite_id,
                "playOnCompletion": True
            }
        )
