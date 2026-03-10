#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Анализатор ML Cloud для определения механизма оплаты
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urlparse, urljoin


class MLCloudAnalyzer:
    """Анализатор ML Cloud"""
    
    def __init__(self):
        self.base_url = "https://app.ml.cloud"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def analyze_main_page(self):
        """Анализ главной страницы"""
        print("=" * 80)
        print("АНАЛИЗ ГЛАВНОЙ СТРАНИЦЫ")
        print("=" * 80)
        
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Поиск ссылок на оплату
            payment_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if any(keyword in href.lower() or keyword in text.lower() 
                       for keyword in ['payment', 'pay', 'oplata', 'оплат', 'billing', 'balance']):
                    full_url = urljoin(self.base_url, href)
                    payment_links.append((text, full_url))
            
            print(f"\n🔗 Найдены ссылки, связанные с оплатой:")
            for text, url in payment_links[:10]:
                print(f"   {text}: {url}")
            
            # Поиск API endpoints
            scripts = soup.find_all('script')
            api_endpoints = set()
            
            for script in scripts:
                script_content = script.string or ""
                script_src = script.get('src', '')
                
                # Поиск API в src
                if script_src and ('api' in script_src.lower()):
                    api_endpoints.add(script_src)
                
                # Поиск API в коде
                patterns = [
                    r'["\'](/api/[^"\']+)["\']',
                    r'["\'](https?://[^"\']*api[^"\']+)["\']',
                    r'baseURL\s*[:=]\s*["\']([^"\']+)["\']',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, script_content)
                    api_endpoints.update(matches)
            
            print(f"\n🔍 Найдены API endpoints:")
            for endpoint in sorted(api_endpoints)[:20]:
                print(f"   {endpoint}")
            
            # Поиск форм
            forms = soup.find_all('form')
            print(f"\n📋 Найдены формы ({len(forms)}):")
            for form in forms:
                action = form.get('action', 'N/A')
                method = form.get('method', 'GET')
                print(f"   {method} → {action}")
            
            return {
                'payment_links': payment_links,
                'api_endpoints': list(api_endpoints),
                'forms': len(forms)
            }
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return None
    
    def analyze_login_page(self):
        """Анализ страницы авторизации"""
        print("\n" + "=" * 80)
        print("АНАЛИЗ СТРАНИЦЫ АВТОРИЗАЦИИ")
        print("=" * 80)
        
        try:
            response = self.session.get(f"{self.base_url}/login")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Поиск формы авторизации
            form = soup.find('form')
            if form:
                print(f"\n📋 Форма авторизации:")
                print(f"   Action: {form.get('action', 'N/A')}")
                print(f"   Method: {form.get('method', 'GET')}")
                
                inputs = form.find_all('input')
                for inp in inputs:
                    name = inp.get('name', '')
                    input_type = inp.get('type', 'text')
                    print(f"   {name} ({input_type})")
            
            return True
        except Exception as e:
            print(f"⚠️  Страница /login не найдена: {e}")
            return False
    
    def find_payment_endpoints(self):
        """Поиск endpoints для оплаты"""
        print("\n" + "=" * 80)
        print("ПОИСК ENDPOINTS ДЛЯ ОПЛАТЫ")
        print("=" * 80)
        
        endpoints_to_try = [
            '/payment',
            '/pay',
            '/billing',
            '/balance',
            '/deposit',
            '/topup',
            '/api/payment',
            '/api/billing',
            '/api/balance',
        ]
        
        found_endpoints = []
        
        for endpoint in endpoints_to_try:
            try:
                url = urljoin(self.base_url, endpoint)
                response = self.session.get(url, timeout=5)
                
                if response.status_code == 200:
                    found_endpoints.append((endpoint, response.status_code, len(response.text)))
                    print(f"✅ {endpoint} - {response.status_code} ({len(response.text)} bytes)")
                elif response.status_code != 404:
                    found_endpoints.append((endpoint, response.status_code, 0))
                    print(f"⚠️  {endpoint} - {response.status_code}")
            except Exception as e:
                pass
        
        return found_endpoints
    
    def analyze_javascript_app(self):
        """Анализ JavaScript приложения (если это SPA)"""
        print("\n" + "=" * 80)
        print("АНАЛИЗ JAVASCRIPT ПРИЛОЖЕНИЯ")
        print("=" * 80)
        
        try:
            response = self.session.get(self.base_url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Поиск всех JavaScript файлов
            scripts = soup.find_all('script', src=True)
            
            print(f"\n📜 Найдено JavaScript файлов: {len(scripts)}")
            
            for script in scripts[:10]:  # Первые 10
                src = script.get('src', '')
                if src:
                    full_url = urljoin(self.base_url, src)
                    print(f"   {full_url}")
            
            # Поиск inline JavaScript
            inline_scripts = soup.find_all('script', src=False)
            if inline_scripts:
                print(f"\n📝 Найдено inline скриптов: {len(inline_scripts)}")
                
                for script in inline_scripts:
                    content = script.string or ""
                    if content and len(content) > 100:
                        # Поиск ключевых слов
                        keywords = ['payment', 'pay', 'billing', 'api', 'token', 'auth']
                        found_keywords = [kw for kw in keywords if kw in content.lower()]
                        if found_keywords:
                            print(f"   Найдены ключевые слова: {', '.join(found_keywords)}")
                            # Показать первые 200 символов
                            preview = content[:200].replace('\n', ' ')
                            print(f"   Preview: {preview}...")
            
            return True
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            return False
    
    def full_analysis(self):
        """Полный анализ"""
        print("\n" + "🔍" * 40)
        print("ПОЛНЫЙ АНАЛИЗ ML CLOUD")
        print("🔍" * 40 + "\n")
        
        results = {}
        
        # 1. Главная страница
        results['main_page'] = self.analyze_main_page()
        
        # 2. Страница авторизации
        results['login'] = self.analyze_login_page()
        
        # 3. Поиск endpoints
        results['endpoints'] = self.find_payment_endpoints()
        
        # 4. JavaScript анализ
        results['js_analysis'] = self.analyze_javascript_app()
        
        return results


def main():
    analyzer = MLCloudAnalyzer()
    results = analyzer.full_analysis()
    
    print("\n" + "=" * 80)
    print("ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 80)
    
    if results.get('main_page'):
        print(f"\n✅ Главная страница проанализирована")
        if results['main_page'].get('payment_links'):
            print(f"   Найдено ссылок на оплату: {len(results['main_page']['payment_links'])}")
    
    if results.get('endpoints'):
        print(f"\n✅ Проверено endpoints: {len(results['endpoints'])}")
    
    print("\n💡 Рекомендации:")
    print("   1. Попробуйте авторизоваться и найти страницу оплаты в интерфейсе")
    print("   2. Откройте DevTools → Network при работе с сайтом")
    print("   3. Проверьте API запросы к /api/ при навигации по сайту")


if __name__ == '__main__':
    main()

