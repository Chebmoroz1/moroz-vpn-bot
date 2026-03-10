#!/usr/bin/env python3
"""
Скрипт для периодического сбора snapshots трафика (каждые 15 минут)
Запускается через systemd timer
"""
import sys
import os
import logging
from datetime import date

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from traffic_manager import traffic_manager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/opt/vpn-bot/logs/traffic_snapshots.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Основная функция для сбора snapshots"""
    try:
        logger.info("Starting traffic snapshot collection...")
        
        # Создаем snapshot (новая запись)
        results = traffic_manager.sync_traffic_stats(
            target_date=date.today(),
            create_snapshot=True
        )
        
        logger.info(f"Traffic snapshot collection completed: {results}")
        
        # Очищаем старые snapshots (старше 30 дней)
        cleanup_old_snapshots()
        
        return 0
        
    except Exception as e:
        logger.error(f"Error collecting traffic snapshots: {e}", exc_info=True)
        return 1

def cleanup_old_snapshots(days_to_keep: int = 30):
    """Удаление старых snapshots (старше указанного количества дней)"""
    try:
        from database import get_db_session, TrafficStatistics
        from datetime import datetime, timedelta
        
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        
        db = get_db_session()
        try:
            deleted_count = db.query(TrafficStatistics).filter(
                TrafficStatistics.date < cutoff_date
            ).delete()
            
            db.commit()
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old traffic snapshots (older than {days_to_keep} days)")
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error cleaning up old snapshots: {e}", exc_info=True)

if __name__ == '__main__':
    sys.exit(main())

