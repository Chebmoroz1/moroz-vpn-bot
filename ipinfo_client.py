"""Модуль для работы с IPinfo API"""
import logging
import requests
import time
from typing import Dict, Optional
from functools import lru_cache
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class IPinfoClient:
    """Клиент для работы с IPinfo API"""
    
    def __init__(self, token: str):
        """
        Инициализация клиента
        
        Args:
            token: API токен IPinfo
        """
        self.token = token
        self.base_url = "https://ipinfo.io"
        self.timeout = 5  # Таймаут запроса в секундах
        self.cache = {}  # Простой кэш в памяти
        self.cache_ttl = timedelta(days=1)  # Время жизни кэша - 1 день
    
    def _get_from_cache(self, ip: str) -> Optional[Dict]:
        """Получить данные из кэша"""
        if ip in self.cache:
            cached_data, cached_time = self.cache[ip]
            if datetime.now() - cached_time < self.cache_ttl:
                return cached_data
            else:
                # Удаляем устаревшие данные
                del self.cache[ip]
        return None
    
    def _save_to_cache(self, ip: str, data: Dict):
        """Сохранить данные в кэш"""
        self.cache[ip] = (data, datetime.now())
        # Ограничиваем размер кэша (максимум 1000 записей)
        if len(self.cache) > 1000:
            # Удаляем самую старую запись
            oldest_ip = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_ip]
    
    def get_ip_info(self, ip: str) -> Optional[Dict]:
        """
        Получить информацию об IP адресе
        
        Args:
            ip: IP адрес для запроса
            
        Returns:
            Словарь с информацией об IP или None в случае ошибки
            Формат: {
                'city': str,
                'region': str,
                'country': str,
                'org': str,  # Провайдер/организация
                'asn': str,  # ASN номер
                'as_name': str,  # Название ASN
                'hostname': str,
                'timezone': str,
                'loc': str  # Координаты (lat,lon)
            }
        """
        if not ip or not ip.strip():
            return None
        
        ip = ip.strip()
        
        # Проверяем кэш
        cached_data = self._get_from_cache(ip)
        if cached_data:
            logger.debug(f"IP {ip} found in cache")
            return cached_data
        
        try:
            # Делаем запрос к API
            url = f"{self.base_url}/{ip}/json"
            params = {"token": self.token}
            
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Обрабатываем ответ
            result = {
                'ip': data.get('ip', ip),
                'city': data.get('city', ''),
                'region': data.get('region', ''),
                'country': data.get('country', ''),
                'org': data.get('org', ''),  # Провайдер/организация
                'hostname': data.get('hostname', ''),
                'timezone': data.get('timezone', ''),
                'loc': data.get('loc', '')  # Координаты
            }
            
            # Обрабатываем ASN данные (если есть)
            if 'asn' in data:
                asn_data = data['asn']
                if isinstance(asn_data, dict):
                    result['asn'] = asn_data.get('asn', '')
                    result['as_name'] = asn_data.get('name', '')
                    result['as_domain'] = asn_data.get('domain', '')
                    result['as_type'] = asn_data.get('type', '')
                else:
                    result['asn'] = str(asn_data)
            
            # Если org не заполнен, но есть as_name, используем его
            if not result['org'] and result.get('as_name'):
                result['org'] = result['as_name']
            
            # Сохраняем в кэш
            self._save_to_cache(ip, result)
            
            logger.debug(f"IP {ip} info retrieved: {result.get('city', 'N/A')}, {result.get('org', 'N/A')}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching IP info for {ip}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching IP info for {ip}: {e}", exc_info=True)
            return None
    
    def get_batch_ip_info(self, ips: list) -> Dict[str, Dict]:
        """
        Получить информацию о нескольких IP адресах
        
        Args:
            ips: Список IP адресов
            
        Returns:
            Словарь {ip: info_dict} с информацией об IP адресах
        """
        result = {}
        for ip in ips:
            if ip:
                info = self.get_ip_info(ip)
                if info:
                    result[ip] = info
        return result
    
    def get_city_and_provider(self, ip: str) -> Dict[str, str]:
        """
        Получить только город и провайдера для IP
        
        Args:
            ip: IP адрес
            
        Returns:
            Словарь с ключами 'city' и 'provider'
        """
        info = self.get_ip_info(ip)
        if not info:
            return {'city': '', 'provider': ''}
        
        city = info.get('city', '')
        provider = info.get('org', '') or info.get('as_name', '')
        
        # Упрощаем название провайдера (убираем ASN номер в начале, если есть)
        if provider:
            # Формат может быть: "AS15169 Google LLC" или "Google LLC"
            provider = provider.replace('AS' + info.get('asn', '') + ' ', '').strip()
            if provider.startswith('AS'):
                # Если все еще начинается с AS, убираем до первого пробела
                parts = provider.split(' ', 1)
                if len(parts) > 1:
                    provider = parts[1]
        
        return {
            'city': city,
            'provider': provider
        }


