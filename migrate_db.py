#!/usr/bin/env python3
"""Простой скрипт миграции БД"""
import sqlite3
from pathlib import Path

db_path = Path('database.db')

print(f"Database path: {db_path}")
print(f"Database exists: {db_path.exists()}")

if not db_path.exists():
    print("ERROR: Database file not found!")
    exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    # Проверяем текущие колонки
    cursor.execute("PRAGMA table_info(vpn_keys)")
    columns_before = [row[1] for row in cursor.fetchall()]
    print(f"\nColumns before: {columns_before}")
    print(f"'created_by_bot' exists: {'created_by_bot' in columns_before}")
    
    if 'created_by_bot' not in columns_before:
        print("\nAdding column 'created_by_bot'...")
        cursor.execute("ALTER TABLE vpn_keys ADD COLUMN created_by_bot BOOLEAN DEFAULT 1")
        conn.commit()
        print("✅ Column added successfully!")
        
        # Устанавливаем значение для существующих ключей
        cursor.execute("UPDATE vpn_keys SET created_by_bot = 1")
        conn.commit()
        print("✅ Default values set!")
    else:
        print("\n⚠️ Column 'created_by_bot' already exists!")
    
    # Проверяем результат
    cursor.execute("PRAGMA table_info(vpn_keys)")
    columns_after = [row[1] for row in cursor.fetchall()]
    print(f"\nColumns after: {columns_after}")
    print(f"'created_by_bot' exists: {'created_by_bot' in columns_after}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
    raise
finally:
    conn.close()
    print("\nMigration completed!")

