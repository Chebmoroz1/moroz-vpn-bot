"""Инициализация базы данных"""
from database import init_db

if __name__ == "__main__":
    print("Инициализация базы данных...")
    init_db()
    print("База данных успешно инициализирована!")

