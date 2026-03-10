#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Менеджер JWT токенов для ML Cloud
Управление токенами: проверка срока действия, автоматическое обновление
"""

import jwt
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path


class MLCloudTokenManager:
    """Менеджер для управления JWT токенами ML Cloud"""
    
    BASE_URL = "https://app.ml.cloud"
    TOKEN_FILE = Path("/tmp/ml_cloud_token.json")
    
    def __init__(self, email: str, password: str):
        """
        Инициализация менеджера токенов
        
        Args:
            email: Email для авторизации
            password: Пароль
        """
        self.email = email
        self.password = password
        self.token_data = self.load_token()
    
    def load_token(self) -> Optional[Dict]:
        """Загрузить сохраненный токен из файла"""
        if self.TOKEN_FILE.exists():
            try:
                with open(self.TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                print(f"⚠️  Ошибка загрузки токена: {e}")
        return None
    
    def save_token(self, token: str, token_data: Dict):
        """Сохранить токен в файл"""
        try:
            data = {
                'token': token,
                'decoded': token_data,
                'saved_at': datetime.now().isoformat()
            }
            with open(self.TOKEN_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✅ Токен сохранен в {self.TOKEN_FILE}")
        except Exception as e:
            print(f"⚠️  Ошибка сохранения токена: {e}")
    
    def decode_token(self, token: str) -> Dict:
        """Декодировать JWT токен"""
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded
        except Exception as e:
            print(f"⚠️  Ошибка декодирования токена: {e}")
            return {}
    
    def is_token_valid(self, token: str = None) -> bool:
        """
        Проверить валидность токена (не истек ли)
        
        Args:
            token: Токен для проверки (если None, использует сохраненный)
        
        Returns:
            bool: True если токен валиден
        """
        if token is None:
            if not self.token_data:
                return False
            token = self.token_data.get('token')
        
        if not token:
            return False
        
        try:
            decoded = self.decode_token(token)
            exp = decoded.get('exp')
            
            if not exp:
                return False
            
            # Проверяем, не истек ли токен (с запасом 5 минут)
            current_time = int(time.time())
            expires_at = exp
            time_until_expiry = expires_at - current_time
            
            # Токен валиден если до истечения больше 5 минут
            return time_until_expiry > 300  # 5 минут в секундах
            
        except Exception as e:
            print(f"⚠️  Ошибка проверки токена: {e}")
            return False
    
    def get_token_expiry_time(self, token: str = None) -> Optional[datetime]:
        """
        Получить время истечения токена
        
        Args:
            token: Токен (если None, использует сохраненный)
        
        Returns:
            datetime: Время истечения или None
        """
        if token is None:
            if not self.token_data:
                return None
            token = self.token_data.get('token')
        
        if not token:
            return None
        
        decoded = self.decode_token(token)
        exp = decoded.get('exp')
        
        if exp:
            return datetime.fromtimestamp(exp)
        
        return None
    
    def get_token_ttl(self, token: str = None) -> Optional[int]:
        """
        Получить время до истечения токена в секундах
        
        Args:
            token: Токен (если None, использует сохраненный)
        
        Returns:
            int: Секунды до истечения или None
        """
        expiry = self.get_token_expiry_time(token)
        if expiry:
            delta = expiry - datetime.now()
            return int(delta.total_seconds())
        return None
    
    def login(self) -> Optional[str]:
        """
        Авторизоваться и получить новый JWT токен
        
        Returns:
            str: JWT токен или None
        """
        print(f"🔐 Авторизация: {self.email}")
        
        session = requests.Session()
        session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Авторизация
        login_url = f"{self.BASE_URL}/api/user/login"
        
        payload = {
            "email": self.email,
            "password": self.password
        }
        
        try:
            response = session.post(login_url, json=payload)
            response.raise_for_status()
            
            # Проверяем ответ
            data = response.json()
            
            # Ищем токен в ответе или в cookies
            token = None
            
            # Вариант 1: Токен в ответе
            if 'token' in data:
                token = data['token']
            elif 'accessToken' in data:
                token = data['accessToken']
            elif 'jwt' in data:
                token = data['jwt']
            
            # Вариант 2: Токен в localStorage (нужно получить через браузер)
            # Вариант 3: Использовать session cookie для дальнейших запросов
            
            if not token:
                # Если токена нет в ответе, возможно нужна вторая стадия авторизации
                # или токен устанавливается в localStorage через JavaScript
                print("⚠️  Токен не найден в ответе. Возможно требуется авторизация через браузер.")
                print("💡 Попробуйте получить токен вручную из localStorage браузера.")
                return None
            
            # Декодируем токен для информации
            decoded = self.decode_token(token)
            
            print(f"✅ Авторизация успешна")
            print(f"   User ID: {decoded.get('userId', 'N/A')}")
            print(f"   Роли: {decoded.get('roles', [])}")
            
            expiry = self.get_token_expiry_time(token)
            if expiry:
                print(f"   Истекает: {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Сохраняем токен
            self.save_token(token, decoded)
            self.token_data = {'token': token, 'decoded': decoded}
            
            return token
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка авторизации: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Статус: {e.response.status_code}")
                print(f"   Ответ: {e.response.text[:200]}")
            return None
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {e}")
            return None
    
    def get_valid_token(self, force_refresh: bool = False) -> Optional[str]:
        """
        Получить валидный токен (обновить при необходимости)
        
        Args:
            force_refresh: Принудительно обновить токен
        
        Returns:
            str: Валидный JWT токен
        """
        # Если принудительное обновление
        if force_refresh:
            print("🔄 Принудительное обновление токена...")
            return self.login()
        
        # Проверяем сохраненный токен
        if self.token_data:
            token = self.token_data.get('token')
            if token and self.is_token_valid(token):
                ttl = self.get_token_ttl(token)
                print(f"✅ Токен валиден (действителен еще {ttl//3600}ч {(ttl%3600)//60}м)")
                return token
            else:
                print("⚠️  Сохраненный токен невалиден или истек")
        
        # Токен невалиден или отсутствует - получаем новый
        print("🔄 Получение нового токена...")
        return self.login()
    
    def auto_refresh_if_needed(self) -> Optional[str]:
        """
        Автоматически обновить токен если он скоро истечет
        
        Returns:
            str: Валидный токен
        """
        if self.token_data:
            token = self.token_data.get('token')
            if token:
                ttl = self.get_token_ttl(token)
                
                # Обновляем если до истечения меньше 1 часа
                if ttl and ttl < 3600:
                    print(f"⏰ Токен истечет через {ttl//60} минут. Обновляем...")
                    return self.get_valid_token(force_refresh=True)
                elif self.is_token_valid(token):
                    return token
        
        return self.get_valid_token()


def analyze_token_lifetime():
    """Анализ времени жизни токена на основе найденного"""
    
    # Токен из предыдущего анализа
    sample_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJiN2ZiYjc2ZS1hZmIyLTQ0NGYtYjc4OS00YWRiZGU5MzMxMGIiLCJyb2xlcyI6WyJ1c2VyIl0sImlhdCI6MTc2NDE5MTgwMiwiZXhwIjoxNzY0MTkxODYyfQ.UJuQheP5nwprTPDj5xQKuZGqb0tw7bZM2hHtggffJ5c"
    
    try:
        decoded = jwt.decode(sample_token, options={"verify_signature": False})
        
        iat = decoded.get('iat')
        exp = decoded.get('exp')
        
        if iat and exp:
            lifetime = exp - iat  # Время жизни в секундах
            
            print("=" * 80)
            print("АНАЛИЗ ВРЕМЕНИ ЖИЗНИ JWT ТОКЕНА ML CLOUD")
            print("=" * 80)
            
            print(f"\n📅 Время выдачи (iat): {datetime.fromtimestamp(iat)}")
            print(f"📅 Время истечения (exp): {datetime.fromtimestamp(exp)}")
            print(f"⏱️  Время жизни: {lifetime} секунд")
            print(f"   = {lifetime // 60} минут")
            print(f"   = {lifetime // 3600} часов")
            print(f"   = {lifetime // 86400} дней")
            
            # Проверяем текущее время
            current_time = int(time.time())
            if exp > current_time:
                time_until_expiry = exp - current_time
                print(f"\n✅ Токен еще действителен")
                print(f"   До истечения: {time_until_expiry} секунд")
                print(f"   = {time_until_expiry // 60} минут")
                print(f"   = {time_until_expiry // 3600} часов")
            else:
                print(f"\n❌ Токен уже истек")
            
            return {
                'lifetime_seconds': lifetime,
                'lifetime_minutes': lifetime // 60,
                'lifetime_hours': lifetime // 3600,
                'lifetime_days': lifetime // 86400
            }
            
    except Exception as e:
        print(f"❌ Ошибка анализа токена: {e}")
        return None


def main():
    """Пример использования"""
    import sys
    
    # Анализ времени жизни токена
    print("\n" + "=" * 80)
    analyze_token_lifetime()
    print("\n" + "=" * 80)
    
    if len(sys.argv) < 3:
        print("\nИспользование:")
        print("  python3 ml_cloud_token_manager.py <email> <password> [action]")
        print("\nДействия:")
        print("  check    - Проверить валидность сохраненного токена")
        print("  refresh  - Обновить токен")
        print("  get      - Получить валидный токен (обновить при необходимости)")
        print("  analyze  - Проанализировать время жизни токена")
        print("\nПример:")
        print("  python3 ml_cloud_token_manager.py email@example.com password123 get")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    action = sys.argv[3] if len(sys.argv) > 3 else "get"
    
    manager = MLCloudTokenManager(email, password)
    
    if action == "check":
        if manager.token_data:
            token = manager.token_data.get('token')
            if manager.is_token_valid(token):
                expiry = manager.get_token_expiry_time(token)
                ttl = manager.get_token_ttl(token)
                print(f"✅ Токен валиден")
                print(f"   Истекает: {expiry}")
                print(f"   Осталось: {ttl // 3600}ч {(ttl % 3600) // 60}м")
            else:
                print(f"❌ Токен невалиден или истек")
        else:
            print("⚠️  Токен не найден")
    
    elif action == "refresh":
        token = manager.get_valid_token(force_refresh=True)
        if token:
            print(f"\n✅ Новый токен получен")
    
    elif action == "get":
        token = manager.auto_refresh_if_needed()
        if token:
            print(f"\n✅ Валидный токен: {token[:50]}...")
    
    elif action == "analyze":
        analyze_token_lifetime()


if __name__ == '__main__':
    main()

