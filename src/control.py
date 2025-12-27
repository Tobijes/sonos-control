import asyncio
import json
import os
from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo

import httpx

from src.auth import SonosAuth
from src.models import Group, Favorite, Player
from src.constants import STATE_PLAYING

# SONOS API URLs
CONTROL_URL_BASE = "https://api.ws.sonos.com/control/api/v1"

ALLOW_WRITE = bool(os.getenv("ALLOW_WRITE", False))
print("Allow write to Sonos", ALLOW_WRITE, flush=True)

RADIO_FAVORITE_NAME = os.getenv("RADIO_FAVORITE_NAME", "DR P3")
print("Radio favorite name", RADIO_FAVORITE_NAME, flush=True)

SLEEP_ROOM_NAME = os.getenv("SLEEP_ROOM_NAME", "Soveværelse")
print("Sleep room name", SLEEP_ROOM_NAME, flush=True)

SLEEP_VOLUME = int(os.getenv("SLEEP_VOLUME", "2"))
print("Sleep volume", SLEEP_VOLUME, flush=True)

SLEEP_SECONDS = int(os.getenv("SLEEP_SECONDS", "900"))
print("Sleep seconds", SLEEP_SECONDS, flush=True)

SLEEP_FAVORITE_NAME = os.getenv("SLEEP_FAVORITE_NAME", "Relaxed Goodnight Piano for Autumn Nights")
print("Sleep favorite name", SLEEP_FAVORITE_NAME, flush=True)

def millis(delta: timedelta):
    return math.ceil(delta.microseconds/1000)

