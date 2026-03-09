"""
FastAPI backend for MOROZ VPN Bot web admin panel.

Provides:
- JWT-like token auth for admin user (linked to Telegram admin)
- CRUD endpoints for users, keys, messages
- Traffic statistics endpoints (using TrafficManager)
- Settings management via AppConfig / ConfigManager
"""

from datetime import datetime, timedelta
import logging
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import JWTError, jwt

from config import WEB_SERVER_DOMAIN, WEB_ADMIN_PORT, get_env
from config_manager import ConfigManager
from database import (
    init_db,
    get_db_session,
    User,
    VPNKey,
    UserMessage,
    AppConfig,
)
from traffic_manager import TrafficManager


logger = logging.getLogger(__name__)


# SECRET_KEY берём из .env; дефолт только для dev
SECRET_KEY = get_env("FASTAPI_SECRET_KEY", get_env("SECRET_KEY", "dev-secret-key"))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


# ──────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    telegram_id: Optional[int]
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    phone_number: Optional[str]
    is_active: bool
    max_keys: int
    is_admin: bool

    class Config:
        orm_mode = True


class VPNKeyOut(BaseModel):
    id: int
    user_id: int
    key_name: str
    client_ip: Optional[str]
    is_active: bool

    class Config:
        orm_mode = True


class MessageOut(BaseModel):
    id: int
    user_id: int
    message_type: str
    message_text: str
    admin_reply: Optional[str]
    status: str
    created_at: datetime
    replied_at: Optional[datetime]

    class Config:
        orm_mode = True


class SettingsItem(BaseModel):
    key: str
    value: Optional[str]
    description: Optional[str]
    is_secret: bool = False
    category: str = "general"


class SettingsUpdate(BaseModel):
    items: List[SettingsItem]


# ──────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_admin_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    with get_db_session() as session:
        user = (
            session.query(User)
            .filter(User.telegram_id == telegram_id, User.is_admin.is_(True))
            .first()
        )
        return user


