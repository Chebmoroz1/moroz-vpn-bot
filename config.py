"""Конфигурация приложения"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Базовый путь проекта
BASE_DIR = Path(__file__).parent

# Импорт config_manager с обработкой ошибок (на случай, если БД еще не инициализирована)
try:
    from config_manager import config_manager
except Exception:
    config_manager = None

def get_config(key: str, env_key: str = None, default: str = ""):
    """Получение настройки с приоритетом: БД -> .env -> default"""
    if config_manager:
        try:
            value = config_manager.get(key)
            if value is not None:
                return value
        except Exception:
            pass
    
    # Fallback на .env
    env_key = env_key or key
    return os.getenv(env_key, default)

# Telegram Bot
BOT_TOKEN = get_config("BOT_TOKEN", default=os.getenv("BOT_TOKEN"))
ADMIN_ID = int(get_config("ADMIN_ID", default=str(os.getenv("ADMIN_ID", 0))))

# Server SSH settings
SERVER_HOST = os.getenv("SERVER_HOST", "194.26.27.31")
SERVER_USER = os.getenv("SERVER_USER", "root")
SERVER_SSH_KEY = os.path.expanduser(os.getenv("SERVER_SSH_KEY", "~/.ssh/id_ed25519"))

# Database
DATABASE_PATH = BASE_DIR / os.getenv("DATABASE_PATH", "database.db")

# VPN Settings
VPN_CONFIGS_DIR = BASE_DIR / os.getenv("VPN_CONFIGS_DIR", "vpn_configs")
VPN_PROTOCOL = os.getenv("VPN_PROTOCOL", "amneziawg")
VPN_PORT = int(os.getenv("VPN_PORT", "40680"))
VPN_NETWORK = os.getenv("VPN_NETWORK", "10.8.1.0/24")
VPN_DOCKER_CONTAINER = os.getenv("VPN_DOCKER_CONTAINER", "amnezia-awg")
VPN_INTERFACE = os.getenv("VPN_INTERFACE", "wg0")

# IPinfo API настройки
IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "a570c3cc73bd6e")

# Contacts
CONTACTS_FILE = BASE_DIR / os.getenv("CONTACTS_FILE", "contacts.json")

# Bot Logo
BOT_LOGO_PATH = BASE_DIR / os.getenv("BOT_LOGO_PATH", "logo.png")

# Web Server
# ВАЖНО: YooMoney не работает с IP-адресами, используйте домен
WEB_SERVER_DOMAIN = os.getenv("WEB_SERVER_DOMAIN", "moroz.myftp.biz")
WEB_SERVER_URL = os.getenv("WEB_SERVER_URL", f"http://{WEB_SERVER_DOMAIN}:8888")
WEB_SERVER_HOST = os.getenv("WEB_SERVER_HOST", "0.0.0.0")
WEB_SERVER_PORT = int(os.getenv("WEB_SERVER_PORT", "8888"))

# Yoomoney (для приема платежей)
# ВАЖНО: YooMoney не работает с IP-адресами, используйте домен
# Приоритет: БД -> .env -> default
YMONEY_CLIENT_ID = get_config("YMONEY_CLIENT_ID", default=os.getenv("YMONEY_CLIENT_ID", ""))
YMONEY_CLIENT_SECRET = get_config("YMONEY_CLIENT_SECRET", default=os.getenv("YMONEY_CLIENT_SECRET", ""))
# YMONEY_WALLET опционален - может быть получен автоматически через API после OAuth авторизации
YMONEY_WALLET = get_config("YMONEY_WALLET", default=os.getenv("YMONEY_WALLET", ""))
# Убираем дефолтное значение-плейсхолдер если оно установлено
if YMONEY_WALLET == "your_wallet_number_here":
    YMONEY_WALLET = ""
YMONEY_REDIRECT_URI = get_config("YMONEY_REDIRECT_URI", default=os.getenv("YMONEY_REDIRECT_URI", f"http://{WEB_SERVER_DOMAIN}:{WEB_SERVER_PORT}/yoomoney_redirect"))
YMONEY_NOTIFICATION_URI = get_config("YMONEY_NOTIFICATION_URI", default=os.getenv("YMONEY_NOTIFICATION_URI", f"http://{WEB_SERVER_DOMAIN}:{WEB_SERVER_PORT}/yoomoney_webhook"))
YMONEY_SITE_URL = get_config("YMONEY_SITE_URL", default=os.getenv("YMONEY_SITE_URL", f"http://{WEB_SERVER_DOMAIN}"))

# Создание необходимых директорий
VPN_CONFIGS_DIR.mkdir(exist_ok=True)
