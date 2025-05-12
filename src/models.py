import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

@dataclass
class Authorization:
    access_token: str
    refresh_token: str
    expires_at: datetime
    token_type: str
    scope: str

    @classmethod
    def from_api(cls, data: dict) -> 'Authorization':
        expires_in = int(data.get("expires_in"))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return cls(
            access_token=data.get('access_token'),
            refresh_token=data.get('refresh_token'),
            token_type=data.get('token_type'),
            scope=data.get("scope"),
            expires_at=expires_at
        )
    
    @classmethod
    def from_file(cls: 'Authorization', data: dict) -> 'Authorization':
        expires_at = datetime.fromisoformat(data.get("expires_at"))
        return cls(
            access_token=data.get('access_token'),
            refresh_token=data.get('refresh_token'),
            token_type=data.get('token_type'),
            scope=data.get("scope"),
            expires_at=expires_at
        )


    def to_json_str(self) -> str:
        json_str = json.dumps(asdict(self), cls=DateTimeEncoder)
        return json_str

@dataclass
class Group:
    id: str
    name: str
    playback_state: str
    player_ids: list[str]
    playback_type: str = None

@dataclass
class Favorite:
    favorite_id: str
    name: str
    description: str    

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