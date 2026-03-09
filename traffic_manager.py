"""
Traffic Manager module for MOROZ VPN Bot.

Collects and analyzes traffic statistics from WireGuard.
Provides methods for saving traffic snapshots, generating overviews,
chart data, per-user and all-users traffic reports.
"""

import json
import logging
from datetime import datetime, date, timedelta

from sqlalchemy import func, desc

from database import get_db_session, VPNKey, TrafficStatistic, User

logger = logging.getLogger(__name__)


class TrafficManager:
    """Manages VPN traffic statistics collection and analysis."""

    # ──────────────────────────────────────────────
    # Save traffic snapshot
    # ──────────────────────────────────────────────

    @classmethod
    def save_traffic_snapshot(cls, stats: list[dict]) -> int:
        """
        Save a traffic snapshot from WireGuard stats.

        Takes output from VPNManager.get_wireguard_stats() — a list of dicts
        with keys: public_key, transfer_rx, transfer_tx, endpoint, latest_handshake.

        Returns the number of records saved.
        """
        saved_count = 0
        now = datetime.now()
        today = date.today()

        try:
            with get_db_session() as session:
                for peer in stats:
                    try:
                        public_key = peer.get("public_key")
                        if not public_key:
                            continue

                        # Find VPNKey by public_key
                        vpn_key = (
                            session.query(VPNKey)
                            .filter(VPNKey.public_key == public_key)
                            .first()
                        )
                        if not vpn_key:
                            logger.debug(
                                "VPN key not found for public_key: %s…",
                                public_key[:16],
                            )
                            continue

                        # Parse endpoint to extract connection IP
                        connection_ip = None
                        endpoint = peer.get("endpoint")
                        if endpoint and endpoint != "(none)":
                            # Endpoint format: "IP:port" or "[IPv6]:port"
                            try:
                                if endpoint.startswith("["):
                                    # IPv6: [::ffff:1.2.3.4]:51820
                                    connection_ip = endpoint.split("]:")[0].lstrip("[")
                                else:
                                    connection_ip = endpoint.rsplit(":", 1)[0]
                            except (IndexError, ValueError):
                                connection_ip = endpoint

                        # Build connection_ips as JSON
                        connection_ips_json = None
                        if connection_ip:
                            connection_ips_json = json.dumps([connection_ip])

                        # Parse latest_handshake (unix timestamp) to datetime
                        last_connection = None
                        latest_handshake = peer.get("latest_handshake")
                        if latest_handshake:
                            try:
                                handshake_ts = int(latest_handshake)
                                if handshake_ts > 0:
                                    last_connection = datetime.fromtimestamp(handshake_ts)
                            except (ValueError, TypeError, OSError):
                                logger.debug(
                                    "Could not parse latest_handshake: %s",
                                    latest_handshake,
                                )

                        # Create TrafficStatistic record
                        traffic_record = TrafficStatistic(
                            vpn_key_id=vpn_key.id,
                            date=today,
                            timestamp=now,
                            bytes_received=int(peer.get("transfer_rx", 0)),
                            bytes_sent=int(peer.get("transfer_tx", 0)),
                            connection_ips=connection_ips_json,
                            last_connection=last_connection,
                        )
                        session.add(traffic_record)

                        # Update VPNKey.last_used if handshake is recent (within 5 minutes)
                        if last_connection:
                            time_since_handshake = now - last_connection
                            if time_since_handshake < timedelta(minutes=5):
                                vpn_key.last_used = now

                        saved_count += 1

                    except Exception as e:
                        logger.error(
                            "Error processing peer %s: %s",
                            peer.get("public_key", "unknown")[:16],
                            e,
                        )
                        continue

        except Exception as e:
            logger.error("Error saving traffic snapshot: %s", e)

        logger.info("Saved %d traffic records out of %d peers", saved_count, len(stats))
        return saved_count

    # ──────────────────────────────────────────────
    # Traffic overview
    # ──────────────────────────────────────────────

    @classmethod
    def get_traffic_overview(cls) -> dict:
        """
        Get traffic overview for the admin dashboard.

        Returns dict with:
            - total_received: total bytes received this month
            - total_sent: total bytes sent this month
            - active_connections: peers with handshake < 5 min ago
            - total_keys: count of active VPN keys
        """
        try:
            with get_db_session() as session:
                now = datetime.now()
                month_start = date(now.year, now.month, 1)
                five_min_ago = now - timedelta(minutes=5)

                # ── Total traffic this month (compute deltas) ──
                # We need to compute deltas from cumulative WG counters.
                # For each key, the monthly traffic = sum of deltas between
                # consecutive snapshots within this month.
                total_received, total_sent = cls._compute_traffic_totals(
                    session, month_start, date.today()
                )

                # ── Active connections ──
                # Peers whose latest snapshot has last_connection within 5 minutes
                active_subq = (
                    session.query(
                        TrafficStatistic.vpn_key_id,
                        func.max(TrafficStatistic.timestamp).label("max_ts"),
                    )
                    .group_by(TrafficStatistic.vpn_key_id)
                    .subquery()
                )

                active_connections = (
                    session.query(func.count(TrafficStatistic.id))
                    .join(
                        active_subq,
                        (TrafficStatistic.vpn_key_id == active_subq.c.vpn_key_id)
                        & (TrafficStatistic.timestamp == active_subq.c.max_ts),
                    )
                    .filter(TrafficStatistic.last_connection >= five_min_ago)
                    .scalar()
                ) or 0

                # ── Total active keys ──
                total_keys = (
                    session.query(func.count(VPNKey.id))
                    .filter(VPNKey.is_active == True)
                    .scalar()
                ) or 0

                return {
                    "total_received": total_received,
                    "total_sent": total_sent,
                    "active_connections": active_connections,
                    "total_keys": total_keys,
                }

        except Exception as e:
            logger.error("Error getting traffic overview: %s", e)
            return {
                "total_received": 0,
                "total_sent": 0,
                "active_connections": 0,
                "total_keys": 0,
            }

    # ──────────────────────────────────────────────
    # Chart data
    # ──────────────────────────────────────────────

    @classmethod
    def get_traffic_chart_data(cls, period: str) -> list[dict]:
        """
        Get traffic data points for chart rendering.

        Args:
            period: one of '6hours', 'day', 'week', 'month'

        Returns list of dicts with:
            - timestamp (ISO string)
            - bytes_received (delta)
            - bytes_sent (delta)

        Traffic values from WireGuard are cumulative, so this method
        computes deltas between consecutive snapshots.
        """
        # Determine time range and grouping interval
        now = datetime.now()

        period_config = {
            "6hours": {"delta": timedelta(hours=6), "interval_minutes": 15},
            "day": {"delta": timedelta(days=1), "interval_minutes": 60},
            "week": {"delta": timedelta(weeks=1), "interval_minutes": 180},
            "month": {"delta": timedelta(days=30), "interval_minutes": 1440},
        }

        config = period_config.get(period)
        if not config:
            logger.warning("Unknown period: %s, defaulting to 'day'", period)
            config = period_config["day"]

        start_time = now - config["delta"]
        interval_minutes = config["interval_minutes"]

        try:
            with get_db_session() as session:
                # Get all snapshots in the period, ordered by key and time
                snapshots = (
                    session.query(
                        TrafficStatistic.vpn_key_id,
                        TrafficStatistic.timestamp,
                        TrafficStatistic.bytes_received,
                        TrafficStatistic.bytes_sent,
                    )
                    .filter(TrafficStatistic.timestamp >= start_time)
                    .order_by(
                        TrafficStatistic.vpn_key_id,
                        TrafficStatistic.timestamp,
                    )
                    .all()
                )

                if not snapshots:
                    return []

                # Compute deltas per key between consecutive snapshots
                deltas = []
                prev_by_key: dict[int, tuple] = {}

                for snap in snapshots:
                    key_id = snap.vpn_key_id
                    if key_id in prev_by_key:
                        prev = prev_by_key[key_id]
                        delta_rx = snap.bytes_received - prev[1]
                        delta_tx = snap.bytes_sent - prev[2]

                        # If delta is negative, counter was reset (WG restart);
                        # treat the current value as the delta itself
                        if delta_rx < 0:
                            delta_rx = snap.bytes_received
                        if delta_tx < 0:
                            delta_tx = snap.bytes_sent

                        deltas.append({
                            "timestamp": snap.timestamp,
                            "bytes_received": delta_rx,
                            "bytes_sent": delta_tx,
                        })

                    prev_by_key[key_id] = (
                        snap.timestamp,
                        snap.bytes_received,
                        snap.bytes_sent,
                    )

                if not deltas:
                    return []

                # Group deltas into time intervals
                interval = timedelta(minutes=interval_minutes)
                grouped: dict[datetime, dict] = {}

                for d in deltas:
                    # Round timestamp down to the interval boundary
                    ts = d["timestamp"]
                    seconds_since_start = (ts - start_time).total_seconds()
                    bucket_index = int(seconds_since_start // interval.total_seconds())
                    bucket_start = start_time + interval * bucket_index

                    if bucket_start not in grouped:
                        grouped[bucket_start] = {
                            "timestamp": bucket_start.isoformat(),
                            "bytes_received": 0,
                            "bytes_sent": 0,
                        }

                    grouped[bucket_start]["bytes_received"] += d["bytes_received"]
                    grouped[bucket_start]["bytes_sent"] += d["bytes_sent"]

                # Sort by timestamp and return
                result = sorted(grouped.values(), key=lambda x: x["timestamp"])
                return result

        except Exception as e:
            logger.error("Error getting traffic chart data: %s", e)
            return []

    # ──────────────────────────────────────────────
    # Per-user traffic
    # ──────────────────────────────────────────────

    @classmethod
    def get_user_traffic(cls, user_id: int, period: str = "month") -> dict:
        """
        Get traffic statistics for a specific user's VPN keys.

        Args:
            user_id: database user ID
            period: one of '6hours', 'day', 'week', 'month'

        Returns dict with:
            - user_id
            - total_received (bytes, delta-based)
            - total_sent (bytes, delta-based)
            - keys: list of per-key traffic dicts
        """
        period_deltas = {
            "6hours": timedelta(hours=6),
            "day": timedelta(days=1),
            "week": timedelta(weeks=1),
            "month": timedelta(days=30),
        }

        delta = period_deltas.get(period, timedelta(days=30))
        start_time = datetime.now() - delta

        try:
            with get_db_session() as session:
                # Get user's active keys
                user_keys = (
                    session.query(VPNKey)
                    .filter(VPNKey.user_id == user_id, VPNKey.is_active == True)
                    .all()
                )

                keys_traffic = []
                total_received = 0
                total_sent = 0

                for key in user_keys:
                    # Get snapshots for this key in the period
                    snapshots = (
                        session.query(
                            TrafficStatistic.timestamp,
                            TrafficStatistic.bytes_received,
                            TrafficStatistic.bytes_sent,
                            TrafficStatistic.last_connection,
                        )
                        .filter(
                            TrafficStatistic.vpn_key_id == key.id,
                            TrafficStatistic.timestamp >= start_time,
                        )
                        .order_by(TrafficStatistic.timestamp)
                        .all()
                    )

                    # Compute deltas
                    key_rx = 0
                    key_tx = 0
                    prev = None

                    for snap in snapshots:
                        if prev is not None:
                            delta_rx = snap.bytes_received - prev.bytes_received
                            delta_tx = snap.bytes_sent - prev.bytes_sent

                            # Handle counter reset
                            if delta_rx < 0:
                                delta_rx = snap.bytes_received
                            if delta_tx < 0:
                                delta_tx = snap.bytes_sent

                            key_rx += delta_rx
                            key_tx += delta_tx

                        prev = snap

                    # Get last connection time for this key
                    last_conn = None
                    if snapshots:
                        last_snap = snapshots[-1]
                        if last_snap.last_connection:
                            last_conn = last_snap.last_connection.isoformat()

                    keys_traffic.append({
                        "key_id": key.id,
                        "key_name": key.key_name,
                        "bytes_received": key_rx,
                        "bytes_sent": key_tx,
                        "total": key_rx + key_tx,
                        "last_connection": last_conn,
                        "is_active": key.is_active,
                    })

                    total_received += key_rx
                    total_sent += key_tx

                return {
                    "user_id": user_id,
                    "total_received": total_received,
                    "total_sent": total_sent,
                    "total": total_received + total_sent,
                    "keys": keys_traffic,
                }

        except Exception as e:
            logger.error("Error getting user traffic for user_id=%d: %s", user_id, e)
            return {
                "user_id": user_id,
                "total_received": 0,
                "total_sent": 0,
                "total": 0,
                "keys": [],
            }

    # ──────────────────────────────────────────────
    # All users traffic
    # ──────────────────────────────────────────────

    @classmethod
    def get_all_users_traffic(cls) -> list[dict]:
        """
        Get traffic statistics for all users this month.

        Returns a list of dicts sorted by total traffic descending:
            - user_id
            - telegram_id
            - username
            - first_name
            - last_name
            - nickname
            - total_received (bytes)
            - total_sent (bytes)
            - total (bytes)
            - keys_count
        """
        try:
            with get_db_session() as session:
                now = datetime.now()
                month_start = datetime(now.year, now.month, 1)

                # Get all active users who have VPN keys
                users = (
                    session.query(User)
                    .filter(User.is_deleted == False)
                    .all()
                )

                users_traffic = []

                for user in users:
                    # Get user's keys
                    user_keys = (
                        session.query(VPNKey)
                        .filter(VPNKey.user_id == user.id)
                        .all()
                    )

                    if not user_keys:
                        continue

                    user_total_rx = 0
                    user_total_tx = 0
                    active_keys = 0

                    for key in user_keys:
                        if key.is_active:
                            active_keys += 1

                        # Get snapshots for this key this month
                        snapshots = (
                            session.query(
                                TrafficStatistic.bytes_received,
                                TrafficStatistic.bytes_sent,
                            )
                            .filter(
                                TrafficStatistic.vpn_key_id == key.id,
                                TrafficStatistic.timestamp >= month_start,
                            )
                            .order_by(TrafficStatistic.timestamp)
                            .all()
                        )

                        # Compute deltas
                        prev = None
                        for snap in snapshots:
                            if prev is not None:
                                delta_rx = snap.bytes_received - prev.bytes_received
                                delta_tx = snap.bytes_sent - prev.bytes_sent

                                if delta_rx < 0:
                                    delta_rx = snap.bytes_received
                                if delta_tx < 0:
                                    delta_tx = snap.bytes_sent

                                user_total_rx += delta_rx
                                user_total_tx += delta_tx

                            prev = snap

                    total = user_total_rx + user_total_tx

                    users_traffic.append({
                        "user_id": user.id,
                        "telegram_id": user.telegram_id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "nickname": user.nickname,
                        "total_received": user_total_rx,
                        "total_sent": user_total_tx,
                        "total": total,
                        "keys_count": active_keys,
                    })

                # Sort by total traffic descending
                users_traffic.sort(key=lambda x: x["total"], reverse=True)
                return users_traffic

        except Exception as e:
            logger.error("Error getting all users traffic: %s", e)
            return []

    # ──────────────────────────────────────────────
    # Format bytes
    # ──────────────────────────────────────────────

    @staticmethod
    def format_bytes(bytes_val: int) -> str:
        """
        Format bytes to a human-readable string.

        Examples:
            0         -> '0 B'
            1023      -> '1023 B'
            1024      -> '1.00 KB'
            1048576   -> '1.00 MB'
            1073741824 -> '1.00 GB'
        """
        if bytes_val < 0:
            return f"-{TrafficManager.format_bytes(-bytes_val)}"

        if bytes_val == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        value = float(bytes_val)

        while value >= 1024.0 and unit_index < len(units) - 1:
            value /= 1024.0
            unit_index += 1

        if unit_index == 0:
            return f"{int(value)} B"

        return f"{value:.2f} {units[unit_index]}"

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    @classmethod
    def _compute_traffic_totals(
        cls, session, start_date: date, end_date: date
    ) -> tuple[int, int]:
        """
        Compute total delta-based traffic (received, sent) across all keys
        for snapshots whose date falls within [start_date, end_date].

        WireGuard counters are cumulative, so we calculate deltas between
        consecutive snapshots per key and sum them up.

        Returns (total_received, total_sent).
        """
        total_received = 0
        total_sent = 0

        try:
            # Get all key IDs that have traffic in this period
            key_ids = (
                session.query(TrafficStatistic.vpn_key_id)
                .filter(
                    TrafficStatistic.date >= start_date,
                    TrafficStatistic.date <= end_date,
                )
                .distinct()
                .all()
            )

            for (key_id,) in key_ids:
                snapshots = (
                    session.query(
                        TrafficStatistic.bytes_received,
                        TrafficStatistic.bytes_sent,
                    )
                    .filter(
                        TrafficStatistic.vpn_key_id == key_id,
                        TrafficStatistic.date >= start_date,
                        TrafficStatistic.date <= end_date,
                    )
                    .order_by(TrafficStatistic.timestamp)
                    .all()
                )

                prev = None
                for snap in snapshots:
                    if prev is not None:
                        delta_rx = snap.bytes_received - prev.bytes_received
                        delta_tx = snap.bytes_sent - prev.bytes_sent

                        # Handle counter reset (WG restart)
                        if delta_rx < 0:
                            delta_rx = snap.bytes_received
                        if delta_tx < 0:
                            delta_tx = snap.bytes_sent

                        total_received += delta_rx
                        total_sent += delta_tx

                    prev = snap

        except Exception as e:
            logger.error("Error computing traffic totals: %s", e)

        return total_received, total_sent
