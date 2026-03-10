"""Скрипт для добавления колонки download_token в существующую БД"""
from database import engine, Base
from sqlalchemy import text
from pathlib import Path
from config import DATABASE_PATH

def add_token_column():
    """Добавление колонки download_token если её нет"""
    if not Path(DATABASE_PATH).exists():
        print("База данных не существует, будет создана при первом запуске")
        return
    
    with engine.connect() as conn:
        # Проверяем, существует ли колонка
        result = conn.execute(text(
            "PRAGMA table_info(vpn_keys)"
        ))
        columns = [row[1] for row in result]
        
        if 'download_token' not in columns:
            print("Добавляем колонку download_token...")
            conn.execute(text(
                "ALTER TABLE vpn_keys ADD COLUMN download_token VARCHAR(255)"
            ))
            conn.commit()
            print("✅ Колонка download_token успешно добавлена!")
        else:
            print("✅ Колонка download_token уже существует")

if __name__ == "__main__":
    add_token_column()

