"""Скрипт для добавления колонки created_by_bot в существующую БД"""
import sqlite3
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

try:
    from config import DATABASE_PATH
except ImportError:
    DATABASE_PATH = Path(__file__).parent / "database.db"
    print(f"Using default path: {DATABASE_PATH}")

def add_column():
    """Добавление колонки created_by_bot"""
    print(f"Connecting to database: {DATABASE_PATH}")
    
    if not Path(DATABASE_PATH).exists():
        print(f"❌ Database file not found: {DATABASE_PATH}")
        return
    
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли колонка
        cursor.execute("PRAGMA table_info(vpn_keys)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Current columns: {columns}")
        print(f"'created_by_bot' in columns: {'created_by_bot' in columns}")
        
        if 'created_by_bot' not in columns:
            # Добавляем колонку
            print("Adding column created_by_bot...")
            cursor.execute("ALTER TABLE vpn_keys ADD COLUMN created_by_bot BOOLEAN DEFAULT 1")
            conn.commit()
            print("✅ Колонка created_by_bot добавлена успешно")
            
            # Устанавливаем значение по умолчанию для существующих ключей
            cursor.execute("UPDATE vpn_keys SET created_by_bot = 1")
            conn.commit()
            print("✅ Значения по умолчанию установлены")
        else:
            print("ℹ️ Колонка created_by_bot уже существует")
            
        # Проверяем результат
        cursor.execute("PRAGMA table_info(vpn_keys)")
        columns_after = [row[1] for row in cursor.fetchall()]
        print(f"Columns after migration: {columns_after}")
            
    except Exception as e:
        print(f"❌ Ошибка при добавлении колонки: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    add_column()

