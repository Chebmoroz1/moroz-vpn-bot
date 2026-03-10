#!/usr/bin/env python3
"""Запуск веб-сервера для YooMoney интеграции"""
import logging
from yoomoney_backend import app
from config import (
    WEB_SERVER_HOST, WEB_SERVER_PORT,
    YMONEY_REDIRECT_URI, YMONEY_NOTIFICATION_URI, YMONEY_SITE_URL
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("Запуск YooMoney веб-сервера")
    logger.info("=" * 60)
    logger.info(f"Домен: {YMONEY_SITE_URL}")
    logger.info(f"Redirect URI: {YMONEY_REDIRECT_URI}")
    logger.info(f"Notification URI: {YMONEY_NOTIFICATION_URI}")
    logger.info(f"Сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    logger.info("")
    logger.info("ВАЖНО: Убедитесь, что в настройках YooMoney приложения указаны:")
    logger.info(f"  ✓ Redirect URI: {YMONEY_REDIRECT_URI}")
    logger.info(f"  ✓ Notification URI: {YMONEY_NOTIFICATION_URI}")
    logger.info(f"  ✓ Адрес сайта: {YMONEY_SITE_URL}")
    logger.info("=" * 60)
    logger.info("")
    
    app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, debug=False)

