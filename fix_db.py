#!/usr/bin/env python3
"""Быстрое исправление БД - добавление колонки created_by_bot"""
import sqlite3
import sys
from pathlib import Path

# Получаем путь к БД
db_path = Path(__file__).parent / "database.db"

print(f"Database path: {db_path.absolute()}")
print(f"Database exists: {db_path.exists()}")

if not db_path.exists():
    print("ERROR: Database file not found!")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

try:
    # Проверяем текущие колонки
    cursor.execute("PRAGMA table_info(vpn_keys)")
    columns_before = [row[1] for row in cursor.fetchall()]
    print(f"\nCurrent columns: {', '.join(columns_before)}")
    
    if 'created_by_bot' not in columns_before:
        print("\nAdding column 'created_by_bot'...")
        cursor.execute("ALTER TABLE vpn_keys ADD COLUMN created_by_bot BOOLEAN DEFAULT 1")
        conn.commit()
        print("✅ Column 'created_by_bot' added!")
        
        # Устанавливаем значение для существующих ключей
        count = cursor.execute("UPDATE vpn_keys SET created_by_bot = 1").rowcount
        conn.commit()
        print(f"✅ Updated {count} existing keys")
    else:
        print("\n✅ Column 'created_by_bot' already exists!")
    
    # Проверяем результат
    cursor.execute("PRAGMA table_info(vpn_keys)")
    columns_after = [row[1] for row in cursor.fetchall()]
    print(f"\nFinal columns: {', '.join(columns_after)}")
    print(f"\n✅ Migration completed successfully!")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    conn.rollback()
    sys.exit(1)
finally:
    conn.close()

