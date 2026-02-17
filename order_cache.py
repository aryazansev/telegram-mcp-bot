import asyncio
import time
from typing import Dict, List, Any, Optional


class OrderCache:
    """Кэш заказов для быстрого доступа"""
    
    def __init__(self, max_size: int = 300):
        self.max_size = max_size
        self.cache: Dict[str, Dict] = {}  # order_number -> order data
        self.cache_by_phone: Dict[str, List[str]] = {}  # phone -> list of order numbers
        self.last_update = 0
        self.ttl = 300  # 5 минут
    
    def _should_refresh(self) -> bool:
        """Нужно ли обновить кэш"""
        return time.time() - self.last_update > self.ttl
    
    async def refresh(self, mcp_manager, force: bool = False):
        """Обновить кэш из RetailCRM"""
        if not force and not self._should_refresh():
            return
        
        try:
            result = await mcp_manager.execute_tool('retailcrm__get_orders', {
                'limit': self.max_size,
                'page': 1
            })
            
            import json
            data = json.loads(result)
            orders = data.get('orders', [])
            
            # Очищаем старый кэш
            self.cache.clear()
            self.cache_by_phone.clear()
            
            for order in orders:
                number = order.get('number')
                if number:
                    self.cache[number] = order
                    
                    # Индексация по телефону
                    phone = order.get('phone', '').replace('+7', '7')
                    if phone and len(phone) >= 10:
                        last10 = phone[-10:]
                        if last10 not in self.cache_by_phone:
                            self.cache_by_phone[last10] = []
                        if number not in self.cache_by_phone[last10]:
                            self.cache_by_phone[last10].append(number)
            
            self.last_update = time.time()
            print(f"[OrderCache] Обновлено: {len(self.cache)} заказов")
            
        except Exception as e:
            print(f"[OrderCache] Ошибка обновления: {e}")
    
    def get_order(self, order_number: str) -> Optional[Dict]:
        """Получить заказ по номеру"""
        return self.cache.get(order_number)
    
    def find_by_phone(self, phone: str) -> List[Dict]:
        """Найти заказы по телефону"""
        phone = phone.replace('+7', '7').replace('-', '').replace(' ', '')
        if len(phone) >= 10:
            last10 = phone[-10:]
            order_numbers = self.cache_by_phone.get(last10, [])
            return [self.cache[n] for n in order_numbers]
        return []
    
    def search(self, query: str) -> List[Dict]:
        """Поиск по номеру или телефону"""
        query = query.strip().lower()
        
        # Точное совпадение по номеру
        if query in self.cache:
            return [self.cache[query]]
        
        # Поиск по части номера
        results = []
        for number, order in self.cache.items():
            if query in number.lower():
                results.append(order)
        
        return results[:10]
    
    def get_stats(self) -> Dict:
        """Статистика кэша"""
        return {
            'total_orders': len(self.cache),
            'last_update': self.last_update,
            'age_seconds': int(time.time() - self.last_update)
        }


# Global cache instance
order_cache = OrderCache(max_size=300)
