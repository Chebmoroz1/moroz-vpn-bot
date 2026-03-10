"""Менеджер настроек приложения (из БД)"""
import logging
from typing import Optional, Dict, List
from database import get_db_session, AppConfig
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigManager:
    """Менеджер для работы с настройками из БД"""
    
    _cache: Dict[str, str] = {}
    _cache_timestamp: Optional[datetime] = None
    _cache_ttl: int = 300  # 5 минут кэширования
    
    @classmethod
    def get(cls, key: str, default: Optional[str] = None) -> Optional[str]:
        """Получение значения настройки"""
        # Проверяем кэш
        if cls._cache_timestamp:
            age = (datetime.now() - cls._cache_timestamp).seconds
            if age < cls._cache_ttl and key in cls._cache:
                return cls._cache[key]
        
        # Получаем из БД
        db = get_db_session()
        try:
            config = db.query(AppConfig).filter(AppConfig.key == key).first()
            if config:
                value = config.value
                # Обновляем кэш
                cls._cache[key] = value
                cls._cache_timestamp = datetime.now()
                return value
            return default
        except Exception as e:
            logger.error(f"Error getting config {key}: {e}")
            return default
        finally:
            db.close()
    
    @classmethod
    def set(cls, key: str, value: str, description: Optional[str] = None,
            is_secret: bool = False, category: str = 'general') -> bool:
        """Установка значения настройки"""
        db = get_db_session()
        try:
            config = db.query(AppConfig).filter(AppConfig.key == key).first()
            if config:
                config.value = value
                config.description = description or config.description
                config.is_secret = is_secret
                config.category = category
                config.updated_at = datetime.now()
            else:
                config = AppConfig(
                    key=key,
                    value=value,
                    description=description,
                    is_secret=is_secret,
                    category=category
                )
                db.add(config)
            
            db.commit()
            
            # Обновляем кэш
            cls._cache[key] = value
            cls._cache_timestamp = datetime.now()
            
            return True
        except Exception as e:
            logger.error(f"Error setting config {key}: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @classmethod
    def delete(cls, key: str) -> bool:
        """Удаление настройки"""
        db = get_db_session()
        try:
            config = db.query(AppConfig).filter(AppConfig.key == key).first()
            if config:
                db.delete(config)
                db.commit()
                
                # Удаляем из кэша
                if key in cls._cache:
                    del cls._cache[key]
                
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting config {key}: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    @classmethod
    def get_all(cls, category: Optional[str] = None) -> List[Dict]:
        """Получение всех настроек (для админ-панели)"""
        db = get_db_session()
        try:
            query = db.query(AppConfig)
            if category:
                query = query.filter(AppConfig.category == category)
            
            configs = query.order_by(AppConfig.category, AppConfig.key).all()
            
            result = []
            for config in configs:
                result.append({
                    'id': config.id,
                    'key': config.key,
                    'value': '***' if config.is_secret and config.value else config.value,
                    'raw_value': config.value if not config.is_secret else None,
                    'description': config.description,
                    'is_secret': config.is_secret,
                    'category': config.category,
                    'updated_at': config.updated_at
                })
            
            return result
        except Exception as e:
            logger.error(f"Error getting all configs: {e}")
            return []
        finally:
            db.close()
    
    @classmethod
    def clear_cache(cls):
        """Очистка кэша"""
        cls._cache.clear()
        cls._cache_timestamp = None


# Глобальный экземпляр менеджера
config_manager = ConfigManager()

