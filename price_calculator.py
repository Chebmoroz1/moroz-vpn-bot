"""Модуль для расчета цен на QR-коды с учетом скидок"""
from typing import Dict, Tuple
from config_manager import config_manager


class PriceCalculator:
    """Калькулятор цен для QR-кодов"""
    
    def __init__(self):
        # Базовые параметры (можно переопределить через config_manager)
        self.base_price = float(config_manager.get("QR_CODE_BASE_PRICE", default="100"))
        self.code_discount = float(config_manager.get("QR_CODE_DISCOUNT", default="0.15"))  # 15%
        self.max_codes = int(config_manager.get("QR_CODE_MAX_COUNT", default="5"))
        self.max_months = 12
        
        # Скидки за период (в процентах)
        self.period_discounts = {
            1: 0.0,    # 0%
            3: 0.05,   # 5%
            6: 0.10,   # 10%
            12: 0.20   # 20%
        }
    
    def get_period_discount(self, months: int) -> float:
        """
        Получить скидку за период
        
        Args:
            months: Количество месяцев
            
        Returns:
            Скидка в долях (0.0 - 1.0)
        """
        # Находим ближайшую скидку (вниз)
        if months >= 12:
            return self.period_discounts[12]
        elif months >= 6:
            return self.period_discounts[6]
        elif months >= 3:
            return self.period_discounts[3]
        else:
            return self.period_discounts[1]
    
    def calculate_price(self, codes_count: int, months: int) -> Dict[str, float]:
        """
        Расчет цены с учетом всех скидок (мультипликативная формула)
        
        Args:
            codes_count: Количество кодов (1-5)
            months: Количество месяцев (1-12)
            
        Returns:
            Словарь с детальной информацией о цене:
            {
                'base_total': базовая цена без скидок,
                'price_per_code_per_month': цена за код за месяц со скидками,
                'total': итоговая цена,
                'code_discount_amount': экономия за количество,
                'period_discount_amount': экономия за период,
                'total_discount_amount': общая экономия,
                'code_discount_percent': процент скидки за количество,
                'period_discount_percent': процент скидки за период
            }
        """
        # Ограничиваем значения
        codes_count = max(1, min(codes_count, self.max_codes))
        months = max(1, min(months, self.max_months))
        
        # Базовая цена без скидок
        base_total = self.base_price * codes_count * months
        
        # Скидка за количество кодов
        if codes_count > 1:
            # Формула: CODE_DISCOUNT * (n-1) / n
            code_discount_factor = self.code_discount * (codes_count - 1) / codes_count
            code_discount_percent = code_discount_factor * 100
        else:
            code_discount_factor = 0.0
            code_discount_percent = 0.0
        
        # Скидка за период
        period_discount_factor = self.get_period_discount(months)
        period_discount_percent = period_discount_factor * 100
        
        # Мультипликативная формула: BASE_PRICE * (1 - CODE_DISCOUNT) * (1 - PERIOD_DISCOUNT)
        price_per_code_per_month = self.base_price * (1 - code_discount_factor) * (1 - period_discount_factor)
        
        # Итоговая цена
        total = price_per_code_per_month * codes_count * months
        
        # Расчет экономии
        code_discount_amount = base_total * code_discount_factor
        period_discount_amount = base_total * period_discount_factor * (1 - code_discount_factor)
        total_discount_amount = base_total - total
        
        return {
            'base_total': base_total,
            'price_per_code_per_month': price_per_code_per_month,
            'total': total,
            'code_discount_amount': code_discount_amount,
            'period_discount_amount': period_discount_amount,
            'total_discount_amount': total_discount_amount,
            'code_discount_percent': code_discount_percent,
            'period_discount_percent': period_discount_percent
        }
    
    def format_price_info(self, codes_count: int, months: int) -> str:
        """
        Форматирование информации о цене для отображения в боте
        
        Args:
            codes_count: Количество кодов
            months: Количество месяцев
            
        Returns:
            Отформатированная строка с информацией о цене и экономии
        """
        price_info = self.calculate_price(codes_count, months)
        
        # Форматируем экономию
        savings_text = "💡 Экономия при такой покупке:\n"
        
        if price_info['code_discount_percent'] > 0:
            savings_text += f"   • Скидка за количество: {price_info['code_discount_percent']:.1f}% ({price_info['code_discount_amount']:.0f}₽)\n"
        else:
            savings_text += f"   • Скидка за количество: 0% (0₽)\n"
        
        if price_info['period_discount_percent'] > 0:
            savings_text += f"   • Скидка за период: {price_info['period_discount_percent']:.1f}% ({price_info['period_discount_amount']:.0f}₽)\n"
        else:
            savings_text += f"   • Скидка за период: 0% (0₽)\n"
        
        if price_info['total_discount_amount'] > 0:
            savings_text += f"   • Общая экономия: {price_info['total_discount_amount']:.0f}₽"
        else:
            savings_text += f"   • Общая экономия: 0₽"
        
        # Описание покупки
        month_word = self._get_month_word(months)
        code_word = self._get_code_word(codes_count)
        description = f"📝 Описание:\n   Вы покупаете {codes_count} {code_word} на {months} {month_word}.\n   После оплаты вы получите QR-код{'и' if codes_count > 1 else ''} для настройки VPN."
        
        return f"{savings_text}\n\n{description}"
    
    def _get_month_word(self, months: int) -> str:
        """Получить правильное склонение слова 'месяц'"""
        if months == 1:
            return "месяц"
        elif 2 <= months <= 4:
            return "месяца"
        else:
            return "месяцев"
    
    def _get_code_word(self, codes_count: int) -> str:
        """Получить правильное склонение слова 'код'"""
        if codes_count == 1:
            return "код"
        elif 2 <= codes_count <= 4:
            return "кода"
        else:
            return "кодов"


# Глобальный экземпляр калькулятора
price_calculator = PriceCalculator()

