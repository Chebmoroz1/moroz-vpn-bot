"""FastAPI backend для веб-панели администрирования"""
import os
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
import os
import csv
import io
from datetime import datetime

# Импортируем модули из корня проекта
import sys
root_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_path))

from database import SessionLocal, User, VPNKey, Payment, TrafficStatistics
from sqlalchemy import func, and_
from traffic_manager import traffic_manager
from contacts import contacts_manager
from config import ADMIN_ID, BOT_TOKEN, WEB_SERVER_URL, YMONEY_CLIENT_ID, YMONEY_CLIENT_SECRET, YMONEY_REDIRECT_URI, YMONEY_WALLET
from yoomoney_helper import YooMoneyHelper
from config_manager import config_manager

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = FastAPI(title="VPN Bot Admin Panel", version="1.0.0")

# Настройка CORS для работы с React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Хранилище токенов авторизации (в продакшене использовать Redis или БД)
admin_tokens: Dict[str, Dict] = {}  # token -> {admin_id, expires_at}


# Pydantic модели для API
class TokenRequest(BaseModel):
    telegram_id: Optional[int] = None
    token: Optional[str] = None


class TokenResponse(BaseModel):
    token: str
    expires_at: datetime


class UserResponse(BaseModel):
    id: int
    telegram_id: Optional[int]
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    nickname: Optional[str]
    phone_number: Optional[str]
    is_active: bool
    max_keys: int
    is_admin: bool
    created_at: datetime
    vpn_keys_count: int = 0
    activation_requested: bool = False
    activation_requested_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class VPNKeyResponse(BaseModel):
    id: int
    user_id: int
    key_name: str
    protocol: str
    created_at: datetime
    last_used: Optional[datetime]
    expires_at: Optional[datetime]
    is_active: bool
    client_ip: Optional[str]
    access_type: str
    subscription_period_days: Optional[int]
    purchase_date: Optional[datetime]
    is_test: bool

    class Config:
        from_attributes = True


class TrafficStatsResponse(BaseModel):
    vpn_key_id: int
    key_name: str
    user_id: int
    bytes_received: int
    bytes_sent: int
    bytes_total: int
    last_connection: Optional[datetime]
    connection_ips: List[str]


class ChartDataPoint(BaseModel):
    timestamp: str
    label: str
    received: int
    sent: int
    total: int


class TrafficOverviewResponse(BaseModel):
    monthly_traffic: dict
    active_connections: dict
    chart_data: Dict[str, List[ChartDataPoint]]


class UserTrafficStatResponse(BaseModel):
    user_id: int
    user_name: str
    username: Optional[str]
    nickname: Optional[str]
    is_admin: bool
    total_traffic: int
    received: int
    sent: int
    keys_count: int
    active_keys_count: int
    last_connection: Optional[datetime]


class PaginatedUsersResponse(BaseModel):
    users: List[UserTrafficStatResponse]
    total: int
    page: int
    limit: int
    total_pages: int


class UserKeyStatResponse(BaseModel):
    vpn_key_id: int
    key_name: str
    is_active: bool
    received: int
    sent: int
    total: int
    last_connection: Optional[datetime]
    connection_ips: List[str]
    uptime_seconds: Optional[int]
    client_ip: Optional[str]


class UserKeysResponse(BaseModel):
    user_id: int
    user_name: str
    period: str
    summary: dict
    keys: List[UserKeyStatResponse]


class UserCreateRequest(BaseModel):
    telegram_id: Optional[int] = None
    phone_number: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    nickname: Optional[str] = None
    is_active: bool = True
    max_keys: int = 1


class UserUpdateRequest(BaseModel):
    nickname: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: Optional[bool] = None
    max_keys: Optional[int] = None


# Функция для генерации токена администратора
def generate_admin_token(telegram_id: int, expires_hours: int = 24) -> str:
    """Генерация токена для веб-панели"""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=expires_hours)
    
    admin_tokens[token] = {
        'admin_id': telegram_id,
        'expires_at': expires_at
    }
    
    logger.info(f"Generated admin token for telegram_id: {telegram_id}, expires: {expires_at}")
    return token


# Функция для проверки токена
def verify_token(token: str) -> Optional[int]:
    """Проверка токена и возврат admin_id если валиден"""
    if token not in admin_tokens:
        return None
    
    token_data = admin_tokens[token]
    
    # Проверяем срок действия
    if datetime.now() > token_data['expires_at']:
        del admin_tokens[token]
        return None
    
    return token_data['admin_id']


