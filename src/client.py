import asyncio
import json
import os
from datetime import datetime, timedelta
import math

import httpx

from src.auth import SonosAuth

def millis(delta: timedelta):
    return math.ceil(delta.microseconds/1000)

ALLOW_WRITE = bool(os.getenv("ALLOW_WRITE", False))
print("Allow write to Sonos", ALLOW_WRITE, flush=True)

class WriteNotAllowedError(Exception):
    pass

class SonosClient:
    sonos_auth: SonosAuth
    client: httpx.AsyncClient

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
        if not ALLOW_WRITE:
            raise WriteNotAllowedError()
        
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
        if not ALLOW_WRITE:
            raise WriteNotAllowedError()

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