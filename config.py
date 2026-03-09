"""
Конфигурация бота.
Загружает настройки из .env файла и предоставляет константы.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем .env
load_dotenv()

# Базовая директория проекта
BASE_DIR = Path(__file__).resolve().parent


def get_env(key: str, default: str = "") -> str:
    """Получить переменную окружения или вернуть значение по умолчанию."""
    return os.getenv(key, default)


# ===================================
# Telegram
# ===================================
BOT_TOKEN: str = get_env("BOT_TOKEN")
ADMIN_ID: int = int(get_env("ADMIN_ID", "0"))

# ===================================
# VPN Сервер
# ===================================
SERVER_HOST: str = get_env("SERVER_HOST", "72.56.52.7")
SERVER_USER: str = get_env("SERVER_USER", "root")
SERVER_SSH_KEY: str = get_env("SERVER_SSH_KEY", "~/.ssh/id_ed25519")

# ===================================
# Настройки VPN (AmneziaWG)
# ===================================
VPN_PORT: int = int(get_env("VPN_PORT", "35649"))
VPN_NETWORK: str = get_env("VPN_NETWORK", "10.8.1.0/24")
VPN_DOCKER_CONTAINER: str = get_env("VPN_DOCKER_CONTAINER", "amnezia-awg")
VPN_INTERFACE: str = get_env("VPN_INTERFACE", "wg0")
VPN_PROTOCOL: str = get_env("VPN_PROTOCOL", "amneziawg")
VPN_CONFIG_PATH: str = get_env("VPN_CONFIG_PATH", "/opt/amnezia/awg/wg0.conf")

# ===================================
# База данных
# ===================================
DATABASE_PATH: Path = (BASE_DIR / get_env("DATABASE_PATH", "database.db")).resolve()
DATABASE_URL: str = f"sqlite:///{DATABASE_PATH}"

# ===================================
# Веб-панель администрирования
# ===================================
WEB_SERVER_DOMAIN: str = get_env("WEB_SERVER_DOMAIN", SERVER_HOST)
WEB_ADMIN_PORT: int = int(get_env("WEB_ADMIN_PORT", "8889"))

# ===================================
# Пути
# ===================================
VPN_CONFIGS_DIR: Path = BASE_DIR / "vpn_configs"
os.makedirs(VPN_CONFIGS_DIR, exist_ok=True)

# ===================================
# IPinfo (опционально)
# ===================================
IPINFO_TOKEN: str = get_env("IPINFO_TOKEN", "")
