#!/usr/bin/env python3
"""Скрипт для анализа реальных данных трафика"""
from traffic_manager import traffic_manager
from database import get_db_session, TrafficStatistics, VPNKey
from datetime import date, datetime, timedelta
from sqlalchemy import func

def format_bytes(bytes_val):
    return f"{bytes_val:,} bytes ({bytes_val / 1024 / 1024:.2f} MB)"

# 1. Получаем текущие данные из WireGuard
print("=== ДАННЫЕ ИЗ WIREGUARD ===")
wg_stats = traffic_manager.get_wireguard_stats()
print(f"Всего ключей в WireGuard: {len(wg_stats)}")
total_wg_received = sum(s.get("bytes_received", 0) for s in wg_stats.values())
total_wg_sent = sum(s.get("bytes_sent", 0) for s in wg_stats.values())
print(f"Total WG Received: {format_bytes(total_wg_received)}")
print(f"Total WG Sent: {format_bytes(total_wg_sent)}")
print(f"Total WG: {format_bytes(total_wg_received + total_wg_sent)}")

# 2. Получаем данные из БД за сегодня
print("\n=== ДАННЫЕ ИЗ БД ЗА СЕГОДНЯ ===")
db = get_db_session()
today = date.today()
stats_today = db.query(
    TrafficStatistics.date,
    func.sum(TrafficStatistics.bytes_received).label("received"),
    func.sum(TrafficStatistics.bytes_sent).label("sent")
).join(VPNKey).filter(
    TrafficStatistics.date == today
).group_by(TrafficStatistics.date).first()

if stats_today:
    print(f"Дата: {stats_today.date}")
    print(f"Received: {format_bytes(stats_today.received)}")
    print(f"Sent: {format_bytes(stats_today.sent)}")
    print(f"Total: {format_bytes(stats_today.received + stats_today.sent)}")
else:
    print("Нет данных за сегодня")

# 3. Получаем данные из БД за последние 7 дней
print("\n=== ДАННЫЕ ИЗ БД ЗА ПОСЛЕДНИЕ 7 ДНЕЙ ===")
week_ago = today - timedelta(days=6)
stats_week = db.query(
    TrafficStatistics.date,
    func.sum(TrafficStatistics.bytes_received).label("received"),
    func.sum(TrafficStatistics.bytes_sent).label("sent")
).join(VPNKey).filter(
    TrafficStatistics.date >= week_ago,
    TrafficStatistics.date <= today
).group_by(TrafficStatistics.date).order_by(TrafficStatistics.date.asc()).all()

for stat in stats_week:
    total = (stat.received or 0) + (stat.sent or 0)
    mb_total = total / 1024 / 1024
    mb_received = stat.received / 1024 / 1024
    mb_sent = stat.sent / 1024 / 1024
    print(f"{stat.date}: Total={mb_total:.2f} MB (R={mb_received:.2f}, S={mb_sent:.2f})")

# 4. Получаем данные, которые возвращает get_chart_data
print("\n=== ДАННЫЕ ИЗ get_chart_data (6hours) ===")
chart_data_6h = traffic_manager.get_chart_data("6hours")
print(f"Всего точек: {len(chart_data_6h)}")
total_chart_6h = sum(p["total"] for p in chart_data_6h)
print(f"Total в графике: {format_bytes(total_chart_6h)}")
print("Первые 3 и последние 3 точки:")
for i, point in enumerate(chart_data_6h[:3] + chart_data_6h[-3:]):
    mb_total = point["total"] / 1024 / 1024
    print(f"  {point['label']}: Total={mb_total:.2f} MB")

print("\n=== ДАННЫЕ ИЗ get_chart_data (day) ===")
chart_data_day = traffic_manager.get_chart_data("day")
print(f"Всего точек: {len(chart_data_day)}")
total_chart_day = sum(p["total"] for p in chart_data_day)
print(f"Total в графике: {format_bytes(total_chart_day)}")
print("Первые 3 и последние 3 точки:")
for i, point in enumerate(chart_data_day[:3] + chart_data_day[-3:]):
    mb_total = point["total"] / 1024 / 1024
    print(f"  {point['label']}: Total={mb_total:.2f} MB")

# 5. Проверяем время последнего обновления
print("\n=== ВРЕМЯ ПОСЛЕДНЕГО ОБНОВЛЕНИЯ ===")
last_update = db.query(func.max(TrafficStatistics.updated_at)).filter(
    TrafficStatistics.date == today
).scalar()
if last_update:
    print(f"Последнее обновление: {last_update}")
    now = datetime.now()
    diff = (now - last_update).total_seconds() / 60
    print(f"Прошло минут с обновления: {diff:.1f}")
else:
    print("Нет данных о времени обновления")

# 6. Проверяем детали по ключам
print("\n=== ДЕТАЛИ ПО КЛЮЧАМ (первые 3) ===")
keys_stats = db.query(
    VPNKey.id,
    VPNKey.name,
    TrafficStatistics.bytes_received,
    TrafficStatistics.bytes_sent,
    TrafficStatistics.updated_at
).join(TrafficStatistics).filter(
    TrafficStatistics.date == today
).limit(3).all()

for key_stat in keys_stats:
    total = (key_stat.bytes_received or 0) + (key_stat.bytes_sent or 0)
    print(f"Key {key_stat.id} ({key_stat.name}): {format_bytes(total)}")
    print(f"  Updated: {key_stat.updated_at}")

db.close()

