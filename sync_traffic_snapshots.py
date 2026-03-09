#!/usr/bin/env python3
"""Скрипт сбора снимков трафика VPN.
Запускается каждые 15 минут через systemd timer.
"""

import asyncio
import logging
import sys

from database import init_db
from vpn_manager import VPNManager
from traffic_manager import TrafficManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


async def main():
    init_db()
    vpn = VPNManager()
    
    logger.info('Сбор статистики трафика...')
    try:
        stats = await vpn.get_wireguard_stats()
        if stats:
            TrafficManager.save_traffic_snapshot(stats)
            logger.info('Сохранено %d записей трафика', len(stats))
        else:
            logger.info('Нет данных о трафике')
    except Exception as e:
        logger.error('Ошибка сбора трафика: %s', e)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