# Dependency для получения сессии БД
def get_db():
    """Получение сессии БД"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Dependency для проверки авторизации
def get_current_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Получение текущего администратора по токену"""
    # Получаем токен из query параметра или заголовка
    token = request.query_params.get("token") or request.headers.get("X-Token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token not provided"
        )
    
    admin_id = verify_token(token)
    if not admin_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Проверяем, что пользователь существует и является администратором
    admin_user = db.query(User).filter(User.telegram_id == admin_id).first()
    if not admin_user or not admin_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    return admin_user


# Настройка статических файлов для React frontend
FRONTEND_BUILD_DIR = Path(__file__).parent.parent / "frontend" / "build"
if FRONTEND_BUILD_DIR.exists():
    # Раздаем статические файлы (JS, CSS, images и т.д.)
    app.mount("/static", StaticFiles(directory=str(FRONTEND_BUILD_DIR / "static")), name="static")
    
    # Корневой эндпоинт для React frontend
    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Главная страница - React frontend"""
        index_file = FRONTEND_BUILD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "VPN Bot Admin Panel API", "docs": "/docs"}
    
    # Fallback для React Router - все остальные маршруты должны возвращать index.html
    # ВАЖНО: Этот маршрут должен быть определен ПОСЛЕ всех API endpoints!
else:
    # Если frontend не собран, возвращаем JSON
    @app.get("/")
    async def root():
        """Главная страница - API info (frontend не собран)"""
        return {
            "message": "VPN Bot Admin Panel API",
            "docs": "/docs",
            "note": "React frontend not built. Run 'cd web_admin/frontend && npm install && npm run build'"
        }


@app.post("/api/auth/token", response_model=TokenResponse)
async def generate_token(request: TokenRequest, db: Session = Depends(get_db)):
    """Генерация токена для веб-панели (должен вызываться из Telegram бота)"""
    telegram_id = request.telegram_id
    
    if not telegram_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="telegram_id is required"
        )
    
    # Проверяем, что пользователь существует и является администратором
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user or not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only admins can generate tokens."
        )
    
    token = generate_admin_token(telegram_id)
    expires_at = admin_tokens[token]['expires_at']
    
    return TokenResponse(token=token, expires_at=expires_at)


@app.get("/api/auth/verify")
async def verify_auth(admin: User = Depends(get_current_admin)):
    """Проверка токена"""
    return {
        "valid": True,
        "admin": {
            "id": admin.id,
            "telegram_id": admin.telegram_id,
            "username": admin.username,
            "first_name": admin.first_name
        }
    }


@app.get("/api/users", response_model=List[UserResponse])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    activation_requests: bool = False,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение списка пользователей"""
    query = db.query(User)
    
    # Если запрашиваются только пользователи с запросами на активацию
    if activation_requests:
        query = query.filter(User.activation_requested == True, User.is_active == False)
    else:
        # Исключаем удаленных пользователей
        query = query.filter(User.is_deleted == False)
    
    users = query.offset(skip).limit(limit).all()
    
    result = []
    for user in users:
        # Подсчитываем количество активных ключей
        vpn_keys_count = db.query(VPNKey).filter(
            VPNKey.user_id == user.id,
            VPNKey.is_active == True
        ).count()
        
        user_dict = {
            **user.__dict__,
            'vpn_keys_count': vpn_keys_count
        }
        # Убираем внутренние атрибуты SQLAlchemy
        user_dict.pop('_sa_instance_state', None)
        result.append(UserResponse(**user_dict))
    
    return result


@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение информации о пользователе"""
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Подсчитываем количество активных ключей
    vpn_keys_count = db.query(VPNKey).filter(
        VPNKey.user_id == user.id,
        VPNKey.is_active == True
    ).count()
    
    user_dict = {
        **user.__dict__,
        'vpn_keys_count': vpn_keys_count
    }
    user_dict.pop('_sa_instance_state', None)
    
    return UserResponse(**user_dict)


@app.get("/api/traffic", response_model=List[TrafficStatsResponse])
async def get_traffic_stats(
    user_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение статистики трафика"""
    from datetime import date as date_type
    
    # Синхронизируем статистику с WireGuard перед получением
    traffic_manager.sync_traffic_stats()
    
    # Определяем период (по умолчанию - текущий месяц)
    if not start_date:
        today = date_type.today()
        start_date_obj = date_type(today.year, today.month, 1)
    else:
        start_date_obj = datetime.fromisoformat(start_date).date()
    
    if not end_date:
        end_date_obj = date_type.today()
    else:
        end_date_obj = datetime.fromisoformat(end_date).date()
    
    # Получаем статистику
    stats = traffic_manager.get_traffic_stats_by_period(
        start_date_obj,
        end_date_obj,
        user_id=user_id
    )
    
    # Форматируем ответ
    result = []
    for stat in stats:
        # Получаем информацию о ключе
        vpn_key = db.query(VPNKey).filter(VPNKey.id == stat['vpn_key_id']).first()
        if vpn_key:
            result.append(TrafficStatsResponse(
                vpn_key_id=stat['vpn_key_id'],
                key_name=vpn_key.key_name,
                user_id=stat['user_id'],
                bytes_received=stat['bytes_received'],
                bytes_sent=stat['bytes_sent'],
                bytes_total=stat['bytes_total'],
                last_connection=stat['last_connection'],
                connection_ips=stat.get('connection_ips', [])
            ))
    
    return result


