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

class APIHandledError(Exception):
    status_code: int 
    message: str

class NotAuthorizedError(APIHandledError):
    status_code = 401
    message = "Missing authorization, go to /login"

class OAuthStateMismatchError(APIHandledError):
    status_code = 403
    message = "The state returned from the OAuth process did not match source state"

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()

        return json.JSONEncoder.default(self, o)