class SonosControl:
    sonos_auth: SonosAuth
    client: httpx.AsyncClient
    household_id: str = None

    # States (without persistence across restarts)
    last_toggled: datetime = None
    sleep_timer: asyncio.Task = None

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
            except (httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
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
            except (httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
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
            except (httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
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
        
        players = {player["id"]: Player(id=player["id"], name=player["name"]) for player in data["players"]}
        groups = [Group(id=g["id"], name=g["name"], playback_state=g["playbackState"], players=[players[player_id] for player_id in g["playerIds"]]) for g in groups]

        for group in groups:
            data = await self.get_playback_metadata(group)
            if "type" in data["container"]:
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
        self.cancel_sleep_timer()

        groups = await self.get_groups()

        if all(group.playable or not group.controllable for group in groups):
            if self.last_toggled is None or (datetime.now() - self.last_toggled) > timedelta(hours=1):
                await self.group_and_play_favorite(groups)
            else:
                await self.group_with_largest_and_play(groups)
        else:
            await self.pause_all_groups(groups)

        self.last_toggled = datetime.now()

    async def group_and_play_favorite(self, groups=None):
        """Runs *Play Procedure*: Group all speakers, set volume to 15% or 20% based on hour, start playback"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return

        favorites_coroutine = self.get_favorites()
        if groups is None:
            groups = await self.get_groups()

        # Set all players volume to standard level. Kick off REST calls and await later  
        volume = self.get_preferred_volume()  
        print(f"Setting players volume to {volume}", flush=True)
        players = [player for group in groups for player in group.players]
        set_player_volume_coroutines = [self.set_player_volume(player=player, volume=volume) for player in players]

        # Gather all players in a single group, reuse if possible
        if len(groups) == 0:
            group = await self.create_group(players=players)
            print("Created group:", group, flush=True)
        elif len(groups) == 1:
            group = groups[0]
            print("Reusing group:", group, flush=True)
        else:
            sizes = [len(group.players) for group in groups]
            group_idx = sizes.index(max(sizes))
            group = groups[group_idx]
            await self.set_group_members(group, players)
            print("Unifying to group:", group, flush=True)
        
        # Await all volumes to be set (call started off earlier)
        await asyncio.gather(*set_player_volume_coroutines)

        # Load first favorite onto the group with playback if possible, otherwise just play
        favorites: list[Favorite] = await favorites_coroutine
        favorites = [favorite for  favorite in favorites if favorite.name == RADIO_FAVORITE_NAME]
        if len(favorites) > 0:
            # Load favorite onto group
            await self.play_favorite(group=group, favorite_id=favorites[0].favorite_id)
        else:
            # Play last played content
            print("No favorite found, just playing", flush=True)
            await self.play_group(group)
    
    async def group_with_largest_and_play(self, groups=None):
        """Runs *Play Procedure*: Group all speakers, set volume , start playback"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return

        if groups is None:
            groups = await self.get_groups()

        # Set all players volume to standard level. Kick off REST calls and await later    
        volume = self.get_preferred_volume()
        print(f"Setting players volume to {volume}", flush=True)
        players = [player for group in groups for player in group.players]
        set_player_volume_coroutines = [self.set_player_volume(player=player, volume=volume) for player in players]

        # Gather all players in a single group, reuse if possible
        if len(groups) == 0:
            group = await self.create_group(players=players)
            print("Created group:", group, flush=True)
        elif len(groups) == 1:
            group = groups[0]
            print("Reusing group:", group, flush=True)
        else:
            sizes = [len(group.players) for group in groups]
            group_idx = sizes.index(max(sizes))
            group = groups[group_idx]
            await self.set_group_members(group, players)
            print("Unifying to group:", group, flush=True)

        # Await all volumes to be set (call started off earlier)
        await asyncio.gather(*set_player_volume_coroutines)

        await self.play_group(group)
        
    async def run_sleep_procedure(self, groups=None):
        """Runs *Sleep Procedure*: Pause all groups, create group with sleep room, set volume to 1, play sleep favorite"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return

        favorites_coroutine = self.get_favorites()
        if groups is None:
            groups = await self.get_groups()

        await self.pause_all_groups(groups)

        players = set([player for group in groups for player in group.players])
        sleep_players = [player for player in players if player.name == SLEEP_ROOM_NAME]

        if len(sleep_players) == 0:
            raise Exception("No sleep players found")
        
        group = await self.create_group(players=sleep_players)
        set_player_volume_coroutines = [self.set_player_volume(player=player, volume=SLEEP_VOLUME) for player in sleep_players]
        
        # Await all volumes to be set (call started off earlier)
        await asyncio.gather(*set_player_volume_coroutines)

        favorites: list[Favorite] = await favorites_coroutine
        favorites = [favorite for favorite in favorites if favorite.name == SLEEP_FAVORITE_NAME]
        if len(favorites) > 0:
            # Load favorite onto group
            await self.play_favorite(group, favorite_id=favorites[0].favorite_id)
        else:
            print("No favorite found, not playing", flush=True)
        # Start sleep timer to pause after 15 minutes
        self.cancel_sleep_timer()
        self.sleep_timer = asyncio.create_task(self.sleep_timer_task())

    async def sleep_timer_task(self, seconds=900):
        print("Sleeping for", seconds, "seconds", flush=True)
        await asyncio.sleep(seconds)  # Sleep for 30 minutes
        print("Sleep timer elapsed, pausing all groups", flush=True)
        await self.pause_all_groups()

    def cancel_sleep_timer(self):
        if self.sleep_timer:
            print("Cancelling existing sleep timer", flush=True)
            self.sleep_timer.cancel()
            self.sleep_timer = None

    async def pause_all_groups(self, groups=None):
        """Pauses all groups"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return
        if groups is None:
            groups = await self.get_groups()
        await asyncio.gather(*[self.pause_group(group) for group in groups])

    async def play_all_groups(self, groups=None):
        """Plays all groups (without changing configuration)"""
        # Check if allowed to change real settings
        if not ALLOW_WRITE:
            return
        if groups is None:
            groups = await self.get_groups()
        await asyncio.gather(*[self.play_group(group) for group in groups])

    async def create_group(self, players: list[Player]):
        """Groups the **players** into a single group"""
        household_id = await self.get_household_id()
        new_group_json = await self.post(
            url=f"{CONTROL_URL_BASE}/households/{household_id}/groups/createGroup",
            json={ "playerIds": [player.id for player in players] }
        )
        g = new_group_json["group"]
        group = Group(id=g["id"], name=g["name"], playback_state="", players=players)
        return group

    async def set_group_members(self, group: Group, players: list[Player]):
        if not ALLOW_WRITE:
            return
        await self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/groups/setGroupMembers",
            json={ "playerIds": [player.id for player in players] }
        )

    async def pause_group(self, group: Group):
        """Pause a single group"""
        # Check that we don't command pause on a HDMI playing session
        if not group.pausable:
            return 
        await self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/playback/pause"
        )

    async def play_group(self, group: Group):
        """Play a single group"""
        # Check that we don't command play on a HDMI playing session
        if not group.playable:
            return 
        await self.post(
            url=f"{CONTROL_URL_BASE}/groups/{group.id}/playback/play"
        )
        
    async def set_player_volume(self, player: Player, volume: int):
        """Sets the volume on an individual player"""
        await self.post(
            url=f"{CONTROL_URL_BASE}/players/{player.id}/playerVolume",
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

    def get_preferred_volume(self):
        # Determine volume level based on time
        now = datetime.now(ZoneInfo("Europe/Copenhagen"))
        volume = 20 if now.hour >= 8 and now.hour < 22 else 15

        return volume