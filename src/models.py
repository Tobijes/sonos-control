import json
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class Authorization:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    scope: str
    last_refreshed: datetime = datetime.now()

@dataclass
class Group:
    id: str
    name: str
    playback_state: str

class NotAuthorizedError(Exception):
    pass

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)