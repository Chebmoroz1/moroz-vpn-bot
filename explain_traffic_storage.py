#!/usr/bin/env python3
"""Объяснение как собирается и хранится статистика трафика"""
from traffic_manager import traffic_manager
from database import get_db_session, TrafficStatistics, VPNKey
from datetime import date, datetime, timedelta
from sqlalchemy import func

print("=" * 70)
print("КАК СОБИРАЕТСЯ И ХРАНИТСЯ СТАТИСТИКА ТРАФИКА")
print("=" * 70)

# 1. Проверяем данные из WireGuard
print("\n1. ДАННЫЕ ИЗ WIREGUARD (wg show wg0 dump):")
print("-" * 70)
wg_stats = traffic_manager.get_wireguard_stats()
if wg_stats:
    first_key = list(wg_stats.keys())[0]
    first_stat = wg_stats[first_key]
    print(f"Пример ключа: {first_key[:30]}...")
    print(f"bytes_received: {first_stat.get('bytes_received', 0):,} bytes")
    print(f"bytes_sent: {first_stat.get('bytes_sent', 0):,} bytes")
    print("\nВАЖНО: WireGuard хранит НАКОПИТЕЛЬНЫЕ значения!")
    print("Это общий трафик с момента создания ключа, а не за день/период.")
    
    total_wg = sum(s.get("bytes_received", 0) + s.get("bytes_sent", 0) for s in wg_stats.values())
    print(f"\nTotal всех ключей: {total_wg:,} bytes ({total_wg/1024/1024:.2f} MB)")
    print("Это накопительный трафик всех ключей с момента их создания.")

# 2. Проверяем как sync_traffic_stats сохраняет данные
print("\n2. КАК sync_traffic_stats() СОХРАНЯЕТ ДАННЫЕ В БД:")
print("-" * 70)
print("При вызове sync_traffic_stats():")
print("1. Получает накопительные значения из WireGuard")
print("2. Для каждого ключа ищет запись в БД за указанную дату (target_date)")
print("3. Если запись существует - ПЕРЕЗАПИСЫВАЕТ накопительные значения")
print("4. Если записи нет - СОЗДАЕТ новую с накопительными значениями")
print("\nВАЖНО: В БД хранятся НАКОПИТЕЛЬНЫЕ значения, а не дневной трафик!")
print("При каждом вызове sync_traffic_stats() значения обновляются на текущие")

# 3. Проверяем данные в БД
print("\n3. ДАННЫЕ В БД (таблица traffic_statistics):")
print("-" * 70)
db = get_db_session()
today = date.today()
yesterday = today - timedelta(days=1)

# Проверяем структуру таблицы
sample = db.query(TrafficStatistics).filter(TrafficStatistics.date == today).first()
if sample:
    print(f"Структура записи:")
    print(f"  - vpn_key_id: {sample.vpn_key_id} (ID ключа)")
    print(f"  - date: {sample.date} (дата записи)")
    print(f"  - bytes_received: {sample.bytes_received:,} (НАКОПИТЕЛЬНОЕ значение)")
    print(f"  - bytes_sent: {sample.bytes_sent:,} (НАКОПИТЕЛЬНОЕ значение)")
    print(f"  - created_at: {sample.created_at} (когда создана запись)")
    print(f"  - updated_at: {sample.updated_at} (когда последний раз обновлена)")

# Проверяем данные за сегодня и вчера
today_stats = db.query(
    func.sum(TrafficStatistics.bytes_received).label("received"),
    func.sum(TrafficStatistics.bytes_sent).label("sent")
).join(VPNKey).filter(TrafficStatistics.date == today).first()

yesterday_stats = db.query(
    func.sum(TrafficStatistics.bytes_received).label("received"),
    func.sum(TrafficStatistics.bytes_sent).label("sent")
).join(VPNKey).filter(TrafficStatistics.date == yesterday).first()

print(f"\nДанные за сегодня ({today}):")
if today_stats:
    total_today = (today_stats.received or 0) + (today_stats.sent or 0)
    print(f"  received: {today_stats.received:,} bytes ({today_stats.received/1024/1024:.2f} MB)")
    print(f"  sent: {today_stats.sent:,} bytes ({today_stats.sent/1024/1024:.2f} MB)")
    print(f"  total: {total_today:,} bytes ({total_today/1024/1024:.2f} MB)")
    print(f"  ^ Это НАКОПИТЕЛЬНЫЕ значения (общий трафик с момента создания ключей)")