@app.get("/api/traffic/overview", response_model=TrafficOverviewResponse)
async def get_traffic_overview(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение общей информации для верхнего блока"""
    # Синхронизируем статистику с WireGuard
    traffic_manager.sync_traffic_stats()
    
    # Получаем трафик за месяц
    monthly_traffic = traffic_manager.get_monthly_traffic()
    
    # Получаем количество активных подключений
    active_count = traffic_manager.get_active_connections_count()
    
    # Получаем общее количество ключей для расчета процента
    total_keys = db.query(VPNKey).filter(VPNKey.is_active == True).count()
    active_percentage = (active_count / total_keys * 100) if total_keys > 0 else 0
    
    # Определяем статус нагрузки
    if active_percentage < 50:
        status = 'normal'
    elif active_percentage < 80:
        status = 'high'
    else:
        status = 'critical'
    
    # Получаем данные для графиков (без фильтрации - общий трафик)
    chart_data_6h = traffic_manager.get_chart_data('6hours')
    chart_data_day = traffic_manager.get_chart_data('day')
    chart_data_week = traffic_manager.get_chart_data('week')
    chart_data_month = traffic_manager.get_chart_data('month')
    
    # Преобразуем данные для графиков
    chart_data_dict = {
        '6hours': [ChartDataPoint(**item) for item in chart_data_6h],
        'day': [ChartDataPoint(**item) for item in chart_data_day],
        'week': [ChartDataPoint(**item) for item in chart_data_week],
        'month': [ChartDataPoint(**item) for item in chart_data_month]
    }
    
    return TrafficOverviewResponse(
        monthly_traffic=monthly_traffic,
        active_connections={
            'count': active_count,
            'percentage': round(active_percentage, 1),
            'status': status
        },
        chart_data=chart_data_dict
    )


@app.get("/api/traffic/users", response_model=PaginatedUsersResponse)
async def get_traffic_users(
    period: str = "month",
    search: Optional[str] = None,
    sort: str = "traffic_desc",
    page: int = 1,
    limit: int = 20,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение списка пользователей с трафиком за период"""
    # Синхронизируем статистику с WireGuard
    traffic_manager.sync_traffic_stats()
    
    # Получаем статистику по пользователям
    result = traffic_manager.get_users_traffic_stats(
        period=period,
        search=search,
        sort=sort,
        page=page,
        limit=limit
    )
    
    # Преобразуем в response models
    users = [UserTrafficStatResponse(**user) for user in result['users']]
    
    return PaginatedUsersResponse(
        users=users,
        total=result['total'],
        page=result['page'],
        limit=result['limit'],
        total_pages=result['total_pages']
    )


@app.get("/api/traffic/users/{user_id}/keys", response_model=UserKeysResponse)
async def get_user_keys_traffic(
    user_id: int,
    period: str = "month",
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение детальной статистики по ключам пользователя"""
    # Синхронизируем статистику с WireGuard
    traffic_manager.sync_traffic_stats()
    
    # Получаем детальную статистику
    result = traffic_manager.get_user_keys_traffic(user_id=user_id, period=period)
    
    if not result:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    
    # Преобразуем ключи в response models
    keys = [UserKeyStatResponse(**key) for key in result['keys']]
    
    return UserKeysResponse(
        user_id=result['user_id'],
        user_name=result['user_name'],
        period=result['period'],
        summary=result['summary'],
        keys=keys
    )


@app.get("/api/traffic/chart", response_model=Dict[str, List[ChartDataPoint]])
async def get_traffic_chart(
    period: str = "6hours",
    vpn_key_id: Optional[int] = None,
    user_id: Optional[int] = None,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение данных для графика трафика с возможностью фильтрации по ключу или пользователю"""
    # Получаем данные для графика (snapshots уже собираются автоматически каждые 15 минут)
    chart_data = traffic_manager.get_chart_data(
        period=period,
        vpn_key_id=vpn_key_id,
        user_id=user_id
    )
    
    return {
        period: [ChartDataPoint(**item) for item in chart_data]
    }


@app.get("/api/keys", response_model=List[VPNKeyResponse])
async def get_keys(
    user_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение списка ключей"""
    query = db.query(VPNKey)
    
    if user_id:
        query = query.filter(VPNKey.user_id == user_id)
    
    keys = query.offset(skip).limit(limit).all()
    
    result = []
    for key in keys:
        key_dict = {**key.__dict__}
        key_dict.pop('_sa_instance_state', None)
        result.append(VPNKeyResponse(**key_dict))
    
    return result


@app.put("/api/keys/{key_id}/activate")
async def activate_key(
    key_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Активация ключа"""
    vpn_key = db.query(VPNKey).filter(VPNKey.id == key_id).first()
    if not vpn_key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    vpn_key.is_active = True
    db.commit()
    
    return {"success": True, "message": "Key activated"}


@app.put("/api/keys/{key_id}/deactivate")
async def deactivate_key(
    key_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Деактивация ключа"""
    vpn_key = db.query(VPNKey).filter(VPNKey.id == key_id).first()
    if not vpn_key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    vpn_key.is_active = False
    db.commit()
    
    return {"success": True, "message": "Key deactivated"}


@app.delete("/api/keys/{key_id}")
async def delete_key(
    key_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Удаление ключа"""
    from vpn_manager import vpn_manager
    
    vpn_key = db.query(VPNKey).filter(VPNKey.id == key_id).first()
    if not vpn_key:
        raise HTTPException(status_code=404, detail="Key not found")
    
    try:
        # Удаляем ключ из WireGuard (передаем public_key и key_name)
        vpn_manager.delete_vpn_key(vpn_key.public_key, vpn_key.key_name)
    except Exception as e:
        logger.error(f"Error deleting key from WireGuard: {e}")
    
    # Удаляем из БД
    db.delete(vpn_key)
    db.commit()
    
    return {"success": True, "message": "Key deleted"}


@app.post("/api/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Создание нового пользователя"""
    # Проверяем, что указан хотя бы один из параметров: telegram_id, phone_number или username
    if not user_data.telegram_id and not user_data.phone_number and not user_data.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of telegram_id, phone_number, or username is required"
        )
    
    # Проверяем уникальность по telegram_id
    if user_data.telegram_id:
        existing = db.query(User).filter(User.telegram_id == user_data.telegram_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this telegram_id already exists"
            )
    
    # Нормализуем номер телефона, если указан, и проверяем уникальность
    normalized_phone = None
    if user_data.phone_number:
        normalized_phone = contacts_manager._normalize_phone(user_data.phone_number)
        existing = db.query(User).filter(User.phone_number == normalized_phone).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this phone_number already exists"
            )
    
    # Проверяем уникальность по username (если указан)
    if user_data.username:
        # Убираем @ если есть и приводим к lowercase для сравнения
        username_normalized = user_data.username.lstrip('@').lower()
        # Получаем всех пользователей с username и сравниваем в Python
        users_with_username = db.query(User).filter(User.username.isnot(None)).all()
        for user in users_with_username:
            if user.username and user.username.lstrip('@').lower() == username_normalized:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this username already exists"
                )
    
    # Создаем объект User с обязательными полями
    new_user = User(
        first_name=user_data.first_name or "Неавторизованный",
        is_active=user_data.is_active,
        max_keys=user_data.max_keys,
        is_admin=False
    )
    
    # Устанавливаем опциональные поля только если они указаны (не None)
    # Используем setattr, чтобы не передавать None в конструктор
    if user_data.telegram_id is not None:
        new_user.telegram_id = user_data.telegram_id
    if normalized_phone is not None:
        new_user.phone_number = normalized_phone
    if user_data.username is not None:
        new_user.username = user_data.username
    if user_data.last_name is not None:
        new_user.last_name = user_data.last_name
    if user_data.nickname is not None:
        new_user.nickname = user_data.nickname
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    user_dict = {
        **new_user.__dict__,
        'vpn_keys_count': 0
    }
    user_dict.pop('_sa_instance_state', None)
    
    return UserResponse(**user_dict)


@app.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Обновление информации о пользователе"""
    user = db.query(User).filter(User.id == user_id, User.is_deleted == False).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Обновляем только переданные поля
    if user_data.nickname is not None:
        user.nickname = user_data.nickname
    if user_data.first_name is not None:
        user.first_name = user_data.first_name
    if user_data.last_name is not None:
        user.last_name = user_data.last_name
    if user_data.phone_number is not None:
        # Нормализуем номер телефона
        normalized_phone = contacts_manager._normalize_phone(user_data.phone_number)
        user.phone_number = normalized_phone
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    if user_data.max_keys is not None:
        user.max_keys = user_data.max_keys
    
    db.commit()
    db.refresh(user)
    
    # Подсчитываем количество активных ключей
    vpn_keys_count = db.query(VPNKey).filter(
        VPNKey.user_id == user.id,
        VPNKey.is_active == True
    ).count()
    
    user_dict = {
        **user.__dict__,
        'vpn_keys_count': vpn_keys_count
    }
    user_dict.pop('_sa_instance_state', None)
    
    return UserResponse(**user_dict)


@app.delete("/api/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Удаление пользователя (hard delete - безвозвратное)"""
    from vpn_manager import vpn_manager
    from database import Payment
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Удаляем все платежи пользователя (чтобы избежать ошибки NOT NULL constraint)
    user_payments = db.query(Payment).filter(Payment.user_id == user_id).all()
    for payment in user_payments:
        db.delete(payment)
    
    # Удаляем все ключи пользователя
    user_keys = db.query(VPNKey).filter(VPNKey.user_id == user_id).all()
    for key in user_keys:
        try:
            vpn_manager.delete_vpn_key(key.key_name)
        except Exception as e:
            logger.error(f"Error deleting key {key.key_name}: {e}")
        db.delete(key)
    
    # Hard delete - полное удаление пользователя из БД
    db.delete(user)
    db.commit()
    
    return {"success": True, "message": "User deleted permanently"}


@app.get("/api/users/export/csv")
async def export_users_csv(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Экспорт пользователей в CSV"""
    users = db.query(User).filter(User.is_deleted == False).all()
    
    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow([
        'ID', 'Telegram ID', 'Username', 'Phone Number', 
        'First Name', 'Last Name', 'Nickname', 
        'Is Active', 'Max Keys', 'Is Admin', 'Created At'
    ])
    
    # Данные
    for user in users:
        writer.writerow([
            user.id,
            user.telegram_id or '',
            user.username or '',
            user.phone_number or '',
            user.first_name or '',
            user.last_name or '',
            user.nickname or '',
            'Yes' if user.is_active else 'No',
            user.max_keys,
            'Yes' if user.is_admin else 'No',
            user.created_at.strftime('%Y-%m-%d %H:%M:%S') if user.created_at else ''
        ])
    
    # Создаем response с CSV
    output.seek(0)
    filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    def generate():
        yield output.getvalue()
        output.close()
    
    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.post("/api/users/import/csv")
async def import_users_csv(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Импорт пользователей из CSV"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file"
        )
    
    content = await file.read()
    content_str = content.decode('utf-8')
    
    # Определяем разделитель (точка с запятой или запятая)
    delimiter = ';' if ';' in content_str.split('\n')[0] else ','
    
    csv_reader = csv.DictReader(io.StringIO(content_str), delimiter=delimiter)
    
    imported_count = 0
    updated_count = 0
    errors = []
    
    for row_num, row in enumerate(csv_reader, start=2):  # Начинаем с 2, т.к. 1 - заголовок
        try:
            # Пропускаем пустые строки
            if not any(row.values()):
                continue
            
            # Обрабатываем значения, убирая пробелы и проверяя на пустоту
            telegram_id_str = row.get('Telegram ID', '').strip()
            telegram_id = int(telegram_id_str) if telegram_id_str else None
            
            phone_number = row.get('Phone Number', '').strip() or None
            username = row.get('Username', '').strip() or None
            first_name = row.get('First Name', '').strip() or None
            last_name = row.get('Last Name', '').strip() or None
            nickname = row.get('Nickname', '').strip() or None
            
            # Обрабатываем булевы значения
            is_active_str = row.get('Is Active', 'Yes').strip().lower()
            is_active = is_active_str == 'yes' if is_active_str else True
            
            max_keys_str = row.get('Max Keys', '1').strip()
            max_keys = int(max_keys_str) if max_keys_str else 1
            
            is_admin_str = row.get('Is Admin', 'No').strip().lower()
            is_admin = is_admin_str == 'yes' if is_admin_str else False
            
            if not telegram_id and not phone_number:
                errors.append(f"Row {row_num}: Either Telegram ID or Phone Number is required")
                continue
            
            # Нормализуем номер телефона
            normalized_phone = None
            if phone_number:
                normalized_phone = contacts_manager._normalize_phone(phone_number)
            
            # Проверяем, существует ли пользователь
            existing_user = None
            if telegram_id:
                existing_user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not existing_user and normalized_phone:
                existing_user = db.query(User).filter(User.phone_number == normalized_phone).first()
            
            if existing_user:
                # Обновляем существующего пользователя
                if telegram_id and not existing_user.telegram_id:
                    existing_user.telegram_id = telegram_id
                if normalized_phone and not existing_user.phone_number:
                    existing_user.phone_number = normalized_phone
                if username:
                    existing_user.username = username
                if first_name:
                    existing_user.first_name = first_name
                if last_name:
                    existing_user.last_name = last_name
                if nickname:
                    existing_user.nickname = nickname
                existing_user.is_active = is_active
                existing_user.max_keys = max_keys
                if is_admin and not existing_user.is_admin:
                    existing_user.is_admin = is_admin
                updated_count += 1
            else:
                # Создаем нового пользователя
                new_user = User(
                    telegram_id=telegram_id,
                    phone_number=normalized_phone,
                    username=username,
                    first_name=first_name or "Неавторизованный",
                    last_name=last_name,
                    nickname=nickname,
                    is_active=is_active,
                    max_keys=max_keys,
                    is_admin=is_admin
                )
                db.add(new_user)
                imported_count += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    db.commit()
    
    return {
        "success": True,
        "imported": imported_count,
        "updated": updated_count,
        "errors": errors,
        "message": f"Imported {imported_count} users, updated {updated_count} users"
    }


@app.put("/api/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Активация пользователя (одобрение запроса на активацию)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_active = True
    user.activation_requested = False
    user.activation_requested_at = None
    db.commit()
    
    # Отправляем уведомление пользователю через бота (если есть telegram_id)
    if user.telegram_id:
        try:
            import requests
            from config import BOT_TOKEN
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": user.telegram_id,
                    "text": "✅ Ваш аккаунт активирован! Теперь вы можете использовать бота."
                },
                timeout=5
            )
        except Exception as e:
            logger.error(f"Error sending activation notification to user {user.telegram_id}: {e}")
    
    return {"success": True, "message": "User activated"}


@app.put("/api/users/{user_id}/reject-activation")
async def reject_activation(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Отказ в активации пользователя"""
    from datetime import datetime
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # При отказе устанавливаем activation_requested = False, но оставляем activation_requested_at
    # Это позволит отличить отклоненный запрос от нового пользователя
    # Если activation_requested_at != None, значит запрос был обработан (отклонен)
    if user.activation_requested_at is None:
        user.activation_requested_at = datetime.now()
    user.activation_requested = False
    db.commit()
    
    # Отправляем уведомление пользователю через бота (если есть telegram_id)
    if user.telegram_id:
        try:
            import requests
            from config import BOT_TOKEN
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": user.telegram_id,
                    "text": "❌ Ваш запрос на активацию отклонен. Вы можете купить доступ или обратиться к администратору."
                },
                timeout=5
            )
        except Exception as e:
            logger.error(f"Error sending rejection notification to user {user.telegram_id}: {e}")
    
    return {"success": True, "message": "Activation request rejected"}


class PaymentResponse(BaseModel):
    id: int
    user_id: int
    amount: str
    currency: str
    status: str
    payment_method: str
    payment_type: str
    yoomoney_payment_id: Optional[str]
    yoomoney_label: str
    description: Optional[str]
    created_at: datetime
    paid_at: Optional[datetime]
    qr_code_count: Optional[int]
    subscription_period_days: Optional[int]
    is_test: bool
    user_username: Optional[str] = None
    user_first_name: Optional[str] = None
    user_nickname: Optional[str] = None

    class Config:
        from_attributes = True


class PaymentStatsResponse(BaseModel):
    total_amount: float
    total_count: int
    donations_amount: float
    donations_count: int
    qr_subscriptions_amount: float
    qr_subscriptions_count: int
    success_count: int
    pending_count: int
    failed_count: int
    monthly_stats: List[Dict]


@app.get("/api/payments", response_model=List[PaymentResponse])
async def get_payments(
    skip: int = 0,
    limit: int = 100,
    payment_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sync: bool = True,  # Автоматическая синхронизация pending платежей
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение списка платежей"""
    # Автоматическая синхронизация pending платежей через API YooMoney
    if sync:
        try:
            # Получаем все pending платежи за последние 7 дней
            recent_date = datetime.now() - timedelta(days=7)
            pending_payments = db.query(Payment).filter(
                Payment.status == 'pending',
                Payment.created_at >= recent_date
            ).all()
            
            if pending_payments:
                # Синхронизируем напрямую через helper
                try:
                    # Получаем токен из БД
                    token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
                    
                    if token:
                        # Создаем helper с токеном
                        helper = YooMoneyHelper(
                            client_id=YMONEY_CLIENT_ID,
                            client_secret=YMONEY_CLIENT_SECRET,
                            redirect_uri=YMONEY_REDIRECT_URI,
                            wallet=YMONEY_WALLET,
                            token=token
                        )
                        
                        # Синхронизируем платежи
                        stats = helper.sync_pending_payments(pending_payments, days_back=30)
                        
                        # Обновляем платежи в БД
                        updated_count = 0
                        for payment in pending_payments:
                            if hasattr(payment, '_verification_result'):
                                result = payment._verification_result
                                if result.get('status') == 'success':
                                    payment.status = 'success'
                                    payment.yoomoney_payment_id = result.get('operation_id') or payment.yoomoney_payment_id
                                    if result.get('datetime'):
                                        payment.paid_at = result['datetime']
                                    updated_count += 1
                                    
                                    # Обрабатываем платеж в зависимости от типа
                                    try:
                                        if payment.payment_type == 'donation':
                                            from yoomoney_backend import _handle_donation
                                            _handle_donation(payment, db)
                                        elif payment.payment_type == 'qr_subscription':
                                            from yoomoney_backend import _handle_qr_subscription
                                            _handle_qr_subscription(payment, db)
                                        elif payment.payment_type == 'test':
                                            from yoomoney_backend import _handle_test_access
                                            _handle_test_access(payment, db)
                                    except (ImportError, Exception) as e:
                                        # Если функции не доступны, просто обновляем статус
                                        logger.warning(f"Could not process payment {payment.id}: {e}")
                        
                        db.commit()
                        
                        if updated_count > 0:
                            logger.info(f"Auto-synced payments: {updated_count} updated")
                except Exception as e:
                    logger.warning(f"Failed to auto-sync payments: {e}")
        except Exception as e:
            logger.warning(f"Error during payment auto-sync: {e}")
    
    query = db.query(Payment)
    
    # Фильтры
    if payment_type:
        query = query.filter(Payment.payment_type == payment_type)
    if status:
        query = query.filter(Payment.status == status)
    if start_date:
        start_date_obj = datetime.fromisoformat(start_date)
        query = query.filter(Payment.created_at >= start_date_obj)
    if end_date:
        end_date_obj = datetime.fromisoformat(end_date)
        query = query.filter(Payment.created_at <= end_date_obj)
    
    payments = query.order_by(Payment.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for payment in payments:
        user = payment.user
        payment_dict = {
            **payment.__dict__,
            'user_username': user.username if user else None,
            'user_first_name': user.first_name if user else None,
            'user_nickname': user.nickname if user else None,
        }
        payment_dict.pop('_sa_instance_state', None)
        result.append(PaymentResponse(**payment_dict))
    
    return result


@app.get("/api/payments/stats", response_model=PaymentStatsResponse)
async def get_payment_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sync: bool = True,  # Автоматическая синхронизация pending платежей
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Получение статистики по платежам"""
    # Автоматическая синхронизация pending платежей через API YooMoney
    if sync:
        try:
            # Получаем все pending платежи за последние 7 дней
            recent_date = datetime.now() - timedelta(days=7)
            pending_payments = db.query(Payment).filter(
                Payment.status == 'pending',
                Payment.created_at >= recent_date
            ).all()
            
            if pending_payments:
                # Синхронизируем напрямую через helper
                try:
                    # Получаем токен из БД
                    token = config_manager.get("YMONEY_ACCESS_TOKEN") if config_manager else None
                    
                    if token:
                        # Создаем helper с токеном
                        helper = YooMoneyHelper(
                            client_id=YMONEY_CLIENT_ID,
                            client_secret=YMONEY_CLIENT_SECRET,
                            redirect_uri=YMONEY_REDIRECT_URI,
                            wallet=YMONEY_WALLET,
                            token=token
                        )
                        
                        # Синхронизируем платежи
                        stats = helper.sync_pending_payments(pending_payments, days_back=30)
                        
                        # Обновляем платежи в БД
                        updated_count = 0
                        for payment in pending_payments:
                            if hasattr(payment, '_verification_result'):
                                result = payment._verification_result
                                if result.get('status') == 'success':
                                    payment.status = 'success'
                                    payment.yoomoney_payment_id = result.get('operation_id') or payment.yoomoney_payment_id
                                    if result.get('datetime'):
                                        payment.paid_at = result['datetime']
                                    updated_count += 1
                                    
                                    # Обрабатываем платеж в зависимости от типа
                                    try:
                                        if payment.payment_type == 'donation':
                                            from yoomoney_backend import _handle_donation
                                            _handle_donation(payment, db)
                                        elif payment.payment_type == 'qr_subscription':
                                            from yoomoney_backend import _handle_qr_subscription
                                            _handle_qr_subscription(payment, db)
                                        elif payment.payment_type == 'test':
                                            from yoomoney_backend import _handle_test_access
                                            _handle_test_access(payment, db)
                                    except (ImportError, Exception) as e:
                                        # Если функции не доступны, просто обновляем статус
                                        logger.warning(f"Could not process payment {payment.id}: {e}")
                        
                        db.commit()
                        
                        if updated_count > 0:
                            logger.info(f"Auto-synced payments for stats: {updated_count} updated")
                except Exception as e:
                    logger.warning(f"Failed to auto-sync payments for stats: {e}")
        except Exception as e:
            logger.warning(f"Error during payment auto-sync for stats: {e}")
    
    from datetime import date as date_type
    
    # Определяем период (по умолчанию - текущий месяц)
    if not start_date:
        today = date_type.today()
        start_date_obj = date_type(today.year, today.month, 1)
    else:
        start_date_obj = datetime.fromisoformat(start_date).date()
    
    if not end_date:
        end_date_obj = date_type.today()
    else:
        end_date_obj = datetime.fromisoformat(end_date).date()
    
    # Базовый запрос с фильтром по дате
    base_query = db.query(Payment).filter(
        and_(
            func.date(Payment.created_at) >= start_date_obj,
            func.date(Payment.created_at) <= end_date_obj
        )
    )
    
    # Общая статистика
    total_query = base_query.filter(Payment.status == 'success')
    total_amount = sum(float(p.amount) for p in total_query.all())
    total_count = total_query.count()
    
    # Статистика по донатам
    donations_query = base_query.filter(
        Payment.payment_type == 'donation',
        Payment.status == 'success'
    )
    donations_amount = sum(float(p.amount) for p in donations_query.all())
    donations_count = donations_query.count()
    
    # Статистика по подпискам на QR-коды
    qr_subscriptions_query = base_query.filter(
        Payment.payment_type == 'qr_subscription',
        Payment.status == 'success'
    )
    qr_subscriptions_amount = sum(float(p.amount) for p in qr_subscriptions_query.all())
    qr_subscriptions_count = qr_subscriptions_query.count()
    
    # Статистика по статусам
    success_count = base_query.filter(Payment.status == 'success').count()
    pending_count = base_query.filter(Payment.status == 'pending').count()
    failed_count = base_query.filter(Payment.status == 'failed').count()
    
    # Статистика по месяцам
    monthly_stats = []
    current_date = start_date_obj
    while current_date <= end_date_obj:
        month_start = date_type(current_date.year, current_date.month, 1)
        if current_date.month == 12:
            month_end = date_type(current_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date_type(current_date.year, current_date.month + 1, 1) - timedelta(days=1)
        
        month_payments = base_query.filter(
            and_(
                func.date(Payment.created_at) >= month_start,
                func.date(Payment.created_at) <= month_end,
                Payment.status == 'success'
            )
        ).all()
        
        month_amount = sum(float(p.amount) for p in month_payments)
        month_count = len(month_payments)
        
        monthly_stats.append({
            'month': month_start.strftime('%Y-%m'),
            'amount': month_amount,
            'count': month_count
        })
        
        # Переходим к следующему месяцу
        if current_date.month == 12:
            current_date = date_type(current_date.year + 1, 1, 1)
        else:
            current_date = date_type(current_date.year, current_date.month + 1, 1)
    
    return PaymentStatsResponse(
        total_amount=total_amount,
        total_count=total_count,
        donations_amount=donations_amount,
        donations_count=donations_count,
        qr_subscriptions_amount=qr_subscriptions_amount,
        qr_subscriptions_count=qr_subscriptions_count,
        success_count=success_count,
        pending_count=pending_count,
        failed_count=failed_count,
        monthly_stats=monthly_stats
    )


# Fallback для React Router - должен быть ПОСЛЕ всех API endpoints
if FRONTEND_BUILD_DIR.exists():
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_frontend(full_path: str, request: Request):
        """Раздача React frontend для всех путей, кроме API"""
        # Если путь начинается с api, это API endpoint - пропускаем
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Если путь начинается с docs или openapi, это документация API
        if full_path.startswith("docs") or full_path.startswith("openapi"):
            raise HTTPException(status_code=404, detail="Not found")
        
        # Проверяем, существует ли файл
        file_path = FRONTEND_BUILD_DIR / full_path
        if file_path.exists() and file_path.is_file() and file_path.is_relative_to(FRONTEND_BUILD_DIR):
            return FileResponse(file_path)
        
        # Если файл не найден, возвращаем index.html (для React Router)
        index_file = FRONTEND_BUILD_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        
        raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn
    # Инициализируем БД при запуске
    from database import init_db
    init_db()
    
    logger.info("Starting FastAPI web admin backend on port 8889")
    uvicorn.run(app, host="0.0.0.0", port=8889, log_level="info")

