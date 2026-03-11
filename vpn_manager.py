"""Управление VPN (AmneziaWG через SSH/Docker)"""
import subprocess
import secrets
import ipaddress
import re
import asyncio
import socket
from pathlib import Path
from typing import Optional, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor
from paramiko import SSHClient, AutoAddPolicy
from config import (
    SERVER_HOST, SERVER_USER, SERVER_SSH_KEY,
    VPN_CONFIGS_DIR, VPN_PORT, VPN_NETWORK, VPN_DOCKER_CONTAINER, VPN_INTERFACE
)
import logging

logger = logging.getLogger(__name__)


class VPNManager:
    """Менеджер для управления VPN через SSH/Docker"""

    def __init__(self):
        self.server_host = SERVER_HOST
        self.server_user = SERVER_USER
        self.ssh_key = SERVER_SSH_KEY
        self.docker_container = VPN_DOCKER_CONTAINER
        self.vpn_interface = VPN_INTERFACE
        self.vpn_port = VPN_PORT
        self.vpn_network = ipaddress.ip_network(VPN_NETWORK, strict=False)
        self.wg_path = "/usr/bin/wg"  # Полный путь к wg внутри Docker контейнера
        
        # Определяем, работаем ли мы локально (на том же сервере)
        self.is_local = self._is_local_server()
        
        # ThreadPoolExecutor для выполнения блокирующих операций
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="vpn_exec")
        
        if self.is_local:
            logger.info("✅ VPN Manager: Используется прямой доступ к Docker (локальный режим) - быстрее и эффективнее")
        else:
            logger.info(f"✅ VPN Manager: Используется SSH доступ к {self.server_host} (удаленный режим)")
    
    def _is_local_server(self) -> bool:
        """
        Проверяет, работает ли бот на том же сервере, что и VPN
        Если да - используем прямой docker exec вместо SSH (намного быстрее!)
        """
        try:
            # Получаем IP адрес текущего хоста
            hostname = socket.gethostname()
            try:
                local_ip = socket.gethostbyname(hostname)
            except socket.gaierror:
                local_ip = None
            
            # Проверяем различные варианты локальных адресов
            local_ips = ['127.0.0.1', 'localhost', '::1']
            if local_ip:
                local_ips.append(local_ip)
            
            # Если SERVER_HOST указывает на локальный адрес
            if self.server_host in local_ips:
                logger.debug(f"Определен локальный режим: SERVER_HOST={self.server_host} в списке локальных адресов")
                return True
            
            # Проверяем, можем ли мы выполнить docker команду напрямую
            # Если контейнер доступен локально - значит мы на том же хосте
            try:
                result = subprocess.run(
                    ['docker', 'ps', '--filter', f'name={self.docker_container}', '--format', '{{.Names}}'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and self.docker_container in result.stdout:
                    logger.debug(f"Определен локальный режим: Docker контейнер {self.docker_container} доступен локально")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
                logger.debug(f"Docker команда недоступна локально: {e}")
            
            # Если ничего не подошло - используем SSH
            return False
        except Exception as e:
            logger.warning(f"Не удалось определить, локальный ли сервер: {e}. Используется SSH режим.")
            return False

    def _docker_exec_local(self, command: str) -> Tuple[str, str, int]:
        """
        Прямое выполнение команды в Docker контейнере (локальный режим)
        Намного быстрее, чем SSH, так как нет overhead на шифрование и аутентификацию
        :param command: Команда для выполнения
        :return: (stdout, stderr, exit_code)
        """
        try:
            # Экранируем команду для безопасной передачи
            escaped_command = command.replace('"', '\\"')
            full_command = ['docker', 'exec', self.docker_container, 'sh', '-c', escaped_command]
            
            logger.debug(f"Executing local docker command: {' '.join(full_command)}")
            
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            
            if result.returncode != 0:
                logger.warning(f"Command failed with exit code {result.returncode}: {result.stderr}")
            
            return result.stdout, result.stderr, result.returncode
            
        except subprocess.TimeoutExpired:
            logger.error(f"Docker command timeout: {command}")
            return "", "Command timeout", 1
        except FileNotFoundError:
            logger.error("Docker command not found. Is Docker installed?")
            return "", "Docker not found", 1
        except Exception as e:
            logger.error(f"Docker exec error: {e}", exc_info=True)
            return "", str(e), 1

    def _ssh_exec(self, command: str, docker_exec: bool = False) -> Tuple[str, str, int]:
        """
        Выполнение команды через SSH (для удаленного доступа)
        :param command: Команда для выполнения
        :param docker_exec: Если True, команда выполняется внутри Docker контейнера
        :return: (stdout, stderr, exit_code)
        """
        try:
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            
            # Проверяем существование SSH ключа
            ssh_key_path = Path(self.ssh_key).expanduser()
            if not ssh_key_path.exists():
                error_msg = f"SSH ключ не найден: {ssh_key_path}"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            logger.debug(f"Connecting to {self.server_user}@{self.server_host} using key {ssh_key_path}")
            
            ssh.connect(
                hostname=self.server_host,
                username=self.server_user,
                key_filename=str(ssh_key_path),
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )

            if docker_exec:
                # Используем sh -c с двойными кавычками для правильного выполнения команды внутри контейнера
                escaped_command = command.replace('"', '\\"')
                full_command = f'docker exec {self.docker_container} sh -c "{escaped_command}"'
            else:
                full_command = command

            logger.debug(f"Executing SSH command: {full_command}")
            stdin, stdout, stderr = ssh.exec_command(full_command)
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8')
            stderr_text = stderr.read().decode('utf-8')

            if exit_code != 0:
                logger.warning(f"Command failed with exit code {exit_code}: {stderr_text}")

            ssh.close()
            return stdout_text, stderr_text, exit_code

        except FileNotFoundError as e:
            logger.error(f"SSH key not found: {e}")
            return "", str(e), 1
        except Exception as e:
            logger.error(f"SSH exec error: {e}", exc_info=True)
            error_msg = f"Ошибка SSH подключения: {str(e)}"
            return "", error_msg, 1
    
    def _exec_command(self, command: str, docker_exec: bool = False) -> Tuple[str, str, int]:
        """
        Универсальный метод выполнения команды
        Автоматически выбирает локальный (docker exec) или SSH режим
        :param command: Команда для выполнения
        :param docker_exec: Если True, команда выполняется внутри Docker контейнера
        :return: (stdout, stderr, exit_code)
        """
        if docker_exec and self.is_local:
            # Используем прямой доступ к Docker (быстрее!)
            return self._docker_exec_local(command)
        else:
            # Используем SSH (для удаленного доступа или локальных команд)
            return self._ssh_exec(command, docker_exec)

    def _generate_wg_keys(self) -> Tuple[str, str]:
        """Генерация пары ключей WireGuard"""
        try:
            # Пробуем использовать локальные команды wg
            logger.debug("Attempting to generate keys locally using wg command")
            private_key = subprocess.run(
                ["wg", "genkey"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            ).stdout.strip()

            public_key = subprocess.run(
                ["wg", "pubkey"],
                input=private_key,
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            ).stdout.strip()

            logger.info("Keys generated successfully using local wg command")
            return private_key, public_key
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            # Если wg не установлен локально, генерируем через сервер
            logger.info(f"Local wg command not available ({e}), using server-side generation")
            return self._generate_wg_keys_via_server()

    def _generate_wg_keys_via_server(self) -> Tuple[str, str]:
        """Генерация ключей через сервер"""
        logger.info("Generating WireGuard keys via server")
        
        # Используем путь по умолчанию (проверено, что он работает)
        wg_path = self.wg_path
        
        # Генерируем приватный ключ
        logger.debug("Generating private key")
        stdout, stderr, exit_code = self._exec_command(f"{wg_path} genkey", docker_exec=True)
        if exit_code != 0:
            error_msg = f"Failed to generate private key on server: {stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)

        private_key = stdout.strip()
        if not private_key:
            error_msg = "Private key is empty"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.debug(f"Private key generated: {private_key[:20]}...")

        # Получаем публичный ключ из приватного через stdin
        logger.debug("Generating public key from private key via stdin")
        
        if self.is_local:
            # Локальный режим: используем subprocess напрямую
            try:
                full_command = ['docker', 'exec', '-i', self.docker_container, wg_path, 'pubkey']
                logger.debug(f"Executing local docker command with stdin: {' '.join(full_command)}")
                
                process = subprocess.Popen(
                    full_command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                public_key_stdout, public_key_stderr = process.communicate(input=private_key, timeout=10)
                public_key_exit_code = process.returncode
                
            except subprocess.TimeoutExpired:
                process.kill()
                error_msg = "Timeout when generating public key"
                logger.error(error_msg)
                raise Exception(error_msg)
            except Exception as e:
                error_msg = f"Error when generating public key: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise Exception(error_msg)
        else:
            # Удаленный режим: используем SSH
            ssh = SSHClient()
            ssh.set_missing_host_key_policy(AutoAddPolicy())
            
            ssh_key_path = Path(self.ssh_key).expanduser()
            ssh.connect(
                hostname=self.server_host,
                username=self.server_user,
                key_filename=str(ssh_key_path),
                timeout=10,
                look_for_keys=False,
                allow_agent=False
            )
            
            try:
                # Формируем команду для выполнения внутри Docker контейнера
                # Используем docker exec -i для передачи stdin
                full_command = f'docker exec -i {self.docker_container} {wg_path} pubkey'
                
                logger.debug(f"Executing SSH command with stdin: {full_command}")
                stdin, stdout, stderr = ssh.exec_command(full_command)
                
                # Передаем приватный ключ через stdin
                # Важно: передаем как байты и закрываем stdin после записи
                stdin.write(private_key.encode('utf-8'))
                stdin.flush()
                stdin.channel.shutdown_write()
                
                exit_code = stdout.channel.recv_exit_status()
                public_key_stdout = stdout.read().decode('utf-8')
                public_key_stderr = stderr.read().decode('utf-8')
                
                public_key_exit_code = exit_code
                
            except Exception as e:
                error_msg = f"SSH error when generating public key: {str(e)}"
                logger.error(error_msg, exc_info=True)
                raise Exception(error_msg)
            finally:
                ssh.close()

        if public_key_exit_code != 0:
            error_msg = f"Failed to generate public key on server: {public_key_stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)

        public_key = public_key_stdout.strip()
        if not public_key:
            error_msg = "Public key is empty"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.debug(f"Public key generated: {public_key[:20]}...")

        logger.info(f"Keys generated successfully via server. Public key: {public_key[:20]}...")
        return private_key, public_key

    def get_server_public_key(self) -> Optional[str]:
        """Получение публичного ключа сервера"""
        logger.info(f"Getting server public key from interface {self.vpn_interface}")
        stdout, stderr, exit_code = self._exec_command(f"{self.wg_path} show {self.vpn_interface} public-key", docker_exec=True)
        
        if exit_code != 0:
            logger.error(f"Failed to get server public key. Exit code: {exit_code}, Stderr: {stderr}")
            # Попробуем альтернативный способ
            stdout2, stderr2, exit_code2 = self._exec_command(f"{self.wg_path} show {self.vpn_interface} dump", docker_exec=True)
            if exit_code2 == 0 and stdout2:
                # Публичный ключ сервера - первое поле в первой строке dump
                lines = stdout2.strip().split('\n')
                if lines:
                    parts = lines[0].split('\t')
                    if len(parts) > 0:
                        return parts[0]
            raise Exception(f"Не удалось получить публичный ключ сервера: {stderr}")
        
        if stdout.strip():
            return stdout.strip()
        
        raise Exception("Публичный ключ сервера пустой")

    def get_server_endpoint(self) -> str:
        """Получение endpoint сервера"""
        return f"{self.server_host}:{self.vpn_port}"

    def get_awg_params_from_server(self) -> Dict[str, str]:
        """
        Получение AmneziaWG параметров (Jc/Jmin/Jmax/S1/S2/H1–H4) с сервера.

        Пытается прочитать /opt/amnezia/awg/wg0.conf внутри Docker-контейнера.
        Возвращает словарь с найденными параметрами или пустой словарь при ошибке.
        """
        params: Dict[str, str] = {}
        try:
            # Читаем конфиг AmneziaWG внутри контейнера
            config_path = "/opt/amnezia/awg/wg0.conf"
            command = f"sed -n '1,80p' {config_path}"
            stdout, stderr, exit_code = self._exec_command(
                command,
                docker_exec=True,
            )

            if exit_code != 0:
                logger.warning(
                    f"Failed to read AWG config {config_path}. "
                    f"Exit code: {exit_code}, stderr: {stderr}"
                )
                return params

            for line in stdout.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = [part.strip() for part in line.split("=", 1)]
                if key in {"Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"}:
                    params[key] = value

            if params:
                logger.info(
                    "AWG params loaded from server: "
                    + ", ".join(f"{k}={v}" for k, v in params.items())
                )
            else:
                logger.warning(
                    "AWG params not found in wg0.conf. "
                    "Client configs will be generated without Jc/Jmin/Jmax/S*/H*."
                )

            return params

        except Exception as e:
            logger.error(f"Failed to get AWG params from server: {e}", exc_info=True)
            return params

    def _generate_psk(self) -> Optional[str]:
        """
        Генерация PresharedKey на сервере (wg genpsk внутри контейнера).
        Возвращает строку PSK или None при ошибке.
        """
        try:
            logger.info("Generating PresharedKey via server")
            stdout, stderr, exit_code = self._exec_command(
                f"{self.wg_path} genpsk",
                docker_exec=True,
            )
            if exit_code != 0:
                logger.warning(
                    f"Failed to generate PresharedKey on server. "
                    f"Exit code: {exit_code}, stderr: {stderr}"
                )
                return None

            psk = stdout.strip()
            if not psk:
                logger.warning("Generated PresharedKey is empty")
                return None

            logger.debug("PresharedKey generated successfully")
            return psk
        except Exception as e:
            logger.error(f"Error generating PresharedKey: {e}", exc_info=True)
            return None

    def get_next_available_ip(self) -> Optional[str]:
        """Получение следующего доступного IP адреса"""
        # Получаем список используемых IP
        stdout, stderr, exit_code = self._exec_command(f"{self.wg_path} show {self.vpn_interface} dump", docker_exec=True)
        
        used_ips = set()
        if exit_code == 0:
            for line in stdout.strip().split('\n'):
                if line:
                    parts = line.split('\t')
                    if len(parts) >= 4:
                        allowed_ips = parts[3]
                        # Извлекаем IP из allowed_ips (формат: 10.8.1.X/32)
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', allowed_ips)
                        if ip_match:
                            used_ips.add(ip_match.group(1))

        # Находим свободный IP.
        # Дополнительно: чтобы минимизировать пересечения с уже выданными ключами
        # внешним Amnezia-клиентом, начинаем выдачу адресов из верхней части подсети
        # (хосты с последним октетом >= 128).
        for host in self.vpn_network.hosts():
            ip_str = str(host)
            last_octet = int(ip_str.split('.')[-1])
            # Пропускаем первые несколько адресов (0, 1 обычно зарезервированы)
            # и всю "нижнюю" половину подсети, чтобы не пересекаться с Amnezia-клиентом.
            if last_octet < 128:
                continue
            if ip_str not in used_ips:
                return ip_str

        return None

    def add_peer(self, public_key: str, allowed_ips: str, preshared_key: Optional[str] = None) -> bool:
        """
        Добавление peer на сервер
        :param public_key: Публичный ключ клиента
        :param allowed_ips: Разрешенные IP адреса (например, 10.8.1.2/32)
        :param preshared_key: Pre-shared key (опционально)
        :return: True если успешно
        """
        # Базовая команда для добавления peer
        if preshared_key:
            # Для pre-shared key используем временный файл
            command = (
                f"echo '{preshared_key}' | "
                f"{self.wg_path} set {self.vpn_interface} peer {public_key} allowed-ips {allowed_ips} preshared-key /dev/stdin"
            )
        else:
            command = f"{self.wg_path} set {self.vpn_interface} peer {public_key} allowed-ips {allowed_ips}"
        
        stdout, stderr, exit_code = self._exec_command(command, docker_exec=True)
        
        if exit_code == 0:
            logger.info(f"Peer added successfully via wg set")
            
            # Для AmneziaWG конфигурация может сохраняться автоматически
            # Но можно попробовать явно сохранить через wg-quick (если доступен)
            # Ошибка сохранения не критична, так как для AmneziaWG wg set достаточно
            save_command = f"wg-quick save {self.vpn_interface} 2>/dev/null || true"
            save_stdout, save_stderr, save_exit = self._ssh_exec(save_command, docker_exec=True)
            
            if save_exit == 0:
                logger.info("Configuration saved via wg-quick")
            else:
                logger.debug(f"wg-quick save not available (expected for AmneziaWG): {save_stderr}")
            
            # Проверяем, что peer действительно добавлен
            verify_stdout, verify_stderr, verify_exit = self._ssh_exec(
                f"{self.wg_path} show {self.vpn_interface} dump", docker_exec=True
            )
            if verify_exit == 0 and public_key in verify_stdout:
                logger.info(f"✅ Verified: peer {public_key[:30]}... is present on server")
            else:
                logger.warning(f"⚠️ Warning: peer {public_key[:30]}... not found in dump after addition")
            
            return True
        
        logger.error(f"Failed to add peer: {stderr}")
        return False

    def remove_peer(self, public_key: str) -> bool:
        """Удаление peer с сервера"""
        command = f"{self.wg_path} set {self.vpn_interface} peer {public_key} remove"
        stdout, stderr, exit_code = self._exec_command(command, docker_exec=True)
        
        if exit_code == 0:
            # Сохраняем конфигурацию WireGuard
            save_command = f"wg-quick save {self.vpn_interface}"
            self._ssh_exec(save_command, docker_exec=True)
            return True
        
        logger.error(f"Failed to remove peer: {stderr}")
        return False

    def generate_config(
        self,
        private_key: str,
        client_ip: str,
        server_public_key: str,
        preshared_key: Optional[str] = None,
    ) -> str:
        """Генерация конфигурационного файла AmneziaWG"""
        # Пытаемся получить параметры AmneziaWG (Jc/Jmin/Jmax/S1/S2/H1–H4)
        awg_params = self.get_awg_params_from_server()

        lines = [
            "[Interface]",
            f"PrivateKey = {private_key}",
            f"Address = {client_ip}/32",
            # Используем такой же DNS, как в рабочем Amnezia-конфиге
            "DNS = 1.1.1.1, 1.0.0.1",
            "MTU = 1280",
        ]

        # Добавляем AWG-параметры, если удалось их прочитать с сервера
        for key in ["Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"]:
            if key in awg_params:
                lines.append(f"{key} = {awg_params[key]}")

        lines.extend(
            [
                "",
                "[Peer]",
                f"PublicKey = {server_public_key}",
            ]
        )

        if preshared_key:
            lines.append(f"PresharedKey = {preshared_key}")

        lines.extend(
            [
                f"Endpoint = {self.get_server_endpoint()}",
                # Включаем и IPv4, и IPv6, как в рабочем iOS-конфиге
                "AllowedIPs = 0.0.0.0/0, ::/0",
                "PersistentKeepalive = 25",
                "",
            ]
        )

        return "\n".join(lines)

    def save_config_file(self, key_name: str, config_content: str, overwrite: bool = False) -> Path:
        """
        Сохранение конфигурационного файла
        
        Args:
            key_name: Имя ключа
            config_content: Содержимое конфигурации
            overwrite: Перезаписывать существующий файл (по умолчанию False для защиты)
        
        Returns:
            Path к файлу конфигурации
        """
        config_path = VPN_CONFIGS_DIR / f"{key_name}.conf"
        
        # Защита от перезаписи: если файл существует и overwrite=False, сохраняем существующий
        if config_path.exists() and not overwrite:
            logger.info(f"Config file already exists, preserving existing config: {config_path}")
            logger.info(f"Existing config will not be overwritten. To overwrite, use overwrite=True")
            return config_path
        
        # Записать или перезаписать файл
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        logger.info(f"Config file {'created' if not config_path.exists() else 'updated'}: {config_path}")
        return config_path

    def generate_qr_code(self, key_name: str, config_path: Path) -> Optional[Path]:
        """Генерация QR-кода из конфигурационного файла"""
        try:
            import qrcode
            from PIL import Image

            # Читаем конфигурацию
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()

            # Генерируем QR-код
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(config_content)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            qr_path = VPN_CONFIGS_DIR / f"{key_name}.png"
            img.save(qr_path)
            return qr_path

        except Exception as e:
            logger.error(f"Failed to generate QR code: {e}")
            return None

    def create_vpn_key(self, user_id: int, key_name: str) -> Optional[Dict]:
        """
        Создание VPN ключа для пользователя
        :param user_id: ID пользователя
        :param key_name: Имя ключа
        :return: Словарь с данными ключа или None при ошибке
        """
        try:
            # 1. Генерируем ключи клиента
            logger.info(f"Generating WireGuard keys for {key_name}")
            private_key, public_key = self._generate_wg_keys()
            logger.info(f"Keys generated successfully. Public key: {public_key[:20]}...")

            # 2. Получаем следующий доступный IP
            logger.info("Getting next available IP address")
            client_ip = self.get_next_available_ip()
            if not client_ip:
                logger.error("No available IP addresses in network")
                raise Exception("Нет доступных IP адресов в сети")

            logger.info(f"Assigned IP: {client_ip}")

            # 3. Получаем публичный ключ сервера
            logger.info("Getting server public key")
            server_public_key = self.get_server_public_key()
            if not server_public_key:
                logger.error("Failed to get server public key. Check SSH connection and Docker container.")
                raise Exception("Не удалось получить публичный ключ сервера. Проверьте SSH подключение и Docker контейнер.")

            logger.info(f"Server public key retrieved: {server_public_key[:20]}...")

            # 4. Генерируем PresharedKey (опционально)
            preshared_key = self._generate_psk()
            if preshared_key:
                logger.info("PresharedKey generated and will be used for this peer")
            else:
                logger.info("PresharedKey not generated; peer will be created without PSK")

            # 5. Добавляем peer на сервер
            logger.info(f"Adding peer to server: {public_key[:20]}... with IP {client_ip}")
            allowed_ips = f"{client_ip}/32"
            if not self.add_peer(public_key, allowed_ips, preshared_key=preshared_key):
                logger.error("Failed to add peer to server")
                raise Exception("Не удалось добавить peer на сервер")

            logger.info("Peer added successfully")

            # 6. Генерируем конфигурацию
            config_content = self.generate_config(
                private_key,
                client_ip,
                server_public_key,
                preshared_key=preshared_key,
            )

            # 7. Сохраняем файл конфигурации
            # Проверка: существует ли уже конфигурация?
            config_file_path = VPN_CONFIGS_DIR / f"{key_name}.conf"
            if not config_file_path.exists():
                # Создать новую конфигурацию
                config_path = self.save_config_file(key_name, config_content, overwrite=True)
                logger.info(f"Config file created: {config_path}")
            else:
                # Использовать существующую конфигурацию (не перезаписывать)
                config_path = config_file_path
                logger.info(f"Config file already exists, preserving: {config_path}")

            # 8. Генерируем QR-код
            qr_path = self.generate_qr_code(key_name, config_path)
            if qr_path:
                logger.info(f"QR code generated: {qr_path}")

            return {
                'private_key': private_key,
                'public_key': public_key,
                'client_ip': client_ip,
                'server_public_key': server_public_key,
                'config_path': config_path,
                'qr_path': qr_path,
                'config_content': config_content
            }

        except Exception as e:
            logger.error(f"Failed to create VPN key: {e}", exc_info=True)
            raise  # Пробрасываем исключение дальше для обработки в боте

    def get_all_peers(self) -> list:
        """
        Получение списка всех пиров (peer'ов) с сервера
        :return: Список словарей с информацией о пирах [{'public_key': ..., 'allowed_ips': ..., 'endpoint': ...}, ...]
        """
        try:
            logger.info(f"Getting all peers from interface {self.vpn_interface}")
            stdout, stderr, exit_code = self._exec_command(f"{self.wg_path} show {self.vpn_interface} dump", docker_exec=True)
            
            if exit_code != 0:
                logger.error(f"Failed to get peers. Exit code: {exit_code}, Stderr: {stderr}")
                logger.error(f"Command output: {stdout}")
                return []
            
            logger.debug(f"Raw dump output:\n{stdout}")
            
            peers = []
            lines = stdout.strip().split('\n')
            
            logger.info(f"Total lines in dump: {len(lines)}")
            
            # Первая строка - это сам сервер (не peer), пропускаем её
            for idx, line in enumerate(lines[1:], start=1):  # Пропускаем первую строку (сервер)
                if not line.strip():
                    continue
                
                logger.debug(f"Processing line {idx}: {line[:100]}...")
                    
                parts = line.split('\t')
                logger.debug(f"Line {idx} parts count: {len(parts)}")
                
                # Формат dump: public_key    preshared_key    endpoint    allowed_ips    last_handshake    rx_bytes    tx_bytes    persistent_keepalive
                if len(parts) >= 4:
                    public_key = parts[0].strip()
                    endpoint = parts[2].strip() if len(parts) > 2 and parts[2] else ""
                    allowed_ips = parts[3].strip() if len(parts) > 3 and parts[3] else ""
                    
                    # Извлекаем IP из allowed_ips (формат: 10.8.1.X/32)
                    ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', allowed_ips)
                    client_ip = ip_match.group(1) if ip_match else None
                    
                    peers.append({
                        'public_key': public_key,
                        'client_ip': client_ip,
                        'allowed_ips': allowed_ips,
                        'endpoint': endpoint
                    })
                    logger.debug(f"Added peer: public_key={public_key[:30]}..., ip={client_ip}")
                else:
                    logger.warning(f"Line {idx} has insufficient parts ({len(parts)} < 4): {line[:100]}")
            
            logger.info(f"Found {len(peers)} peers on server")
            
            # Выводим детали найденных пиров для отладки
            if peers:
                logger.info("Peers found on server:")
                for peer in peers:
                    logger.info(f"  - Public key: {peer['public_key'][:30]}..., IP: {peer['client_ip']}, Endpoint: {peer.get('endpoint', 'N/A')}")
            else:
                logger.warning("No peers found on server!")
            
            return peers
            
        except Exception as e:
            logger.error(f"Failed to get peers: {e}", exc_info=True)
            return []

    def get_peer_status(
        self,
        public_key: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Получение статуса конкретного peer'а по public_key или client_ip.

        Возвращает словарь с полями:
        - public_key
        - client_ip
        - allowed_ips
        - endpoint
        - last_handshake (int, unix timestamp)
        - rx_bytes
        - tx_bytes
        - persistent_keepalive
        """
        if not public_key and not client_ip:
            logger.error("get_peer_status called without public_key or client_ip")
            return None

        try:
            logger.info(
                f"Getting peer status for "
                f"{'public_key=' + public_key[:20] + '...' if public_key else ''}"
                f"{' client_ip=' + client_ip if client_ip else ''}"
            )
            stdout, stderr, exit_code = self._exec_command(
                f"{self.wg_path} show {self.vpn_interface} dump", docker_exec=True
            )

            if exit_code != 0:
                logger.error(
                    f"Failed to get peer status. Exit code: {exit_code}, Stderr: {stderr}"
                )
                return None

            lines = stdout.strip().split("\n")
            if not lines:
                return None

            # Первая строка - сервер, пропускаем
            for idx, line in enumerate(lines[1:], start=1):
                if not line.strip():
                    continue

                parts = line.split("\t")
                # Ожидаемый формат:
                # public_key, preshared_key, endpoint, allowed_ips,
                # last_handshake, rx_bytes, tx_bytes, persistent_keepalive, ...
                if len(parts) < 7:
                    logger.debug(
                        f"Line {idx} has insufficient parts ({len(parts)} < 7): {line[:100]}"
                    )
                    continue

                peer_public_key = parts[0].strip()
                endpoint = parts[2].strip() if parts[2] else ""
                allowed_ips = parts[3].strip() if parts[3] else ""
                last_handshake_raw = parts[4].strip() if len(parts) > 4 else "0"
                rx_bytes_raw = parts[5].strip() if len(parts) > 5 else "0"
                tx_bytes_raw = parts[6].strip() if len(parts) > 6 else "0"
                persistent_keepalive = parts[7].strip() if len(parts) > 7 else ""

                ip_match = re.search(r"(\d+\.\d+\.\d+\.\d+)", allowed_ips)
                peer_client_ip = ip_match.group(1) if ip_match else None

                # Фильтрация по public_key / client_ip
                if public_key and peer_public_key != public_key:
                    continue
                if client_ip and peer_client_ip != client_ip:
                    continue

                try:
                    last_handshake = int(last_handshake_raw or "0")
                except ValueError:
                    last_handshake = 0

                try:
                    rx_bytes = int(rx_bytes_raw or "0")
                except ValueError:
                    rx_bytes = 0

                try:
                    tx_bytes = int(tx_bytes_raw or "0")
                except ValueError:
                    tx_bytes = 0

                status: Dict = {
                    "public_key": peer_public_key,
                    "client_ip": peer_client_ip,
                    "allowed_ips": allowed_ips,
                    "endpoint": endpoint,
                    "last_handshake": last_handshake,
                    "rx_bytes": rx_bytes,
                    "tx_bytes": tx_bytes,
                    "persistent_keepalive": persistent_keepalive,
                }

                logger.info(
                    f"Peer status: public_key={peer_public_key[:30]}..., "
                    f"ip={peer_client_ip}, rx={rx_bytes}, tx={tx_bytes}, "
                    f"last_handshake={last_handshake}"
                )
                return status

            logger.info("Peer not found in dump")
            return None

        except Exception as e:
            logger.error(f"Failed to get peer status: {e}", exc_info=True)
            return None

    def sync_keys_with_server(self, db_session) -> dict:
        """
        Синхронизация ключей между БД и сервером
        :param db_session: Сессия БД
        :return: Словарь со статистикой синхронизации
        """
        from database import VPNKey, User
        from datetime import datetime
        
        stats = {
            'added_from_server': 0,
            'removed_from_server': 0,
            'errors': []
        }
        
        try:
            # Получаем все пиры с сервера
            logger.info("Starting key synchronization with server...")
            server_peers = self.get_all_peers()
            logger.info(f"Server peers count: {len(server_peers)}")
            
            server_public_keys = {peer['public_key'] for peer in server_peers}
            logger.info(f"Server public keys count: {len(server_public_keys)}")
            
            # Получаем все ключи из БД с публичными ключами
            db_keys = db_session.query(VPNKey).filter(VPNKey.public_key.isnot(None)).all()
            db_public_keys = {key.public_key for key in db_keys if key.public_key}
            logger.info(f"DB keys count: {len(db_keys)}, DB public keys count: {len(db_public_keys)}")
            
            # Находим ключи на сервере, которых нет в БД
            missing_in_db = server_public_keys - db_public_keys
            logger.info(f"Keys on server but not in DB: {len(missing_in_db)}")
            
            if missing_in_db:
                logger.info(f"Found {len(missing_in_db)} keys on server that are not in DB")
                
                # Создаем или находим системного пользователя для ключей, созданных не через бота
                system_user = db_session.query(User).filter(User.telegram_id == 0).first()
                if not system_user:
                    system_user = User(
                        telegram_id=0,
                        username="system",
                        first_name="System",
                        is_active=True,
                        is_admin=False,
                        max_keys=999
                    )
                    db_session.add(system_user)
                    db_session.commit()
                    db_session.refresh(system_user)
                
                # Добавляем недостающие ключи в БД
                for peer in server_peers:
                    if peer['public_key'] in missing_in_db:
                        try:
                            # Создаем имя ключа на основе IP и даты
                            date_str = datetime.now().strftime("%Y%m%d_%H%M")
                            ip_part = peer['client_ip'].replace('.', '_') if peer['client_ip'] else 'unknown'
                            key_name = f"external_{ip_part}_{date_str}"
                            
                            # Проверяем уникальность имени
                            existing = db_session.query(VPNKey).filter(VPNKey.key_name == key_name).first()
                            counter = 1
                            while existing:
                                key_name = f"external_{ip_part}_{date_str}_{counter}"
                                existing = db_session.query(VPNKey).filter(VPNKey.key_name == key_name).first()
                                counter += 1
                            
                            vpn_key = VPNKey(
                                user_id=system_user.id,
                                key_name=key_name,
                                protocol='amneziawg',
                                client_ip=peer['client_ip'],
                                public_key=peer['public_key'],
                                private_key=None,  # Приватный ключ недоступен для ключей, созданных не через бота
                                is_active=True,
                                created_by_bot=False  # Ключ создан не через бота
                            )
                            db_session.add(vpn_key)
                            stats['added_from_server'] += 1
                            logger.info(f"Added key from server: {key_name} (IP: {peer['client_ip']})")
                        except Exception as e:
                            logger.error(f"Error adding key from server: {e}", exc_info=True)
                            stats['errors'].append(f"Error adding key {peer['public_key'][:20]}...: {e}")
                
                db_session.commit()
            
            # Находим ключи в БД, которых нет на сервере
            missing_on_server = db_public_keys - server_public_keys
            
            if missing_on_server:
                logger.info(f"Found {len(missing_on_server)} keys in DB that are not on server")
                
                # Помечаем ключи как неактивные, если их нет на сервере
                for key in db_keys:
                    if key.public_key in missing_on_server and key.is_active:
                        key.is_active = False
                        stats['removed_from_server'] += 1
                        logger.info(f"Marked key as inactive: {key.key_name} (not found on server)")
                
                db_session.commit()
            
            logger.info(f"Synchronization completed: added={stats['added_from_server']}, removed={stats['removed_from_server']}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to synchronize keys: {e}", exc_info=True)
            stats['errors'].append(f"Synchronization error: {e}")
            return stats

    def delete_vpn_key(self, public_key: Optional[str], key_name: str) -> bool:
        """
        Удаление VPN ключа
        :param public_key: Публичный ключ клиента (может быть None для старых ключей)
        :param key_name: Имя ключа
        :return: True если успешно
        """
        try:
            # 1. Удаляем peer с сервера (если есть public_key)
            if public_key:
                logger.info(f"Removing peer from server: {public_key[:20]}...")
                if not self.remove_peer(public_key):
                    logger.warning(f"Failed to remove peer from server, but continuing with file deletion")
                else:
                    logger.info("Peer removed from server successfully")
            else:
                logger.warning(f"Public key is None for {key_name}, skipping server deletion")

            # 2. Удаляем файлы
            config_path = VPN_CONFIGS_DIR / f"{key_name}.conf"
            qr_path = VPN_CONFIGS_DIR / f"{key_name}.png"

            if config_path.exists():
                config_path.unlink()
                logger.info(f"Deleted config file: {config_path}")
            else:
                logger.warning(f"Config file not found: {config_path}")

            if qr_path and qr_path.exists():
                qr_path.unlink()
                logger.info(f"Deleted QR code: {qr_path}")
            elif qr_path:
                logger.warning(f"QR code file not found: {qr_path}")

            return True

        except Exception as e:
            logger.error(f"Failed to delete VPN key: {e}", exc_info=True)
            return False

    # ========== АСИНХРОННЫЕ ВЕРСИИ МЕТОДОВ ==========
    # Обертки для выполнения блокирующих операций в отдельном потоке

    async def _ssh_exec_async(self, command: str, docker_exec: bool = False) -> Tuple[str, str, int]:
        """
        Асинхронная версия _ssh_exec
        Выполняет SSH команду в отдельном потоке
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._ssh_exec,
            command,
            docker_exec
        )

    async def get_server_public_key_async(self) -> Optional[str]:
        """Асинхронная версия get_server_public_key"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.get_server_public_key
        )

    async def get_next_available_ip_async(self) -> Optional[str]:
        """Асинхронная версия get_next_available_ip"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.get_next_available_ip
        )

    async def add_peer_async(self, public_key: str, allowed_ips: str, preshared_key: Optional[str] = None) -> bool:
        """Асинхронная версия add_peer"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.add_peer,
            public_key,
            allowed_ips,
            preshared_key
        )

    async def remove_peer_async(self, public_key: str) -> bool:
        """Асинхронная версия remove_peer"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.remove_peer,
            public_key
        )

    async def create_vpn_key_async(self, user_id: int, key_name: str) -> Optional[Dict]:
        """
        Асинхронная версия create_vpn_key
        Выполняет создание VPN ключа в отдельном потоке
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.create_vpn_key,
            user_id,
            key_name
        )

    async def delete_vpn_key_async(self, public_key: Optional[str], key_name: str) -> bool:
        """Асинхронная версия delete_vpn_key"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.delete_vpn_key,
            public_key,
            key_name
        )

    async def get_all_peers_async(self) -> list:
        """Асинхронная версия get_all_peers"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.get_all_peers
        )

    async def get_peer_status_async(
        self,
        public_key: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> Optional[Dict]:
        """Асинхронная версия get_peer_status"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self.get_peer_status,
            public_key,
            client_ip,
        )

    def shutdown(self):
        """Закрытие executor при завершении работы"""
        if self.executor:
            self.executor.shutdown(wait=True)


# Глобальный экземпляр менеджера VPN
vpn_manager = VPNManager()