async def get_current_admin(token: str) -> User:
    """Dependency to ensure the caller is an admin."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        telegram_id: int = payload.get("telegram_id")
        if telegram_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_admin_user_by_telegram_id(telegram_id)
    if user is None:
        raise credentials_exception
    return user


# ──────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────


app = FastAPI(title="MOROZ VPN Bot Web Admin")

# Разрешаем запросы только с реального адреса веб-панели и локальной разработки
allowed_origins = {
    f"http://{WEB_SERVER_DOMAIN}:{WEB_ADMIN_PORT}",
    f"https://{WEB_SERVER_DOMAIN}:{WEB_ADMIN_PORT}",
    "http://localhost:8889",
    "http://127.0.0.1:8889",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    init_db()
    logger.info("Web admin backend started (domain=%s)", WEB_SERVER_DOMAIN)


# ──────────────────────────────────────────────
# Auth endpoints
# ──────────────────────────────────────────────


class TokenRequest(BaseModel):
    telegram_id: int


@app.post("/api/auth/token", response_model=Token)
def generate_token(payload: TokenRequest):
    """Generate access token for admin based on telegram_id."""
    user = get_admin_user_by_telegram_id(payload.telegram_id)
    if not user:
        raise HTTPException(status_code=403, detail="Not an admin user")

    token = create_access_token({"telegram_id": payload.telegram_id})
    return Token(access_token=token)


@app.get("/api/auth/verify")
def verify_token(token: str):
    """Verify token validity."""
    user = get_admin_user_by_telegram_id(
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("telegram_id", 0)
    )
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return {"ok": True, "telegram_id": user.telegram_id}


# ──────────────────────────────────────────────
# Users & keys
# ──────────────────────────────────────────────


@app.get("/api/users", response_model=List[UserOut])
def list_users(admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        users = session.query(User).all()
        return users


@app.get("/api/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_deleted = True
    return {"ok": True}


@app.get("/api/keys", response_model=List[VPNKeyOut])
def list_keys(admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        keys = session.query(VPNKey).all()
        return keys


@app.delete("/api/keys/{key_id}")
def delete_key(key_id: int, admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        key = session.query(VPNKey).filter(VPNKey.id == key_id).first()
        if not key:
            raise HTTPException(status_code=404, detail="Key not found")
        key.is_active = False
    # Full removal from server is handled by bot / admin tools
    return {"ok": True}


# ──────────────────────────────────────────────
# Messages
# ──────────────────────────────────────────────


@app.get("/api/messages", response_model=List[MessageOut])
def list_messages(admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        msgs = (
            session.query(UserMessage)
            .order_by(UserMessage.created_at.desc())
            .all()
        )
        return msgs


@app.get("/api/messages/{msg_id}", response_model=MessageOut)
def get_message(msg_id: int, admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        msg = session.query(UserMessage).filter(UserMessage.id == msg_id).first()
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        return msg


# ──────────────────────────────────────────────
# Traffic / stats
# ──────────────────────────────────────────────


@app.get("/api/traffic/overview")
def traffic_overview(admin: User = Depends(get_current_admin)):
    return TrafficManager.get_traffic_overview()


@app.get("/api/traffic/chart")
def traffic_chart(period: str = "day", admin: User = Depends(get_current_admin)):
    return TrafficManager.get_traffic_chart_data(period)


@app.get("/api/traffic/users")
def traffic_users(admin: User = Depends(get_current_admin)):
    return TrafficManager.get_all_users_traffic()


@app.get("/api/traffic/user/{user_id}")
def traffic_user(user_id: int, admin: User = Depends(get_current_admin)):
    return TrafficManager.get_user_traffic(user_id, period="month")


@app.get("/api/stats")
def global_stats(admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        total_users = session.query(User).count()
        active_users = session.query(User).filter(User.is_active.is_(True)).count()
        admins = session.query(User).filter(User.is_admin.is_(True)).count()
        total_keys = session.query(VPNKey).count()
    return {
        "total_users": total_users,
        "active_users": active_users,
        "admins": admins,
        "total_keys": total_keys,
    }


# ──────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────


@app.get("/api/settings", response_model=List[SettingsItem])
def get_settings(admin: User = Depends(get_current_admin)):
    with get_db_session() as session:
        entries = session.query(AppConfig).all()
        items: List[SettingsItem] = []
        for e in entries:
            value = e.value
            if e.is_secret and value:
                # Mask secret value
                value = value[:3] + "…" + value[-2:] if len(value) > 5 else "***"
            items.append(
                SettingsItem(
                    key=e.key,
                    value=value,
                    description=e.description,
                    is_secret=e.is_secret,
                    category=e.category,
                )
            )
        return items


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate, admin: User = Depends(get_current_admin)):
    for item in payload.items:
        ConfigManager.set(
            key=item.key,
            value=item.value or "",
            description=item.description,
            is_secret=item.is_secret,
            category=item.category,
        )
    return {"ok": True}


@app.get("/api/settings/auth-bypass")
def get_auth_bypass(admin: User = Depends(get_current_admin)):
    enabled = ConfigManager.get_bool("auth_bypass_enabled", False)
    until = ConfigManager.get("auth_bypass_until")
    max_keys = ConfigManager.get_auth_bypass_max_keys()
    return {
        "enabled": enabled,
        "until": until,
        "max_keys": max_keys,
    }


class AuthBypassUpdate(BaseModel):
    enabled: bool
    hours: Optional[int] = None
    max_keys: Optional[int] = None


@app.put("/api/settings/auth-bypass")
def update_auth_bypass(payload: AuthBypassUpdate, admin: User = Depends(get_current_admin)):
    if payload.enabled:
        hours = payload.hours or 24
        until_dt = datetime.utcnow() + timedelta(hours=hours)
        ConfigManager.set(
            "auth_bypass_enabled",
            "true",
            description="Включён ли режим открытого доступа",
            category="access",
        )
        ConfigManager.set(
            "auth_bypass_until",
            until_dt.isoformat(),
            description="До какого момента действует режим открытого доступа",
            category="access",
        )
        if payload.max_keys is not None:
            ConfigManager.set(
                "auth_bypass_max_keys",
                str(payload.max_keys),
                description="Сколько ключей выдаётся при авто-активации",
                category="access",
            )
    else:
        ConfigManager.set(
            "auth_bypass_enabled",
            "false",
            description="Включён ли режим открытого доступа",
            category="access",
        )
    return {"ok": True}

