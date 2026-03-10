"""
Утилиты для работы с базой данных
"""
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path='db.sqlite'):
        self.db_path = db_path
    
    def get_connection(self):
        """Получить соединение с БД"""
        return sqlite3.connect(self.db_path)
    
    def get_config(self, key: str) -> Optional[str]:
        """Получить значение конфигурации"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM config WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_config(self, key: str, value: str):
        """Установить значение конфигурации"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO config (key, value) 
            VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()
    
    def save_donation(self, label: str, telegram_id: int, amount: float, 
                     operation_id: Optional[str] = None, status: str = 'pending') -> bool:
        """Сохранить донат"""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO donations 
                (label, telegram_id, amount, status, operation_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (label, telegram_id, amount, status, operation_id, datetime.now()))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_donation(self, label: str) -> Optional[Dict]:
        """Получить донат по label"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM donations WHERE label = ?', (label,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    
    def get_user_donations(self, telegram_id: int) -> List[Dict]:
        """Получить все донаты пользователя"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM donations 
            WHERE telegram_id = ? 
            ORDER BY timestamp DESC
        ''', (telegram_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_pending_donations(self) -> List[Dict]:
        """Получить все ожидающие донаты"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM donations 
            WHERE status = 'pending' 
            ORDER BY timestamp DESC
        ''')
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

