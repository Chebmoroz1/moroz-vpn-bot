"""
Менеджер конфигурации приложения.
Читает/записывает настройки из таблицы app_config в БД с кэшированием (TTL=5 мин).
Приоритет: БД (app_config) → переменные окружения (.env) → значение по умолчанию.
"""

import os
import time
import logging
from datetime import datetime

from database import get_db_session, AppConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Централизованный менеджер настроек приложения.

    Все настройки хранятся в таблице ``app_config`` и кэшируются
    в памяти на 5 минут (``_cache_ttl``).  При промахе кэша выполняется
    запрос к БД, затем проверяются переменные окружения, и наконец
    используется переданное значение по умолчанию.
    """

    _cache: dict = {}          # key -> (value, timestamp)
    _cache_ttl: int = 300      # 5 минут

    # ------------------------------------------------------------------
    # Основные методы чтения / записи
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, key: str, default: str | None = None) -> str | None:
        """Получить значение настройки.

        Приоритет: кэш (если не истёк) → БД → os.environ → default.
        """
        # 1. Проверка кэша
        cached = cls._cache.get(key)
        if cached is not None:
            value, ts = cached
            if time.time() - ts < cls._cache_ttl:
                return value

        # 2. Запрос к БД
        try:
            with get_db_session() as session:
                entry = (
                    session.query(AppConfig)
                    .filter(AppConfig.key == key)
                    .first()
                )
                if entry is not None:
                    cls._cache[key] = (entry.value, time.time())
                    return entry.value
        except Exception as e:
            logger.error("Ошибка при чтении настройки '%s' из БД: %s", key, e)

        # 3. Переменные окружения
        env_value = os.environ.get(key)
        if env_value is not None:
            cls._cache[key] = (env_value, time.time())
            return env_value

        # 4. Значение по умолчанию
        return default

    @classmethod
    def set(
        cls,
        key: str,
        value: str,
        description: str | None = None,
        is_secret: bool = False,
        category: str = "general",
    ) -> None:
        """Записать значение настройки в БД и обновить кэш."""
        try:
            with get_db_session() as session:
                entry = (
                    session.query(AppConfig)
                    .filter(AppConfig.key == key)
                    .first()
                )
                if entry is not None:
                    entry.value = value
                    if description is not None:
                        entry.description = description
                    entry.is_secret = is_secret
                    entry.category = category
                    entry.updated_at = datetime.now()
                else:
                    entry = AppConfig(
                        key=key,
                        value=value,
                        description=description,
                        is_secret=is_secret,
                        category=category,
                    )
                    session.add(entry)
                session.commit()

            # Обновляем кэш после успешной записи
            cls._cache[key] = (value, time.time())
            logger.info("Настройка '%s' сохранена (category=%s)", key, category)
        except Exception as e:
            logger.error("Ошибка при сохранении настройки '%s': %s", key, e)
            raise

    # ------------------------------------------------------------------
    # Типизированные геттеры
    # ------------------------------------------------------------------

    @classmethod
    def get_bool(cls, key: str, default: bool = False) -> bool:
        """Получить булево значение настройки."""
        val = cls.get(key)
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes")

    @classmethod
    def get_int(cls, key: str, default: int = 0) -> int:
        """Получить целочисленное значение настройки."""
        val = cls.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except (ValueError, TypeError):
            logger.warning(
                "Невозможно преобразовать '%s' в int для ключа '%s', "
                "используется default=%s",
                val,
                key,
                default,
            )
            return default

    # ------------------------------------------------------------------
    # Кэш
    # ------------------------------------------------------------------

    @classmethod
    def clear_cache(cls) -> None:
        """Очистить весь кэш настроек."""
        cls._cache = {}
        logger.debug("Кэш настроек очищен")

    @classmethod
    def invalidate(cls, key: str) -> None:
        """Удалить конкретный ключ из кэша."""
        cls._cache.pop(key, None)

    # ------------------------------------------------------------------
    # Массовые операции
    # ------------------------------------------------------------------

    @classmethod
    def get_all(cls, category: str | None = None) -> list[dict]:
        """Получить все записи настроек, опционально фильтруя по категории.

        Возвращает список словарей с полями:
        ``key``, ``value``, ``description``, ``is_secret``, ``category``,
        ``created_at``, ``updated_at``.
        """
        try:
            with get_db_session() as session:
                query = session.query(AppConfig)
                if category is not None:
                    query = query.filter(AppConfig.category == category)
                entries = query.all()
                result = [
                    {
                        "key": e.key,
                        "value": e.value,
                        "description": e.description,
                        "is_secret": e.is_secret,
                        "category": e.category,
                        "created_at": (
                            e.created_at.isoformat() if e.created_at else None
                        ),
                        "updated_at": (
                            e.updated_at.isoformat() if e.updated_at else None
                        ),
                    }
                    for e in entries
                ]
                return result
        except Exception as e:
            logger.error("Ошибка при получении списка настроек: %s", e)
            return []

    @classmethod
    def delete(cls, key: str) -> bool:
        """Удалить запись настройки из БД и кэша.

        Возвращает ``True``, если запись была найдена и удалена.
        """
        try:
            with get_db_session() as session:
                entry = (
                    session.query(AppConfig)
                    .filter(AppConfig.key == key)
                    .first()
                )
                if entry is None:
                    return False
                session.delete(entry)
                session.commit()

            cls._cache.pop(key, None)
            logger.info("Настройка '%s' удалена", key)
            return True
        except Exception as e:
            logger.error("Ошибка при удалении настройки '%s': %s", key, e)
            return False

    # ------------------------------------------------------------------
    # Режим открытого доступа (Auth Bypass)
    # ------------------------------------------------------------------

    @classmethod
    def is_auth_bypass_active(cls) -> bool:
        """Проверить, активен ли режим открытого доступа.

        Режим считается активным, если:
        1. ``auth_bypass_enabled`` == ``'true'``
        2. ``auth_bypass_until`` ещё не наступило

        Если время действия истекло — режим автоматически отключается.
        """
        enabled = cls.get_bool("auth_bypass_enabled", default=False)
        if not enabled:
            return False

        until_str = cls.get("auth_bypass_until")
        if not until_str:
            return False

        try:
            until_dt = datetime.fromisoformat(until_str)
        except (ValueError, TypeError):
            logger.warning(
                "Некорректный формат auth_bypass_until: '%s'", until_str
            )
            return False

        if datetime.now() >= until_dt:
            # Время истекло — автоматически выключаем
            logger.info("Режим открытого доступа истёк (%s), отключаю", until_str)
            cls.set(
                "auth_bypass_enabled",
                "false",
                description="Включён ли режим открытого доступа",
                category="access",
            )
            cls.invalidate("auth_bypass_enabled")
            cls.invalidate("auth_bypass_until")
            return False

        return True

    @classmethod
    def get_auth_bypass_max_keys(cls) -> int:
        """Получить лимит ключей для авто-активированных пользователей."""
        return cls.get_int("auth_bypass_max_keys", default=1)
