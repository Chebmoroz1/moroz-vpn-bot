"""Модуль для получения статистики трафика из WireGuard"""
import json
import logging
import re
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from vpn_manager import vpn_manager
from database import get_db_session, VPNKey, TrafficStatistics

logger = logging.getLogger(__name__)


class TrafficManager:
    """Менеджер для работы со статистикой трафика"""
    
    def __init__(self):
        self.vpn_manager = vpn_manager
    
    def get_wireguard_stats(self) -> Dict[str, Dict]:
        """
        Получение статистики трафика из WireGuard
        
        Returns:
            Словарь вида {public_key: {bytes_received, bytes_sent, last_handshake, endpoint}}
        """
        try:
            # Выполняем команду wg show wg0 dump для получения полной статистики
            # Используем локальный docker exec, если доступен, иначе SSH
            if hasattr(self.vpn_manager, '_docker_exec_local'):
                # Локальный режим - используем прямой docker exec
                stdout, stderr, exit_code = self.vpn_manager._docker_exec_local(
                    f"wg show {self.vpn_manager.vpn_interface} dump"
                )
            else:
                # Удаленный режим - используем SSH
                stdout, stderr, exit_code = self.vpn_manager._ssh_exec(
                    f"wg show {self.vpn_manager.vpn_interface} dump",
                    docker_exec=True
                )
            
            if exit_code != 0:
                logger.error(f"Failed to get WireGuard stats: {stderr}")
                return {}
            
            stats = {}
            
            # Формат вывода wg dump:
            # public_key | private_key | preshared_key | endpoint | allowed_ips | last_handshake | transfer_rx | transfer_tx | persistent_keepalive
            # Все поля разделены табуляцией
            
            for line in stdout.strip().split('\n'):
                if not line.strip():
                    continue
                
                parts = line.split('\t')
                # Минимум нужно 6 полей: public_key, private_key, preshared_key, endpoint, allowed_ips, last_handshake
                if len(parts) < 6:
                    continue
                
                public_key = parts[0]
                # Пропускаем серверный ключ (у него есть private_key во втором поле)
                if len(parts) > 1 and parts[1] and parts[1] != '(none)' and parts[1].strip():
                    # Это серверный ключ, пропускаем
                    continue
                
                # Формат для клиентских ключей: public_key | (none) | endpoint | allowed_ips | last_handshake | transfer_rx | transfer_tx | persistent_keepalive
                # Для серверного ключа: public_key | private_key | preshared_key | endpoint | allowed_ips | last_handshake | transfer_rx | transfer_tx
                # Определяем формат по наличию private_key
                if len(parts) > 1 and parts[1] and parts[1] != '(none)' and parts[1].strip():
                    # Серверный ключ - пропускаем
                    continue
                
                # Клиентский ключ: public_key | (none) | endpoint | allowed_ips | last_handshake | transfer_rx | transfer_tx
                endpoint = parts[2] if len(parts) > 2 and parts[2] != '(none)' else None
                allowed_ips = parts[3] if len(parts) > 3 else ''
                last_handshake_str = parts[4] if len(parts) > 4 else '0'  # last_handshake в поле 5 (индекс 4)
                transfer_rx = parts[5] if len(parts) > 5 else '0'  # transfer_rx в поле 6 (индекс 5)
                transfer_tx = parts[6] if len(parts) > 6 else '0'  # transfer_tx в поле 7 (индекс 6)
                
                # Парсим last_handshake (секунды с эпохи Unix, или 0 если не было подключения)
                last_handshake = None
                if last_handshake_str and last_handshake_str != '0':
                    try:
                        timestamp = int(last_handshake_str)
                        # Проверяем, что timestamp разумный (не раньше 2000 года и не в будущем)
                        min_timestamp = 946684800  # 2000-01-01 00:00:00 UTC
                        max_timestamp = int(datetime.now().timestamp()) + 3600  # Текущее время + 1 час
                        
                        if min_timestamp <= timestamp <= max_timestamp:
                            last_handshake = datetime.fromtimestamp(timestamp)
                        else:
                            # Если timestamp неразумный, считаем что подключения не было
                            logger.debug(f"Invalid timestamp {timestamp} for key {public_key[:20]}...")
                            last_handshake = None
                    except (ValueError, OSError) as e:
                        logger.debug(f"Error parsing timestamp {last_handshake_str}: {e}")
                        pass
                
                # Парсим трафик (в байтах)
                bytes_received = 0
                bytes_sent = 0
                
                if transfer_rx:
                    try:
                        bytes_received = int(transfer_rx)
                    except ValueError:
                        pass
                
                if transfer_tx:
                    try:
                        bytes_sent = int(transfer_tx)
                    except ValueError:
                        pass
                
                # Извлекаем IP адрес из endpoint (если есть)
                ip_address = None
                if endpoint:
                    # Формат: IP:PORT
                    ip_match = re.match(r'^(\d+\.\d+\.\d+\.\d+):', endpoint)
                    if ip_match:
                        ip_address = ip_match.group(1)
                
                stats[public_key] = {
                    'bytes_received': bytes_received,
                    'bytes_sent': bytes_sent,
                    'last_handshake': last_handshake,
                    'endpoint': endpoint,
                    'ip_address': ip_address,
                    'allowed_ips': allowed_ips
                }
            
            logger.info(f"Retrieved stats for {len(stats)} WireGuard peers")
            return stats
        
        except Exception as e:
            logger.error(f"Error getting WireGuard stats: {e}", exc_info=True)
            return {}
    
    def sync_traffic_stats(self, target_date: Optional[date] = None, create_snapshot: bool = True) -> Dict[str, int]:
        """
        Синхронизация статистики трафика с WireGuard и сохранение snapshot в БД
        
        Args:
            target_date: Дата для статистики (по умолчанию - сегодня)
            create_snapshot: Если True, создает новую запись (snapshot), иначе обновляет последнюю
            
        Returns:
            Словарь с результатами: {'updated': count, 'created': count, 'errors': count}
        """
        if target_date is None:
            target_date = date.today()
        
        # Получаем статистику из WireGuard
        wg_stats = self.get_wireguard_stats()
        
        if not wg_stats:
            logger.warning("No WireGuard stats retrieved")
            return {'updated': 0, 'created': 0, 'errors': 0}
        
        db = get_db_session()
        results = {'updated': 0, 'created': 0, 'errors': 0}
        snapshot_timestamp = datetime.now()
        
        try:
            # Получаем все активные ключи
            vpn_keys = db.query(VPNKey).filter(VPNKey.is_active == True).all()
            
            # Создаем словарь для быстрого поиска по public_key (нормализованному)
            keys_by_public_key = {}
            for key in vpn_keys:
                if key.public_key:
                    normalized_key = key.public_key.strip()
                    keys_by_public_key[normalized_key] = key
            
            # Обрабатываем каждый ключ
            for public_key, wg_stat in wg_stats.items():
                normalized_wg_key = public_key.strip()
                
                if normalized_wg_key not in keys_by_public_key:
                    logger.debug(f"Key not found in DB (might be server key): {normalized_wg_key[:20]}...")
                    continue
                
                vpn_key = keys_by_public_key[normalized_wg_key]
                
                try:
                    if create_snapshot:
                        # Создаем новый snapshot (новая запись каждые 15 минут)
                        # Получаем последний snapshot для этого ключа для IP адресов
                        last_snapshot = db.query(TrafficStatistics).filter(
                            TrafficStatistics.vpn_key_id == vpn_key.id
                        ).order_by(TrafficStatistics.timestamp.desc()).first()
                        
                        ip_addresses = []
                        if last_snapshot and last_snapshot.connection_ips:
                            try:
                                ip_addresses = json.loads(last_snapshot.connection_ips)
                            except (json.JSONDecodeError, TypeError):
                                ip_addresses = []
                        
                        # Добавляем новый IP адрес, если есть
                        if wg_stat.get('ip_address') and wg_stat['ip_address'] not in ip_addresses:
                            ip_addresses.append(wg_stat['ip_address'])
                            ip_addresses = ip_addresses[-10:]  # Оставляем последние 10
                        
                        # Создаем новый snapshot
                        traffic_stat = TrafficStatistics(
                            vpn_key_id=vpn_key.id,
                            date=target_date,
                            timestamp=snapshot_timestamp,
                            bytes_received=wg_stat['bytes_received'],
                            bytes_sent=wg_stat['bytes_sent'],
                            last_connection=wg_stat['last_handshake'],
                            connection_ips=json.dumps(ip_addresses) if ip_addresses else None
                        )
                        db.add(traffic_stat)
                        results['created'] += 1
                    else:
                        # Обновляем последнюю запись (старый режим для совместимости)
                        traffic_stat = db.query(TrafficStatistics).filter(
                            TrafficStatistics.vpn_key_id == vpn_key.id,
                            TrafficStatistics.date == target_date
                        ).order_by(TrafficStatistics.timestamp.desc()).first()
                        
                        if traffic_stat:
                            ip_addresses = []
                            if traffic_stat.connection_ips:
                                try:
                                    ip_addresses = json.loads(traffic_stat.connection_ips)
                                except (json.JSONDecodeError, TypeError):
                                    ip_addresses = []
                            
                            if wg_stat.get('ip_address') and wg_stat['ip_address'] not in ip_addresses:
                                ip_addresses.append(wg_stat['ip_address'])
                                ip_addresses = ip_addresses[-10:]
                            
                            traffic_stat.bytes_received = wg_stat['bytes_received']
                            traffic_stat.bytes_sent = wg_stat['bytes_sent']
                            traffic_stat.last_connection = wg_stat['last_handshake']
                            traffic_stat.connection_ips = json.dumps(ip_addresses) if ip_addresses else None
                            traffic_stat.updated_at = datetime.now()
                            results['updated'] += 1
                        else:
                            # Создаем новую запись, если нет
                            traffic_stat = TrafficStatistics(
                                vpn_key_id=vpn_key.id,
                                date=target_date,
                                timestamp=snapshot_timestamp,
                                bytes_received=wg_stat['bytes_received'],
                                bytes_sent=wg_stat['bytes_sent'],
                                last_connection=wg_stat['last_handshake'],
                                connection_ips=json.dumps(ip_addresses) if ip_addresses else None
                            )
                            db.add(traffic_stat)
                            results['created'] += 1
                    
                except Exception as e:
                    logger.error(f"Error syncing traffic stat for key {vpn_key.id}: {e}", exc_info=True)
                    results['errors'] += 1
            
            db.commit()
            logger.info(f"Traffic stats synced: {results} (snapshots: {create_snapshot})")
            
        except Exception as e:
            logger.error(f"Error syncing traffic stats: {e}", exc_info=True)
            db.rollback()
            results['errors'] += 1
        finally:
            db.close()
        
        return results
    
    def get_traffic_stats_by_period(
        self, 
        start_date: date, 
        end_date: date,
        user_id: Optional[int] = None,
        vpn_key_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Получение статистики трафика за период
        
        Args:
            start_date: Начальная дата
            end_date: Конечная дата
            user_id: ID пользователя (опционально)
            vpn_key_id: ID ключа (опционально)
            
        Returns:
            Список словарей со статистикой
        """
        db = get_db_session()
        try:
            query = db.query(TrafficStatistics, VPNKey).join(VPNKey)
            
            # Фильтруем по дате
            query = query.filter(
                TrafficStatistics.date >= start_date,
                TrafficStatistics.date <= end_date
            )
            
            # Фильтруем по пользователю, если указан
            if user_id:
                query = query.filter(VPNKey.user_id == user_id)
            
            # Фильтруем по ключу, если указан
            if vpn_key_id:
                query = query.filter(VPNKey.id == vpn_key_id)
            
            # Группируем по ключу и суммируем трафик
            from sqlalchemy import func
            results = query.with_entities(
                VPNKey.id.label('vpn_key_id'),
                VPNKey.key_name,
                VPNKey.user_id,
                func.sum(TrafficStatistics.bytes_received).label('total_received'),
                func.sum(TrafficStatistics.bytes_sent).label('total_sent'),
                func.max(TrafficStatistics.last_connection).label('last_connection'),
                func.max(TrafficStatistics.connection_ips).label('connection_ips')
            ).group_by(VPNKey.id, VPNKey.key_name, VPNKey.user_id).all()
            
            stats_list = []
            for row in results:
                ip_addresses = []
                if row.connection_ips:
                    try:
                        ip_addresses = json.loads(row.connection_ips)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                stats_list.append({
                    'vpn_key_id': row.vpn_key_id,
                    'key_name': row.key_name,
                    'user_id': row.user_id,
                    'bytes_received': row.total_received or 0,
                    'bytes_sent': row.total_sent or 0,
                    'bytes_total': (row.total_received or 0) + (row.total_sent or 0),
                    'last_connection': row.last_connection,
                    'connection_ips': ip_addresses
                })
            
            return stats_list
        
        except Exception as e:
            logger.error(f"Error getting traffic stats by period: {e}", exc_info=True)
            return []
        finally:
            db.close()
    
    def get_current_month_stats(self, user_id: Optional[int] = None) -> List[Dict]:
        """
        Получение статистики за текущий месяц
        
        Args:
            user_id: ID пользователя (опционально)
            
        Returns:
            Список словарей со статистикой
        """
        today = date.today()
        start_date = date(today.year, today.month, 1)
        end_date = today
        
        return self.get_traffic_stats_by_period(start_date, end_date, user_id=user_id)
    
    def format_bytes(self, bytes_value: int) -> str:
        """
        Форматирование байтов в человекочитаемый формат
        
        Args:
            bytes_value: Количество байтов
            
        Returns:
            Отформатированная строка (например, "1.5 GB")
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024.0:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024.0
        return f"{bytes_value:.2f} PB"
    
    def get_active_connections_count(self) -> int:
        """
        Получение количества активных подключений
        Peer считается активным, если last_handshake был менее 5 минут назад
        
        Returns:
            Количество активных подключений
        """
        try:
            wg_stats = self.get_wireguard_stats()
            now = datetime.now()
            active_count = 0
            
            for public_key, stat in wg_stats.items():
                if stat.get('last_handshake'):
                    time_diff = (now - stat['last_handshake']).total_seconds()
                    if time_diff < 300:  # 5 минут
                        active_count += 1
            
            return active_count
        except Exception as e:
            logger.error(f"Error getting active connections count: {e}", exc_info=True)
            return 0
    
    def get_monthly_traffic(self) -> Dict[str, int]:
        """
        Получение трафика за текущий календарный месяц
        
        Returns:
            Словарь с трафиком: {'received': int, 'sent': int, 'total': int}
        """
        try:
            today = date.today()
            start_date = date(today.year, today.month, 1)
            end_date = today
            
            stats = self.get_traffic_stats_by_period(start_date, end_date)
            
            total_received = sum(s['bytes_received'] for s in stats)
            total_sent = sum(s['bytes_sent'] for s in stats)
            total = total_received + total_sent
            
            return {
                'received': total_received,
                'sent': total_sent,
                'total': total
            }
        except Exception as e:
            logger.error(f"Error getting monthly traffic: {e}", exc_info=True)
            return {'received': 0, 'sent': 0, 'total': 0}
    
    def get_chart_data(
        self, 
        period: str = '6hours',
        vpn_key_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Получение данных для графика трафика из snapshots с вычислением разницы
        
        Args:
            period: Период ('6hours', 'day', 'week', 'month')
            Интервалы группировки:
            - 6hours: 15 минут
            - day: 1 час
            - week: 3 часа
            - month: 1 день
            vpn_key_id: ID ключа для фильтрации (опционально)
            user_id: ID пользователя для фильтрации (опционально)
            
        Returns:
            Список словарей с данными для графика
        """
        try:
            now = datetime.now()
            end_date = date.today()
            
            # Определяем параметры периода
            if period == '6hours':
                start_datetime = now - timedelta(hours=6)
                interval_minutes = 15
            elif period == 'day':
                start_datetime = datetime.combine(end_date, datetime.min.time())
                interval_minutes = 60
            elif period == 'week':
                start_datetime = datetime.combine(end_date - timedelta(days=6), datetime.min.time())
                interval_minutes = 180
            elif period == 'month':
                start_datetime = datetime.combine(date(end_date.year, end_date.month, 1), datetime.min.time())
                interval_minutes = 1440
            else:
                start_datetime = now - timedelta(hours=6)
                interval_minutes = 15
            
            return self._get_chart_data_from_snapshots(
                start_datetime, 
                now, 
                interval_minutes, 
                period,
                vpn_key_id,
                user_id
            )
                
        except Exception as e:
            logger.error(f"Error getting chart data: {e}", exc_info=True)
            return []
    
    def _get_chart_data_from_snapshots(
        self,
        start_datetime: datetime,
        end_datetime: datetime,
        interval_minutes: int,
        period: str,
        vpn_key_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Получение данных для графика из snapshots с вычислением разницы между соседними snapshots
        
        Args:
            start_datetime: Начало периода
            end_datetime: Конец периода (обычно текущее время)
            interval_minutes: Интервал группировки в минутах
            period: Период для форматирования меток
            vpn_key_id: ID ключа для фильтрации
            user_id: ID пользователя для фильтрации
            
        Returns:
            Список словарей с данными для графика
        """
        try:
            db = get_db_session()
            try:
                from sqlalchemy import func, and_, or_
                from database import User
                
                # Получаем все snapshots за период
                query = db.query(
                    TrafficStatistics.vpn_key_id,
                    TrafficStatistics.timestamp,
                    TrafficStatistics.bytes_received,
                    TrafficStatistics.bytes_sent
                ).join(VPNKey)
                
                # Фильтруем по периоду
                query = query.filter(
                    TrafficStatistics.timestamp >= start_datetime,
                    TrafficStatistics.timestamp <= end_datetime
                )
                
                # Фильтруем по ключу, если указан
                if vpn_key_id:
                    query = query.filter(TrafficStatistics.vpn_key_id == vpn_key_id)
                
                # Фильтруем по пользователю, если указан
                if user_id:
                    query = query.join(User, VPNKey.user_id == User.id).filter(User.id == user_id)
                
                # Сортируем по времени
                query = query.order_by(TrafficStatistics.timestamp.asc())
                
                results = query.all()
                
                if not results:
                    return []
                
                # Группируем snapshots по интервалам
                # Для каждого интервала берем последний snapshot каждого ключа
                # Создаем словарь: {interval_start: {vpn_key_id: {received, sent, timestamp}}}
                snapshots_by_interval = defaultdict(lambda: {})
                
                for row in results:
                    # Округляем timestamp до интервала
                    timestamp = row.timestamp
                    if isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        except:
                            timestamp = datetime.fromisoformat(timestamp)
                    
                    # Округляем до интервала
                    minutes = (timestamp.minute // interval_minutes) * interval_minutes
                    interval_start = timestamp.replace(minute=minutes, second=0, microsecond=0)
                    
                    # Сохраняем последний snapshot для каждого ключа в интервале
                    key_id = row.vpn_key_id
                    if key_id not in snapshots_by_interval[interval_start] or \
                       snapshots_by_interval[interval_start][key_id]['timestamp'] < timestamp:
                        snapshots_by_interval[interval_start][key_id] = {
                            'received': row.bytes_received or 0,
                            'sent': row.bytes_sent or 0,
                            'timestamp': timestamp
                        }
                
                # Сначала получаем начальные значения для каждого ключа (из первого snapshot)
                # Это нужно для правильного вычисления разницы
                first_snapshot_time = min(snapshots_by_interval.keys()) if snapshots_by_interval else None
                initial_key_data = defaultdict(lambda: {'received': 0, 'sent': 0})
                
                if first_snapshot_time:
                    # Находим самый первый snapshot для каждого ключа во всем периоде
                    for row in results:
                        key_id = row.vpn_key_id
                        if key_id not in initial_key_data:
                            # Ищем первый snapshot этого ключа
                            first_snapshot = db.query(TrafficStatistics).filter(
                                TrafficStatistics.vpn_key_id == key_id,
                                TrafficStatistics.timestamp < start_datetime
                            ).order_by(TrafficStatistics.timestamp.desc()).first()
                            
                            if first_snapshot:
                                initial_key_data[key_id] = {
                                    'received': first_snapshot.bytes_received or 0,
                                    'sent': first_snapshot.bytes_sent or 0
                                }
                
                # Генерируем интервалы для графика
                chart_data = []
                current_interval = start_datetime.replace(
                    minute=(start_datetime.minute // interval_minutes) * interval_minutes,
                    second=0,
                    microsecond=0
                )
                
                # Храним последние значения для каждого ключа (начинаем с начальных)
                prev_key_data = initial_key_data.copy()
                
                while current_interval <= end_datetime:
                    # Получаем snapshots для этого интервала
                    interval_snapshots = snapshots_by_interval.get(current_interval, {})
                    
                    # Вычисляем трафик за интервал (разница между текущим и предыдущим snapshot)
                    interval_received = 0
                    interval_sent = 0
                    
                    # Для каждого ключа в интервале вычисляем разницу
                    for key_id, snapshot_data in interval_snapshots.items():
                        # Вычисляем разницу от предыдущего значения этого ключа
                        key_received = max(0, snapshot_data['received'] - prev_key_data[key_id]['received'])
                        key_sent = max(0, snapshot_data['sent'] - prev_key_data[key_id]['sent'])
                        
                        interval_received += key_received
                        interval_sent += key_sent
                        
                        # Обновляем предыдущие значения для этого ключа
                        prev_key_data[key_id] = {
                            'received': snapshot_data['received'],
                            'sent': snapshot_data['sent']
                        }
                    
                    # Форматируем метку в зависимости от периода
                    if period == '6hours':
                        if current_interval.date() == end_datetime.date():
                            label = current_interval.strftime('%H:%M')
                        else:
                            label = current_interval.strftime('%d.%m %H:%M')
                    elif period == 'day':
                        label = current_interval.strftime('%H:00')
                    elif period == 'week':
                        label = current_interval.strftime('%d.%m %H:00')
                    elif period == 'month':
                        label = current_interval.strftime('%d.%m')
                    else:
                        label = current_interval.strftime('%H:%M')
                    
                    chart_data.append({
                        'timestamp': current_interval.isoformat(),
                        'label': label,
                        'received': interval_received,
                        'sent': interval_sent,
                        'total': interval_received + interval_sent
                    })
                    
                    # Переходим к следующему интервалу
                    current_interval += timedelta(minutes=interval_minutes)
                
                return chart_data
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting chart data from snapshots: {e}", exc_info=True)
            return []
    
    def _get_chart_data_from_wireguard_with_diff(self, period: str, now: datetime, end_date: date) -> List[Dict]:
        """
        Получение данных для графика из WireGuard с вычислением разницы от начала дня
        Используется для коротких периодов (6 часов, сутки)
        """
        try:
            # Получаем текущие данные из WireGuard
            wg_stats = self.get_wireguard_stats()
            current_total_received = sum(stat.get('bytes_received', 0) for stat in wg_stats.values())
            current_total_sent = sum(stat.get('bytes_sent', 0) for stat in wg_stats.values())
            
            # Получаем данные за начало дня из БД (базовая точка)
            db = get_db_session()
            try:
                from sqlalchemy import func
                
                # Пытаемся получить данные за сегодня из БД (если они есть, это накопительные значения)
                today_stats = db.query(
                    func.sum(TrafficStatistics.bytes_received).label('received'),
                    func.sum(TrafficStatistics.bytes_sent).label('sent')
                ).join(VPNKey).filter(
                    TrafficStatistics.date == end_date
                ).first()
                
                # Если данных за сегодня нет, используем данные за вчера как базовую точку
                if not today_stats or (today_stats.received == 0 and today_stats.sent == 0):
                    yesterday = end_date - timedelta(days=1)
                    yesterday_stats = db.query(
                        func.sum(TrafficStatistics.bytes_received).label('received'),
                        func.sum(TrafficStatistics.bytes_sent).label('sent')
                    ).join(VPNKey).filter(
                        TrafficStatistics.date == yesterday
                    ).first()
                    
                    if yesterday_stats:
                        base_received = yesterday_stats.received or 0
                        base_sent = yesterday_stats.sent or 0
                    else:
                        # Если нет данных за вчера, считаем что трафик начался с нуля сегодня
                        base_received = 0
                        base_sent = 0
                else:
                    # Используем данные за сегодня как базовую точку (они могут быть устаревшими)
                    # Но лучше использовать данные за вчера, если они есть
                    yesterday = end_date - timedelta(days=1)
                    yesterday_stats = db.query(
                        func.sum(TrafficStatistics.bytes_received).label('received'),
                        func.sum(TrafficStatistics.bytes_sent).label('sent')
                    ).join(VPNKey).filter(
                        TrafficStatistics.date == yesterday
                    ).first()
                    
                    if yesterday_stats:
                        base_received = yesterday_stats.received or 0
                        base_sent = yesterday_stats.sent or 0
                    else:
                        base_received = today_stats.received or 0
                        base_sent = today_stats.sent or 0
                
            finally:
                db.close()
            
            # Вычисляем трафик за сегодня (разница между текущим значением и базовой точкой)
            today_traffic_received = max(0, current_total_received - base_received)
            today_traffic_sent = max(0, current_total_sent - base_sent)
            
            chart_data = []
            
            if period == '6hours':
                # Генерируем интервалы по 15 минут за последние 6 часов
                current_interval = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
                start_interval = current_interval - timedelta(hours=6)
                
                # Вычисляем трафик за последние 6 часов
                # Предполагаем, что трафик распределен равномерно в течение дня
                # Используем пропорцию: трафик за 6 часов = (трафик за день) * (6 часов / часы с начала дня)
                day_start = datetime.combine(end_date, datetime.min.time())
                hours_from_day_start = (now - day_start).total_seconds() / 3600
                
                if hours_from_day_start > 0:
                    # Вычисляем трафик за последние 6 часов пропорционально времени
                    # Если прошло меньше 6 часов с начала дня, используем весь трафик за сегодня
                    hours_in_period = min(6.0, hours_from_day_start)
                    traffic_ratio = hours_in_period / hours_from_day_start if hours_from_day_start > 0 else 1.0
                    period_traffic_received = int(today_traffic_received * traffic_ratio)
                    period_traffic_sent = int(today_traffic_sent * traffic_ratio)
                else:
                    period_traffic_received = 0
                    period_traffic_sent = 0
                
                # Распределяем трафик за период равномерно по интервалам
                intervals_count = 24  # 6 часов * 4 интервала в час
                received_per_interval = period_traffic_received / intervals_count if intervals_count > 0 else 0
                sent_per_interval = period_traffic_sent / intervals_count if intervals_count > 0 else 0
                
                interval = start_interval
                for i in range(intervals_count):
                    # Если интервал в будущем, трафик = 0
                    if interval > now:
                        received = 0
                        sent = 0
                    else:
                        received = int(received_per_interval)
                        sent = int(sent_per_interval)
                    
                    # Форматируем метку
                    if interval.date() == now.date():
                        label = interval.strftime('%H:%M')
                    else:
                        label = interval.strftime('%d.%m %H:%M')
                    
                    chart_data.append({
                        'timestamp': interval.isoformat(),
                        'label': label,
                        'received': received,
                        'sent': sent,
                        'total': received + sent
                    })
                    interval += timedelta(minutes=15)
                    
            elif period == 'day':
                # Генерируем интервалы по 1 часу за сутки
                start_interval = datetime.combine(end_date, datetime.min.time())
                end_interval = datetime.combine(end_date, datetime.max.time())
                
                # Вычисляем, сколько времени прошло с начала дня
                day_start = datetime.combine(end_date, datetime.min.time())
                hours_from_day_start = (now - day_start).total_seconds() / 3600
                
                current = start_interval
                prev_hour_traffic_received = 0
                prev_hour_traffic_sent = 0
                
                while current <= end_interval:
                    # Вычисляем, сколько времени прошло с начала дня до этого часа
                    hour_from_start = (current - day_start).total_seconds() / 3600
                    
                    # Если час в будущем, трафик = 0
                    if current > now:
                        received = 0
                        sent = 0
                    else:
                        # Распределяем трафик пропорционально времени
                        if hours_from_day_start > 0:
                            # Трафик до этого часа пропорционален времени
                            traffic_ratio = min(1.0, hour_from_start / hours_from_day_start)
                            
                            # Вычисляем накопительный трафик до этого часа
                            cumulative_received = int(today_traffic_received * traffic_ratio)
                            cumulative_sent = int(today_traffic_sent * traffic_ratio)
                            
                            # Вычисляем трафик за этот час как разницу
                            received = max(0, cumulative_received - prev_hour_traffic_received)
                            sent = max(0, cumulative_sent - prev_hour_traffic_sent)
                            
                            prev_hour_traffic_received = cumulative_received
                            prev_hour_traffic_sent = cumulative_sent
                        else:
                            received = 0
                            sent = 0
                            prev_hour_traffic_received = 0
                            prev_hour_traffic_sent = 0
                    
                    chart_data.append({
                        'timestamp': current.isoformat(),
                        'label': current.strftime('%H:00'),
                        'received': received,
                        'sent': sent,
                        'total': received + sent
                    })
                    current += timedelta(hours=1)
            
            return chart_data
            
        except Exception as e:
            logger.error(f"Error getting chart data from WireGuard with diff: {e}", exc_info=True)
            return []
    
    def _get_chart_data_from_db_with_diff(self, period: str, end_date: date, now: datetime) -> List[Dict]:
        """
        Получение данных для графика из БД (для длительных периодов)
        Вычисляет разницу между днями для получения трафика за каждый день
        """
        try:
            db = get_db_session()
            try:
                from sqlalchemy import func
                
                # Определяем период (только для week и month, day и 6hours обрабатываются в другом методе)
                if period == 'week':
                    start_date = end_date - timedelta(days=6)
                elif period == 'month':
                    start_date = date(end_date.year, end_date.month, 1)
                else:
                    # Не должно попасть сюда для day и 6hours
                    logger.warning(f"Unexpected period in _get_chart_data_from_db_with_diff: {period}")
                    return []
                
                # Получаем данные за период, группированные по дате
                query = db.query(
                    TrafficStatistics.date,
                    func.sum(TrafficStatistics.bytes_received).label('received'),
                    func.sum(TrafficStatistics.bytes_sent).label('sent')
                ).join(VPNKey).filter(
                    TrafficStatistics.date >= start_date,
                    TrafficStatistics.date <= end_date
                ).group_by(TrafficStatistics.date).order_by(TrafficStatistics.date.asc())
                
                results = query.all()
                
                # Создаем словарь данных по датам
                data_by_date = {}
                for row in results:
                    data_by_date[row.date] = {
                        'received': row.received or 0,
                        'sent': row.sent or 0
                    }
                
                chart_data = []
                
                if period == '6hours':
                    # Генерируем интервалы по 15 минут за последние 6 часов
                    current_interval = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
                    start_interval = current_interval - timedelta(hours=6)
                    
                    # Получаем данные за сегодня
                    today_data = data_by_date.get(end_date, {'received': 0, 'sent': 0})
                    total_received = today_data['received']
                    total_sent = today_data['sent']
                    
                    # Распределяем данные по интервалам с учетом времени суток
                    intervals_count = 24
                    interval = start_interval
                    
                    # Вычисляем сумму факторов для нормализации
                    total_factor = 0
                    factors = []
                    for i in range(intervals_count):
                        hour = interval.hour
                        # Больше трафика в дневное время (10-22 часа)
                        hour_factor = 0.2 + 0.8 * max(0, math.sin((hour - 6) * math.pi / 12))
                        factors.append(hour_factor)
                        total_factor += hour_factor
                        interval += timedelta(minutes=15)
                    
                    # Распределяем трафик по интервалам
                    interval = start_interval
                    for i, factor in enumerate(factors):
                        if total_factor > 0:
                            received = int((total_received * factor) / total_factor)
                            sent = int((total_sent * factor) / total_factor)
                        else:
                            received = int(total_received / intervals_count)
                            sent = int(total_sent / intervals_count)
                        
                        # Форматируем метку
                        if interval.date() == now.date():
                            label = interval.strftime('%H:%M')
                        else:
                            label = interval.strftime('%d.%m %H:%M')
                        
                        chart_data.append({
                            'timestamp': interval.isoformat(),
                            'label': label,
                            'received': received,
                            'sent': sent,
                            'total': received + sent
                        })
                        interval += timedelta(minutes=15)
                        
                elif period == 'week':
                    # Генерируем интервалы по 3 часа за неделю
                    # Вычисляем разницу между днями для получения реального трафика
                    start_interval = datetime.combine(start_date, datetime.min.time())
                    end_interval = datetime.combine(end_date, datetime.max.time())
                    
                    # Вычисляем трафик за каждый день (разница между днями)
                    daily_traffic = {}
                    prev_date = None
                    prev_received = 0
                    prev_sent = 0
                    
                    current_date = start_date
                    while current_date <= end_date:
                        day_data = data_by_date.get(current_date, {'received': 0, 'sent': 0})
                        current_received = day_data['received']
                        current_sent = day_data['sent']
                        
                        if prev_date is not None:
                            # Вычисляем разницу (трафик за день)
                            day_received = max(0, current_received - prev_received)
                            day_sent = max(0, current_sent - prev_sent)
                        else:
                            # Для первого дня используем текущее значение (если нет предыдущего дня)
                            # Или пытаемся получить данные за день раньше
                            day_before = current_date - timedelta(days=1)
                            day_before_stats = db.query(
                                func.sum(TrafficStatistics.bytes_received).label('received'),
                                func.sum(TrafficStatistics.bytes_sent).label('sent')
                            ).join(VPNKey).filter(
                                TrafficStatistics.date == day_before
                            ).first()
                            
                            if day_before_stats and (day_before_stats.received or day_before_stats.sent):
                                day_received = max(0, current_received - (day_before_stats.received or 0))
                                day_sent = max(0, current_sent - (day_before_stats.sent or 0))
                            else:
                                # Если нет данных за предыдущий день, используем текущее значение
                                day_received = current_received
                                day_sent = current_sent
                        
                        daily_traffic[current_date] = {
                            'received': day_received,
                            'sent': day_sent
                        }
                        
                        prev_date = current_date
                        prev_received = current_received
                        prev_sent = current_sent
                        current_date += timedelta(days=1)
                    
                    # Распределяем дневной трафик по 3-часовым интервалам (равномерно)
                    current = start_interval
                    while current <= end_interval:
                        current_date = current.date()
                        day_traffic = daily_traffic.get(current_date, {'received': 0, 'sent': 0})
                        
                        # В дне 8 интервалов по 3 часа, распределяем равномерно
                        received = int(day_traffic['received'] / 8)
                        sent = int(day_traffic['sent'] / 8)
                        
                        label = current.strftime('%d.%m %H:00')
                        
                        chart_data.append({
                            'timestamp': current.isoformat(),
                            'label': label,
                            'received': received,
                            'sent': sent,
                            'total': received + sent
                        })
                        current += timedelta(hours=3)
                        
                elif period == 'month':
                    # Генерируем интервалы по 1 дню за месяц
                    # Вычисляем разницу между днями для получения реального трафика
                    prev_date = None
                    prev_received = 0
                    prev_sent = 0
                    
                    current_date = start_date
                    while current_date <= end_date:
                        day_data = data_by_date.get(current_date, {'received': 0, 'sent': 0})
                        current_received = day_data['received']
                        current_sent = day_data['sent']
                        
                        if prev_date is not None:
                            # Вычисляем разницу (трафик за день)
                            day_received = max(0, current_received - prev_received)
                            day_sent = max(0, current_sent - prev_sent)
                        else:
                            # Для первого дня пытаемся получить данные за день раньше
                            day_before = current_date - timedelta(days=1)
                            day_before_stats = db.query(
                                func.sum(TrafficStatistics.bytes_received).label('received'),
                                func.sum(TrafficStatistics.bytes_sent).label('sent')
                            ).join(VPNKey).filter(
                                TrafficStatistics.date == day_before
                            ).first()
                            
                            if day_before_stats and (day_before_stats.received or day_before_stats.sent):
                                day_received = max(0, current_received - (day_before_stats.received or 0))
                                day_sent = max(0, current_sent - (day_before_stats.sent or 0))
                            else:
                                # Если нет данных за предыдущий день, используем текущее значение
                                day_received = current_received
                                day_sent = current_sent
                        
                        chart_data.append({
                            'timestamp': current_date.isoformat(),
                            'label': current_date.strftime('%d.%m'),
                            'received': day_received,
                            'sent': day_sent,
                            'total': day_received + day_sent
                        })
                        
                        prev_date = current_date
                        prev_received = current_received
                        prev_sent = current_sent
                        current_date += timedelta(days=1)
                
                return chart_data
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting chart data from DB: {e}", exc_info=True)
            return []
    
    def get_users_traffic_stats(
        self,
        period: str = 'month',
        search: Optional[str] = None,
        sort: str = 'traffic_desc',
        page: int = 1,
        limit: int = 20
    ) -> Dict:
        """
        Получение статистики трафика по пользователям с пагинацией
        
        Args:
            period: Период ('day', 'week', 'month', '30days')
            search: Поиск по имени/username
            sort: Сортировка ('traffic_desc', 'traffic_asc', 'keys', 'name')
            page: Номер страницы
            limit: Количество записей на странице
            
        Returns:
            Словарь с результатами и пагинацией
        """
        try:
            today = date.today()
            
            # Определяем период
            if period == 'day':
                start_date = end_date = today
            elif period == 'week':
                start_date = today - timedelta(days=6)
                end_date = today
            elif period == 'month':
                start_date = date(today.year, today.month, 1)
                end_date = today
            elif period == '30days':
                start_date = today - timedelta(days=29)
                end_date = today
            else:
                start_date = date(today.year, today.month, 1)
                end_date = today
            
            db = get_db_session()
            try:
                from sqlalchemy import func
                from database import User
                
                # Применяем поиск, если указан - сначала находим пользователей
                user_ids_filter = None
                if search:
                    search_users = db.query(User.id).filter(
                        (User.first_name.ilike(f'%{search}%')) |
                        (User.username.ilike(f'%{search}%')) |
                        (User.nickname.ilike(f'%{search}%'))
                    ).all()
                    user_ids_filter = [u.id for u in search_users]
                    if not user_ids_filter:
                        # Если поиск не дал результатов, возвращаем пустой список
                        return {'users': [], 'total': 0, 'page': 1, 'limit': limit, 'total_pages': 0}
                
                # Получаем статистику по пользователям
                query = db.query(
                    VPNKey.user_id,
                    func.sum(TrafficStatistics.bytes_received).label('total_received'),
                    func.sum(TrafficStatistics.bytes_sent).label('total_sent'),
                    func.count(func.distinct(VPNKey.id)).label('keys_count'),
                    func.max(TrafficStatistics.last_connection).label('last_connection')
                ).join(
                    TrafficStatistics, VPNKey.id == TrafficStatistics.vpn_key_id
                ).filter(
                    TrafficStatistics.date >= start_date,
                    TrafficStatistics.date <= end_date,
                    VPNKey.is_active == True
                )
                
                # Применяем фильтр по пользователям, если был поиск
                if user_ids_filter:
                    query = query.filter(VPNKey.user_id.in_(user_ids_filter))
                
                query = query.group_by(VPNKey.user_id)
                
                # Получаем общее количество для пагинации
                total_count = query.count()
                
                # Применяем сортировку
                if sort == 'traffic_desc':
                    query = query.order_by(
                        (func.sum(TrafficStatistics.bytes_received) + 
                         func.sum(TrafficStatistics.bytes_sent)).desc()
                    )
                elif sort == 'traffic_asc':
                    query = query.order_by(
                        (func.sum(TrafficStatistics.bytes_received) + 
                         func.sum(TrafficStatistics.bytes_sent)).asc()
                    )
                elif sort == 'keys':
                    query = query.order_by(func.count(func.distinct(VPNKey.id)).desc())
                # Для сортировки по имени нужно будет делать отдельный запрос
                
                # Применяем пагинацию
                offset = (page - 1) * limit
                results = query.offset(offset).limit(limit).all()
                
                # Получаем информацию о пользователях и активных ключах
                users_list = []
                # Получаем все user_id из результатов
                user_ids = [row.user_id for row in results]
                
                # Загружаем всех пользователей одним запросом
                users_dict = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}
                
                # Получаем статистику WireGuard один раз
                wg_stats = self.get_wireguard_stats()
                
                for row in results:
                    user = users_dict.get(row.user_id)
                    if not user:
                        continue
                    
                    # Подсчитываем активные ключи
                    active_keys_count = 0
                    user_keys = db.query(VPNKey).filter(
                        VPNKey.user_id == user.id,
                        VPNKey.is_active == True
                    ).all()
                    
                    for key in user_keys:
                        if key.public_key and key.public_key in wg_stats:
                            stat = wg_stats[key.public_key]
                            if stat.get('last_handshake'):
                                time_diff = (datetime.now() - stat['last_handshake']).total_seconds()
                                if time_diff < 300:  # 5 минут
                                    active_keys_count += 1
                    
                    total_traffic = (row.total_received or 0) + (row.total_sent or 0)
                    
                    users_list.append({
                        'user_id': user.id,
                        'user_name': user.nickname or user.first_name or user.username or f'User #{user.id}',
                        'username': user.username,
                        'nickname': user.nickname,
                        'is_admin': user.is_admin,
                        'total_traffic': total_traffic,
                        'received': row.total_received or 0,
                        'sent': row.total_sent or 0,
                        'keys_count': row.keys_count or 0,
                        'active_keys_count': active_keys_count,
                        'last_connection': row.last_connection
                    })
                
                # Если нужна сортировка по имени, делаем её на клиенте
                if sort == 'name':
                    users_list.sort(key=lambda x: x['user_name'].lower())
                
                total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1
                
                return {
                    'users': users_list,
                    'total': total_count,
                    'page': page,
                    'limit': limit,
                    'total_pages': total_pages
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting users traffic stats: {e}", exc_info=True)
            return {'users': [], 'total': 0, 'page': 1, 'limit': limit, 'total_pages': 0}
    
    def get_user_keys_traffic(
        self,
        user_id: int,
        period: str = 'month'
    ) -> Dict:
        """
        Получение детальной статистики по ключам пользователя
        
        Args:
            user_id: ID пользователя
            period: Период ('day', 'week', 'month', '30days')
            
        Returns:
            Словарь с детальной статистикой по пользователю и его ключам
        """
        try:
            today = date.today()
            
            # Определяем период
            if period == 'day':
                start_date = end_date = today
            elif period == 'week':
                start_date = today - timedelta(days=6)
                end_date = today
            elif period == 'month':
                start_date = date(today.year, today.month, 1)
                end_date = today
            elif period == '30days':
                start_date = today - timedelta(days=29)
                end_date = today
            else:
                start_date = date(today.year, today.month, 1)
                end_date = today
            
            db = get_db_session()
            try:
                from sqlalchemy import func
                from database import User
                
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    return {}
                
                # Получаем все ключи пользователя
                user_keys = db.query(VPNKey).filter(VPNKey.user_id == user_id).all()
                
                # Получаем статистику по каждому ключу
                keys_stats = []
                total_received = 0
                total_sent = 0
                active_keys_count = 0
                last_connection = None
                
                wg_stats = self.get_wireguard_stats()
                
                for key in user_keys:
                    # Получаем статистику за период
                    key_stats = self.get_traffic_stats_by_period(
                        start_date, end_date, vpn_key_id=key.id
                    )
                    
                    key_received = 0
                    key_sent = 0
                    key_last_connection = None
                    
                    if key_stats:
                        key_received = key_stats[0]['bytes_received']
                        key_sent = key_stats[0]['bytes_sent']
                        key_last_connection = key_stats[0]['last_connection']
                    
                    total_received += key_received
                    total_sent += key_sent
                    
                    if key_last_connection:
                        if not last_connection or key_last_connection > last_connection:
                            last_connection = key_last_connection
                    
                    # Проверяем активность ключа
                    is_active = False
                    uptime_seconds = None
                    if key.public_key and key.public_key in wg_stats:
                        stat = wg_stats[key.public_key]
                        if stat.get('last_handshake'):
                            time_diff = (datetime.now() - stat['last_handshake']).total_seconds()
                            if time_diff < 300:  # 5 минут
                                is_active = True
                                uptime_seconds = int(time_diff)
                    
                    if is_active:
                        active_keys_count += 1
                    
                    # Получаем IP адреса
                    connection_ips = []
                    if key_stats and key_stats[0].get('connection_ips'):
                        connection_ips = key_stats[0]['connection_ips']
                    
                    keys_stats.append({
                        'vpn_key_id': key.id,
                        'key_name': key.key_name,
                        'is_active': is_active,
                        'received': key_received,
                        'sent': key_sent,
                        'total': key_received + key_sent,
                        'last_connection': key_last_connection,
                        'connection_ips': connection_ips,
                        'uptime_seconds': uptime_seconds,
                        'client_ip': key.client_ip
                    })
                
                user_name = user.nickname or user.first_name or user.username or f'User #{user.id}'
                
                return {
                    'user_id': user.id,
                    'user_name': user_name,
                    'period': period,
                    'summary': {
                        'total_received': total_received,
                        'total_sent': total_sent,
                        'total_traffic': total_received + total_sent,
                        'active_keys_count': active_keys_count,
                        'total_keys_count': len(user_keys),
                        'last_connection': last_connection
                    },
                    'keys': keys_stats
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting user keys traffic: {e}", exc_info=True)
            return {}


# Глобальный экземпляр менеджера трафика
traffic_manager = TrafficManager()

