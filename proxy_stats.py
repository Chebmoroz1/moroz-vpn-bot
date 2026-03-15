"""Статистика MTProxy: активные TCP-подключения на порт 8444 (на сервере, не в Docker)."""
import logging
import os
import subprocess
from typing import List, Tuple

from vpn_manager import vpn_manager

logger = logging.getLogger(__name__)

MTPROXY_PORT = 8444


def _use_local_ss() -> bool:
    """Решать, выполнять ли ss локально (без SSH). True если is_local или MTPROXY_USE_LOCAL=1."""
    if os.environ.get("MTPROXY_USE_LOCAL", "").strip().lower() in ("1", "true", "yes"):
        return True
    return vpn_manager.is_local


def _run_ss_local(port: int) -> Tuple[str, str, int]:
    """Выполнить ss локально (когда бот и прокси на одном хосте)."""
    cmd = ["ss", "-tn", "state", "established", f"sport = :{port}"]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r.stdout, r.stderr, r.returncode
    except Exception as e:
        return "", str(e), 1


def get_proxy_active_connection_ips(port: int = MTPROXY_PORT) -> Tuple[List[str], str]:
    """
    Получить список уникальных IP клиентов с активными TCP-сессиями на порт прокси.

    Если MTPROXY_USE_LOCAL=1 в окружении или vpn_manager.is_local — выполняется
    локальный вызов ss без SSH. Иначе — через SSH на SERVER_HOST. При ошибке SSH
    (например, нет ключа) делается повторная попытка локально.

    :param port: порт прокси (по умолчанию 8444)
    :return: (список IP, пустая строка или сообщение об ошибке)
    """
    if _use_local_ss():
        stdout, stderr, exit_code = _run_ss_local(port)
    else:
        cmd = f"ss -tn state established sport = :{port}"
        stdout, stderr, exit_code = vpn_manager._ssh_exec(cmd, docker_exec=False)
        # Если SSH не удался из-за отсутствия ключа — пробуем локальный ss
        if exit_code != 0 and "ключ не найден" in (stderr or "").lower():
            logger.info("proxy_stats: SSH key missing, trying local ss")
            stdout, stderr, exit_code = _run_ss_local(port)

    if exit_code != 0:
        err = stderr.strip() or f"exit code {exit_code}"
        logger.warning("proxy_stats: ss command failed: %s", err)
        return [], err

    ips = set()
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line or "Address" in line and "Port" in line:
            continue
        parts = line.split()
        # Формат может быть: State Recv-Q Send-Q Local:Port Peer:Port (5+ колонок)
        # или: Recv-Q Send-Q Local:Port Peer:Port (4 колонки)
        peer = None
        if len(parts) >= 5:
            peer = parts[4]
        elif len(parts) >= 4:
            peer = parts[3]
        if peer and ":" in peer:
            ip = peer.rsplit(":", 1)[0].strip("[]")
            if ip and ip != "0.0.0.0":
                ips.add(ip)

    return sorted(ips), ""
