"""
VPN Manager module for MOROZ VPN Bot.

Manages AmneziaWG keys via Docker exec on the SAME server (local mode only).
Handles key generation, peer management, config file creation, and QR codes.
"""

import os
import subprocess
import logging
import asyncio
import ipaddress
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import qrcode
from PIL import Image

from config import (
    SERVER_HOST, VPN_PORT, VPN_DOCKER_CONTAINER, VPN_INTERFACE,
    VPN_PROTOCOL, VPN_CONFIGS_DIR, VPN_NETWORK, VPN_CONFIG_PATH
)
from database import get_db_session, VPNKey, User

logger = logging.getLogger(__name__)


class VPNManager:
    """
    Manages AmneziaWG VPN keys and peers via Docker exec commands
    on the local server. No SSH required — all operations are performed
    through ``docker exec`` against the running container.
    """

    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=5)
        logger.info(
            "VPNManager initialized — container=%s, interface=%s, network=%s",
            VPN_DOCKER_CONTAINER, VPN_INTERFACE, VPN_NETWORK,
        )

    # ──────────────────────────────────────────────
    # Docker command helpers
    # ──────────────────────────────────────────────

    def _run_docker_cmd(self, cmd: str) -> str:
        """
        Run a command inside the VPN Docker container synchronously.

        Parameters
        ----------
        cmd : str
            Command to execute inside the container.

        Returns
        -------
        str
            Stripped stdout of the executed command.

        Raises
        ------
        subprocess.CalledProcessError
            If the command exits with a non-zero return code.
        """
        full_cmd = f"docker exec {VPN_DOCKER_CONTAINER} {cmd}"
        logger.debug("Running docker cmd: %s", full_cmd)

        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(
                "Docker cmd failed (rc=%d): %s\nstderr: %s",
                result.returncode, full_cmd, result.stderr.strip(),
            )
            raise subprocess.CalledProcessError(
                result.returncode, full_cmd,
                output=result.stdout, stderr=result.stderr,
            )

        return result.stdout.strip()

    async def _async_docker_cmd(self, cmd: str) -> str:
        """
        Run a Docker exec command asynchronously via the thread-pool executor.

        Parameters
        ----------
        cmd : str
            Command to execute inside the container.

        Returns
        -------
        str
            Stripped stdout of the executed command.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._run_docker_cmd, cmd)

    # ──────────────────────────────────────────────
    # Server introspection
    # ──────────────────────────────────────────────

    async def get_server_public_key(self) -> str:
        """
        Retrieve the server's WireGuard public key from the running interface.

        Returns
        -------
        str
            The server public key (base64).
        """
        try:
            pub_key = await self._async_docker_cmd(f"wg show {VPN_INTERFACE} public-key")
            logger.info("Server public key: %s", pub_key)
            return pub_key
        except Exception as e:
            logger.error("Failed to get server public key: %s", e)
            raise

    async def get_server_obfuscation_params(self) -> dict:
        """
        Parse AmneziaWG obfuscation parameters from the wg0.conf inside
        the Amnezia container.

        We intentionally read from the config file (/opt/amnezia/awg/wg0.conf)
        instead of relying on ``wg show wg0 dump`` to ensure that the
        client config matches exactly what Amnezia generated originally.

        Returns
        -------
        dict
            Keys: Jc, Jmin, Jmax, S1, S2, H1, H2, H3, H4 (all as strings).
        """
        try:
            cfg = await self._async_docker_cmd(f"cat {VPN_CONFIG_PATH}")
            params: dict[str, str] = {}
            for line in cfg.splitlines():
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = [p.strip() for p in line.split("=", 1)]
                if key in {"Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"}:
                    params[key] = value

            # Basic sanity: fall back to zeros if something is missing
            for k in ("Jc", "Jmin", "Jmax", "S1", "S2", "H1", "H2", "H3", "H4"):
                params.setdefault(k, "0")

            logger.info("Server obfuscation params (from config): %s", params)
            return params

        except Exception as e:
            logger.error("Failed to get obfuscation params from %s: %s", VPN_CONFIG_PATH, e)
            # Fallback to zeros so that config generation still works
            return {
                "Jc": "0",
                "Jmin": "0",
                "Jmax": "0",
                "S1": "0",
                "S2": "0",
                "H1": "0",
                "H2": "0",
                "H3": "0",
                "H4": "0",
            }

    # ──────────────────────────────────────────────
    # IP address management
    # ──────────────────────────────────────────────

    async def get_used_ips(self) -> set[str]:
        """
        Collect all IP addresses currently assigned to peers on the interface.

        Returns
        -------
        set[str]
            Set of IP addresses (without CIDR suffix) already in use.
        """
        used_ips: set[str] = set()
        try:
            dump = await self._async_docker_cmd(f"wg show {VPN_INTERFACE} dump")
            lines = dump.strip().split("\n")

            # Skip the first line (interface), remaining lines are peers.
            # Peer format: public_key  preshared_key  endpoint  allowed_ips  latest_handshake  transfer_rx  transfer_tx  persistent_keepalive  ...
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) >= 4:
                    allowed_ips = parts[3]  # e.g. "10.8.1.2/32"
                    for cidr in allowed_ips.split(","):
                        cidr = cidr.strip()
                        if cidr and cidr != "(none)":
                            ip = cidr.split("/")[0]
                            used_ips.add(ip)

            logger.debug("Used IPs on server: %s", used_ips)
        except Exception as e:
            logger.error("Failed to get used IPs: %s", e)

        return used_ips

    async def get_next_ip(self) -> str:
        """
        Find the next available IP address in the VPN subnet.

        Iterates from .2 upward within ``VPN_NETWORK``, skipping the
        network address, broadcast address, gateway (.1), and any
        addresses already assigned to peers.

        Returns
        -------
        str
            The next free IP address.

        Raises
        ------
        RuntimeError
            If no free addresses remain in the subnet.
        """
        used_ips = await self.get_used_ips()
        network = ipaddress.IPv4Network(VPN_NETWORK, strict=False)

        for host in network.hosts():
            ip_str = str(host)
            # Skip .0 (network) and .1 (gateway / server)
            if ip_str.endswith(".0") or ip_str.endswith(".1"):
                continue
            if ip_str not in used_ips:
                logger.info("Next available IP: %s", ip_str)
                return ip_str

        raise RuntimeError(f"No free IP addresses in {VPN_NETWORK}")

    # ──────────────────────────────────────────────
    # Key generation
    # ──────────────────────────────────────────────

    async def generate_keys(self) -> tuple[str, str]:
        """
        Generate a WireGuard private/public key pair inside the container.

        Returns
        -------
        tuple[str, str]
            ``(private_key, public_key)`` as base64-encoded strings.
        """
        try:
            private_key = await self._async_docker_cmd("wg genkey")
            public_key = await self._async_docker_cmd(
                f"bash -c 'echo {private_key} | wg pubkey'"
            )
            logger.info("Generated key pair — public_key=%s", public_key)
            return private_key, public_key
        except Exception as e:
            logger.error("Failed to generate keys: %s", e)
            raise

    # ──────────────────────────────────────────────
    # Peer management
    # ──────────────────────────────────────────────

    async def add_peer(self, public_key: str, client_ip: str) -> bool:
        """
        Add a new peer to the running WireGuard interface and persist the config.

        Parameters
        ----------
        public_key : str
            Client public key (base64).
        client_ip : str
            Client tunnel IP address (without CIDR).

        Returns
        -------
        bool
            ``True`` if the peer was successfully added and verified.
        """
        try:
            # Use a shared preshared key generated by AmneziaWG, if available.
            # This key is created alongside the server keys in /opt/amnezia/awg.
            try:
                psk_path = "/opt/amnezia/awg/wireguard_psk.key"
                # Add peer to the live interface with preshared-key for better security.
                await self._async_docker_cmd(
                    f"wg set {VPN_INTERFACE} peer {public_key} "
                    f"preshared-key {psk_path} allowed-ips {client_ip}/32"
                )
            except Exception:
                # Fallback: add peer without preshared-key if something goes wrong.
                await self._async_docker_cmd(
                    f"wg set {VPN_INTERFACE} peer {public_key} "
                    f"allowed-ips {client_ip}/32"
                )

            # Persist configuration by appending a [Peer] block to the actual
            # AmneziaWG config file instead of calling `wg-quick save`, which
            # expects /etc/wireguard/wg0.conf and fails in this container.
            persist_cmd = (
                "bash -lc '"
                "psk=\"$(cat /opt/amnezia/awg/wireguard_psk.key 2>/dev/null || echo)\"; "
                f"cfg=\"{VPN_CONFIG_PATH}\"; "
                "printf \"\\n[Peer]\\nPublicKey = " + public_key + "\\n\" >> \"$cfg\"; "
                "if [ -n \"$psk\" ]; then "
                "  printf \"PresharedKey = %s\\n\" \"$psk\" >> \"$cfg\"; "
                "fi; "
                f"printf \"AllowedIPs = {client_ip}/32\\n\" >> \"$cfg\""
                "'"
            )
            await self._async_docker_cmd(persist_cmd)

            # Verify the peer was actually added
            dump = await self._async_docker_cmd(f"wg show {VPN_INTERFACE} dump")
            if public_key in dump:
                logger.info("Peer added successfully: %s (%s)", public_key, client_ip)
                return True

            logger.error(
                "Peer NOT found after add — public_key=%s, ip=%s",
                public_key,
                client_ip,
            )
            return False

        except Exception as e:
            logger.error("Failed to add peer %s: %s", public_key, e)
            return False

    async def remove_peer(self, public_key: str) -> bool:
        """
        Remove a peer from the running WireGuard interface and persist the config.

        Parameters
        ----------
        public_key : str
            Client public key (base64).

        Returns
        -------
        bool
            ``True`` if the peer was successfully removed.
        """
        try:
            await self._async_docker_cmd(
                f"wg set {VPN_INTERFACE} peer {public_key} remove"
            )
            await self._async_docker_cmd(f"wg-quick save {VPN_INTERFACE}")
            logger.info("Peer removed: %s", public_key)
            return True
        except Exception as e:
            logger.error("Failed to remove peer %s: %s", public_key, e)
            return False

    # ──────────────────────────────────────────────
    # Config generation
    # ──────────────────────────────────────────────

    def generate_config(
        self,
        private_key: str,
        client_ip: str,
        server_public_key: str,
        obfuscation_params: dict,
        preshared_key: str | None = None,
    ) -> str:
        """
        Generate an AmneziaWG client ``.conf`` file content.

        Parameters
        ----------
        private_key : str
            Client private key (base64).
        client_ip : str
            Client tunnel IP address.
        server_public_key : str
            Server public key (base64).
        obfuscation_params : dict
            AmneziaWG obfuscation parameters (Jc, Jmin, Jmax, S1, S2, H1–H4).

        Returns
        -------
        str
            Complete ``.conf`` file content.
        """
        config = (
            f"[Interface]\n"
            f"PrivateKey = {private_key}\n"
            f"Address = {client_ip}/32\n"
            f"DNS = 1.1.1.1, 1.0.0.1\n"
            f"Jc = {obfuscation_params['Jc']}\n"
            f"Jmin = {obfuscation_params['Jmin']}\n"
            f"Jmax = {obfuscation_params['Jmax']}\n"
            f"S1 = {obfuscation_params['S1']}\n"
            f"S2 = {obfuscation_params['S2']}\n"
            f"H1 = {obfuscation_params['H1']}\n"
            f"H2 = {obfuscation_params['H2']}\n"
            f"H3 = {obfuscation_params['H3']}\n"
            f"H4 = {obfuscation_params['H4']}\n"
            f"\n"
            f"[Peer]\n"
            f"PublicKey = {server_public_key}\n"
            f"Endpoint = {SERVER_HOST}:{VPN_PORT}\n"
        )

        if preshared_key:
            config += f"PresharedKey = {preshared_key}\n"

        config += (
            f"AllowedIPs = 0.0.0.0/0, ::/0\n"
            f"PersistentKeepalive = 25\n"
        )
        return config

    def save_config_file(self, config_content: str, key_name: str) -> str:
        """
        Save a client config to a ``.conf`` file on disk.

        Parameters
        ----------
        config_content : str
            Full config file content.
        key_name : str
            Unique key name used as the filename stem.

        Returns
        -------
        str
            Absolute path to the saved file.
        """
        os.makedirs(VPN_CONFIGS_DIR, exist_ok=True)
        file_path = os.path.join(VPN_CONFIGS_DIR, f"{key_name}.conf")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(config_content)

        logger.info("Config saved: %s", file_path)
        return file_path

    def generate_qr_code(self, config_content: str, key_name: str) -> str:
        """
        Generate a QR-code PNG image from the config content.

        Parameters
        ----------
        config_content : str
            Full config file content to encode.
        key_name : str
            Unique key name used as the filename stem.

        Returns
        -------
        str
            Absolute path to the saved PNG file.
        """
        os.makedirs(VPN_CONFIGS_DIR, exist_ok=True)
        qr_path = os.path.join(VPN_CONFIGS_DIR, f"{key_name}.png")

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(config_content)
        qr.make(fit=True)

        img: Image.Image = qr.make_image(fill_color="black", back_color="white")
        img.save(qr_path)

        logger.info("QR code saved: %s", qr_path)
        return qr_path

    # ──────────────────────────────────────────────
    # Key naming
    # ──────────────────────────────────────────────

    def generate_key_name(self, user: User) -> str:
        """
        Generate a unique, filesystem-safe key name from user information.

        Format: ``{first_name}_{phone_part}_{datetime}_{telegram_id}``

        Parameters
        ----------
        user : User
            Database user object.

        Returns
        -------
        str
            Sanitized key name, max 60 characters.
        """
        first_name = (user.first_name or "user").strip()
        phone = (user.phone_number or "nophone").strip()
        telegram_id = str(user.telegram_id or 0)
        now = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Sanitize: replace spaces with _, '+' with 'plus', drop non-alnum/_
        def sanitize(s: str) -> str:
            s = s.replace(" ", "_")
            s = s.replace("+", "plus")
            s = re.sub(r"[^a-zA-Z0-9_]", "", s)
            return s

        first_name = sanitize(first_name)
        phone_part = sanitize(phone)
        telegram_id = sanitize(telegram_id)

        key_name = f"{first_name}_{phone_part}_{now}_{telegram_id}"

        # Truncate to 60 characters
        if len(key_name) > 60:
            key_name = key_name[:60]

        logger.debug("Generated key name: %s", key_name)
        return key_name

    # ──────────────────────────────────────────────
    # Full lifecycle: create / delete key
    # ──────────────────────────────────────────────

    async def create_key(self, user: User) -> dict | None:
        """
        Full key creation flow:

        1. Check user key limits (skipped for admin).
        2. Generate a WireGuard key pair.
        3. Find the next free IP address.
        4. Add the peer to the server.
        5. Generate config, save files and QR code.
        6. Create a database record.

        Parameters
        ----------
        user : User
            The user requesting the key.

        Returns
        -------
        dict | None
            Dictionary with key information on success, or ``None`` on error.
            Keys: ``key_id``, ``key_name``, ``client_ip``, ``config_file``,
            ``qr_code_file``, ``config_content``.
        """
        try:
            # ── 1. Check limits ──────────────────────────
            # Admin users are not subject to key limits.
            if not user.is_admin:
                with get_db_session() as session:
                    active_keys = (
                        session.query(VPNKey)
                        .filter(
                            VPNKey.user_id == user.id,
                            VPNKey.is_active.is_(True),
                        )
                        .count()
                    )
                    max_keys = user.max_keys or 0

                    if max_keys > 0 and active_keys >= max_keys:
                        logger.warning(
                            "User %s (id=%d) reached key limit: %d/%d",
                            user.username,
                            user.id,
                            active_keys,
                            max_keys,
                        )
                        return None

            # ── 2. Generate key pair ─────────────────────
            private_key, public_key = await self.generate_keys()

            # ── 3. Get next free IP ──────────────────────
            client_ip = await self.get_next_ip()

            # ── 4. Add peer to server ────────────────────
            success = await self.add_peer(public_key, client_ip)
            if not success:
                logger.error("Failed to add peer to server for user %s", user.username)
                return None

            # ── 5. Generate config & files ───────────────
            server_public_key = await self.get_server_public_key()
            obfuscation_params = await self.get_server_obfuscation_params()

            # Shared preshared key used by AmneziaWG for all peers.
            try:
                preshared_key = await self._async_docker_cmd(
                    "cat /opt/amnezia/awg/wireguard_psk.key"
                )
            except Exception:
                preshared_key = ""

            config_content = self.generate_config(
                private_key,
                client_ip,
                server_public_key,
                obfuscation_params,
                preshared_key=preshared_key or None,
            )

            key_name = self.generate_key_name(user)
            config_file = self.save_config_file(config_content, key_name)
            qr_code_file = self.generate_qr_code(config_content, key_name)

            # ── 6. Create DB record ──────────────────────
            with get_db_session() as session:
                vpn_key = VPNKey(
                    user_id=user.id,
                    key_name=key_name,
                    config_file_path=config_file,
                    qr_code_path=qr_code_file,
                    protocol=VPN_PROTOCOL,
                    client_ip=client_ip,
                    public_key=public_key,
                    private_key=private_key,
                    created_by_bot=True,
                    is_active=True,
                )
                session.add(vpn_key)
                session.flush()
                key_id = vpn_key.id

            logger.info(
                "Key created — id=%d, name=%s, user=%s, ip=%s",
                key_id, key_name, user.username, client_ip,
            )

            return {
                "key_id": key_id,
                "key_name": key_name,
                "client_ip": client_ip,
                "config_file": config_file,
                "qr_code_file": qr_code_file,
                "config_content": config_content,
            }

        except Exception as e:
            logger.error("Error creating key for user %s: %s", user.username, e, exc_info=True)
            return None

    async def delete_key(self, key_id: int) -> bool:
        """
        Full key deletion flow:

        1. Look up the key in the database.
        2. Remove the peer from the WireGuard interface.
        3. Delete config and QR code files from disk.
        4. Delete the database record.

        Parameters
        ----------
        key_id : int
            Primary key of the VPNKey record.

        Returns
        -------
        bool
            ``True`` if all steps completed successfully.
        """
        try:
            # ── 1. Find the key in DB ────────────────────
            with get_db_session() as session:
                vpn_key = session.query(VPNKey).filter(VPNKey.id == key_id).first()
                if not vpn_key:
                    logger.warning("Key id=%d not found in database", key_id)
                    return False

                public_key = vpn_key.public_key
                config_path = vpn_key.config_file_path
                qr_path = vpn_key.qr_code_path
                key_name = vpn_key.key_name

            # ── 2. Remove peer from server ───────────────
            if public_key:
                removed = await self.remove_peer(public_key)
                if not removed:
                    logger.warning(
                        "Could not remove peer %s from server (key id=%d), "
                        "continuing with DB/file cleanup",
                        public_key, key_id,
                    )

            # ── 3. Delete files ──────────────────────────
            for fpath in (config_path, qr_path):
                if fpath and os.path.exists(fpath):
                    try:
                        os.remove(fpath)
                        logger.debug("Deleted file: %s", fpath)
                    except OSError as e:
                        logger.warning("Failed to delete file %s: %s", fpath, e)

            # ── 4. Delete DB record ──────────────────────
            with get_db_session() as session:
                vpn_key = session.query(VPNKey).filter(VPNKey.id == key_id).first()
                if vpn_key:
                    session.delete(vpn_key)

            logger.info("Key deleted — id=%d, name=%s", key_id, key_name)
            return True

        except Exception as e:
            logger.error("Error deleting key id=%d: %s", key_id, e, exc_info=True)
            return False

    # ──────────────────────────────────────────────
    # Statistics & sync
    # ──────────────────────────────────────────────

    async def get_wireguard_stats(self) -> list[dict]:
        """
        Parse ``wg show`` dump output to collect per-peer traffic statistics.

        Peer lines in the dump have the format::

            public_key  preshared_key  endpoint  allowed_ips  latest_handshake
            transfer_rx  transfer_tx  persistent_keepalive  ...

        Returns
        -------
        list[dict]
            Each dict contains: ``public_key``, ``endpoint``, ``allowed_ips``,
            ``latest_handshake``, ``transfer_rx``, ``transfer_tx``.
        """
        stats: list[dict] = []
        try:
            dump = await self._async_docker_cmd(f"wg show {VPN_INTERFACE} dump")
            lines = dump.strip().split("\n")

            # Skip first line (interface)
            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) < 8:
                    continue

                stats.append({
                    "public_key": parts[0],
                    "endpoint": parts[2] if parts[2] != "(none)" else None,
                    "allowed_ips": parts[3],
                    "latest_handshake": (
                        datetime.fromtimestamp(int(parts[4])).isoformat()
                        if parts[4] != "0" else None
                    ),
                    "transfer_rx": int(parts[5]),
                    "transfer_tx": int(parts[6]),
                })

            logger.info("Retrieved stats for %d peers", len(stats))
        except Exception as e:
            logger.error("Failed to get WireGuard stats: %s", e)

        return stats

    async def sync_keys_with_server(self) -> dict:
        """
        Synchronise database VPN key records with the actual server state.

        * Keys present in DB but missing on the server are marked inactive.
        * Peers present on the server but missing in DB are reported.

        Returns
        -------
        dict
            Summary with keys: ``synced``, ``deactivated``, ``orphaned_peers``,
            ``total_db_keys``, ``total_server_peers``.
        """
        result = {
            "synced": 0,
            "deactivated": 0,
            "orphaned_peers": 0,
            "total_db_keys": 0,
            "total_server_peers": 0,
        }

        try:
            # Get server peers
            dump = await self._async_docker_cmd(f"wg show {VPN_INTERFACE} dump")
            lines = dump.strip().split("\n")

            server_pubkeys: set[str] = set()
            for line in lines[1:]:
                parts = line.split("\t")
                if parts:
                    server_pubkeys.add(parts[0])

            result["total_server_peers"] = len(server_pubkeys)

            # Get DB keys
            with get_db_session() as session:
                db_keys = (
                    session.query(VPNKey)
                    .filter(VPNKey.is_active.is_(True))
                    .all()
                )
                result["total_db_keys"] = len(db_keys)
                db_pubkeys: set[str] = set()

                for key in db_keys:
                    if key.public_key:
                        db_pubkeys.add(key.public_key)

                    if key.public_key and key.public_key in server_pubkeys:
                        # Key exists on both sides — synced
                        result["synced"] += 1
                    elif key.public_key and key.public_key not in server_pubkeys:
                        # Key in DB but not on server — deactivate
                        key.is_active = False
                        result["deactivated"] += 1
                        logger.warning(
                            "Deactivated key id=%d (%s) — not found on server",
                            key.id, key.key_name,
                        )

            # Orphaned peers: on server but not in DB
            orphaned = server_pubkeys - db_pubkeys
            result["orphaned_peers"] = len(orphaned)
            if orphaned:
                logger.warning(
                    "Found %d orphaned peers on server (not in DB): %s",
                    len(orphaned),
                    ", ".join(list(orphaned)[:5]) + ("..." if len(orphaned) > 5 else ""),
                )

            logger.info(
                "Sync complete — synced=%d, deactivated=%d, orphaned=%d",
                result["synced"], result["deactivated"], result["orphaned_peers"],
            )

        except Exception as e:
            logger.error("Failed to sync keys with server: %s", e, exc_info=True)

        return result
