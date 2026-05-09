import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.core.config import get_settings
from app.models import Role


class JWTAuth:
    def __init__(self):
        self.settings = get_settings()
        self.secret_key = "foodbridge-secret-key-for-jwt-2026"
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 60 * 24

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def create_session_token(self, uid: str, email: str, role: Role) -> str:
        return self.create_access_token({
            "sub": uid,
            "email": email,
            "role": role.value
        })


jwt_auth = JWTAuth()
