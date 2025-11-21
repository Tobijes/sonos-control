import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import src.constants as c

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

@dataclass(frozen=True)
class Player:
    id: str
    name: str

@dataclass
class Group:
    id: str
    name: str
    playback_state: str
    players: list[Player]
    playback_type: str = None

    @property
    def playable(self) -> bool:
        return self.controllable and self.playback_state in [c.STATE_IDLE, c.STATE_PAUSED] 
    
    @property
    def pausable(self) -> bool:
        return self.controllable and self.playback_state in [c.STATE_PLAYING] 
    
    @property
    def controllable(self) -> bool:
        return self.playback_type != c.PLAYBACK_STATE_HDMI

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