print(f"\nДанные за вчера ({yesterday}):")
if yesterday_stats and yesterday_stats.received is not None:
    total_yesterday = (yesterday_stats.received or 0) + (yesterday_stats.sent or 0)
    print(f"  received: {yesterday_stats.received:,} bytes ({yesterday_stats.received/1024/1024:.2f} MB)")
    print(f"  sent: {yesterday_stats.sent:,} bytes ({yesterday_stats.sent/1024/1024:.2f} MB)")
    print(f"  total: {total_yesterday:,} bytes ({total_yesterday/1024/1024:.2f} MB)")
    print(f"  ^ Это НАКОПИТЕЛЬНЫЕ значения на конец вчерашнего дня")
    
    if today_stats:
        diff_received = (today_stats.received or 0) - (yesterday_stats.received or 0)
        diff_sent = (today_stats.sent or 0) - (yesterday_stats.sent or 0)
        diff_total = diff_received + diff_sent
        print(f"\nРАЗНИЦА (сегодня - вчера) = РЕАЛЬНЫЙ ТРАФИК ЗА СЕГОДНЯ:")
        print(f"  received: {diff_received:,} bytes ({diff_received/1024/1024:.2f} MB)")
        print(f"  sent: {diff_sent:,} bytes ({diff_sent/1024/1024:.2f} MB)")
        print(f"  total: {diff_total:,} bytes ({diff_total/1024/1024:.2f} MB)")
        print(f"  ^ Это реальный трафик, который прошел за сегодня!")
else:
    print("  НЕТ ДАННЫХ ЗА ВЧЕРА!")
    print("  ^^^ ЭТО ОСНОВНАЯ ПРОБЛЕМА! ^^^")
    print("  sync_traffic_stats() вызывается только для target_date=today")
    print("  Поэтому в БД нет данных за предыдущие дни")
    print("  Невозможно вычислить разницу для получения реального трафика!")

# 4. Проверяем несколько дней
print("\n4. ДАННЫЕ ЗА ПОСЛЕДНИЕ 7 ДНЕЙ:")
print("-" * 70)
week_ago = today - timedelta(days=6)
week_stats = db.query(
    TrafficStatistics.date,
    func.sum(TrafficStatistics.bytes_received).label("received"),
    func.sum(TrafficStatistics.bytes_sent).label("sent")
).join(VPNKey).filter(
    TrafficStatistics.date >= week_ago,
    TrafficStatistics.date <= today
).group_by(TrafficStatistics.date).order_by(TrafficStatistics.date.asc()).all()

prev_received = 0
prev_sent = 0
print("Дата        | Накопительный (MB) | Разница (MB) = Реальный трафик за день")
print("-" * 70)
for stat in week_stats:
    day_received = stat.received or 0
    day_sent = stat.sent or 0
    day_total = day_received + day_sent
    day_total_mb = day_total / 1024 / 1024
    
    if prev_received > 0 or prev_sent > 0:
        diff_received = day_received - prev_received
        diff_sent = day_sent - prev_sent
        diff_total = diff_received + diff_sent
        diff_total_mb = diff_total / 1024 / 1024
        print(f"{stat.date} | {day_total_mb:15.2f} | {diff_total_mb:15.2f}")
    else:
        print(f"{stat.date} | {day_total_mb:15.2f} | N/A (первый день)")
    prev_received = day_received
    prev_sent = day_sent

# 5. Проблема с текущей реализацией
print("\n5. ПРОБЛЕМА С ТЕКУЩЕЙ РЕАЛИЗАЦИЕЙ:")
print("-" * 70)
print("Проблема: В БД есть данные только за ОДИН день (сегодня)")
print("Причина: sync_traffic_stats() вызывается только для target_date=today")
print("Результат: Невозможно вычислить разницу между днями для получения реального трафика")
print("\nРешение:")
print("1. Нужно вызывать sync_traffic_stats() каждый день (например, в 00:00)")
print("2. Или хранить snapshots трафика с временными метками")
print("3. Или вычислять разницу от значения в начале дня")

db.close()

print("\n" + "=" * 70)

