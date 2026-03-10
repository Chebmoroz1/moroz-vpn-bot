"""Миграция: Добавление таблицы app_config для хранения настроек"""
import sqlite3
from pathlib import Path
from config import DATABASE_PATH

def migrate():
    """Добавление таблицы app_config"""
    db_path = Path(DATABASE_PATH)
    
    if not db_path.exists():
        print(f"❌ База данных не найдена: {db_path}")
        print("Создайте базу данных сначала через init_db()")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица app_config
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_config'")
        if cursor.fetchone():
            print("✅ Таблица app_config уже существует")
            cursor.close()
            conn.close()
            return True
        
        # Создаем таблицу app_config
        cursor.execute("""
            CREATE TABLE app_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL UNIQUE,
                value VARCHAR(2000),
                description VARCHAR(500),
                is_secret BOOLEAN DEFAULT 0,
                category VARCHAR(50) DEFAULT 'general',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Создаем индекс для быстрого поиска по ключу
        cursor.execute("CREATE INDEX idx_app_config_key ON app_config(key)")
        cursor.execute("CREATE INDEX idx_app_config_category ON app_config(category)")
        
        conn.commit()
        print("✅ Таблица app_config успешно создана")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при миграции: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Миграция: Добавление таблицы app_config")
    print("=" * 60)
    print()
    
    if migrate():
        print()
        print("✅ Миграция завершена успешно!")
    else:
        print()
        print("❌ Миграция завершилась с ошибкой")
        exit(1)

