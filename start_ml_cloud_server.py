#!/usr/bin/env python3
"""Запуск веб-сервера для ML Cloud интеграции (замена YooMoney)"""
import logging
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from ml_cloud_backend import app
from config import (
    WEB_SERVER_HOST, WEB_SERVER_PORT
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("Запуск ML Cloud веб-сервера (замена YooMoney)")
    logger.info("=" * 60)
    logger.info(f"Сервер: {WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    logger.info(f"Эндпоинты:")
    logger.info(f"  - POST /generate_payment_uri - Генерация платежной ссылки")
    logger.info(f"  - POST /check_payment_status - Проверка статуса платежа")
    logger.info(f"  - GET /health - Проверка здоровья сервиса")
    logger.info("")
    logger.info("Платежная система: ML Cloud (Tinkoff)")
    logger.info("Минимальная сумма: 250 ₽")
    logger.info("Комиссия: 2%")
    logger.info("=" * 60)
    logger.info("")
    
    try:
        app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, debug=False)
    except KeyboardInterrupt:
        logger.info("Остановка сервера...")
    except Exception as e:
        logger.error(f"Ошибка запуска сервера: {e}", exc_info=True)
        sys.exit(1)

