"""Статистика MTProxy: активные TCP-подключения на порт 8444 (на сервере, не в Docker)."""
import logging
from typing import List, Tuple

from vpn_manager import vpn_manager

logger = logging.getLogger(__name__)

MTPROXY_PORT = 8444


def get_proxy_active_connection_ips(port: int = MTPROXY_PORT) -> Tuple[List[str], str]:
    """
    Получить список уникальных IP клиентов с активными TCP-сессиями на порт прокси.

    Выполняет на сервере: ss -tn state established sport = :8444
    Парсит колонку Peer (client IP:port), возвращает уникальные IP.

    :param port: порт прокси (по умолчанию 8444)
    :return: (список IP, пустая строка или сообщение об ошибке)
    """
    cmd = f"ss -tn state established sport = :{port}"
    stdout, stderr, exit_code = vpn_manager._ssh_exec(cmd, docker_exec=False)

    if exit_code != 0:
        err = stderr.strip() or f"exit code {exit_code}"
        logger.warning("proxy_stats: ss command failed: %s", err)
        return [], err

    ips = set()
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("State"):
            continue
        parts = line.split()
        # Формат: State Recv-Q Send-Q Local:Port Peer:Port
        if len(parts) >= 5:
            peer = parts[4]
            if ":" in peer:
                ip = peer.rsplit(":", 1)[0]
                if ip and not ip.startswith("["):
                    ips.add(ip)
            else:
                ips.add(peer)

    return sorted(ips), ""
