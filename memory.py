import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional


class MemoryStore:
    """Хранилище долговременной памяти пользователей"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.getenv("MEMORY_DB_PATH", "memory.db")
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id INTEGER PRIMARY KEY,
                facts TEXT DEFAULT '[]',
                preferences TEXT DEFAULT '{}',
                last_orders TEXT DEFAULT '[]',
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_message TEXT,
                assistant_response TEXT,
                was_helpful INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def get_user_memory(self, user_id: int) -> Dict[str, Any]:
        """Получить память пользователя"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM user_memory WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "user_id": row["user_id"],
                "facts": json.loads(row["facts"]),
                "preferences": json.loads(row["preferences"]),
                "last_orders": json.loads(row["last_orders"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
        
        return {
            "user_id": user_id,
            "facts": [],
            "preferences": {},
            "last_orders": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    def update_user_memory(self, user_id: int, facts: List[str] = None, 
                          preferences: Dict = None, last_orders: List = None):
        """Обновить память пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get current memory
        current = self.get_user_memory(user_id)
        
        if facts is not None:
            current["facts"] = facts
        if preferences is not None:
            current["preferences"] = preferences
        if last_orders is not None:
            current["last_orders"] = last_orders
        
        current["updated_at"] = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_memory (user_id, facts, preferences, last_orders, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, json.dumps(current["facts"]), json.dumps(current["preferences"]),
              json.dumps(current["last_orders"]), current["created_at"], current["updated_at"]))
        
        conn.commit()
        conn.close()
    
    def add_fact(self, user_id: int, fact: str):
        """Добавить факт о пользователе"""
        memory = self.get_user_memory(user_id)
        if fact not in memory["facts"]:
            memory["facts"].append(fact)
            self.update_user_memory(user_id, facts=memory["facts"])
    
    def get_facts_text(self, user_id: int) -> str:
        """Получить факты в виде текста для system prompt"""
        memory = self.get_user_memory(user_id)
        if not memory["facts"]:
            return ""
        
        facts_text = "Известно о пользователе:\n"
        for fact in memory["facts"][-10:]:  # Last 10 facts
            facts_text += f"- {fact}\n"
        return facts_text
    
    def get_preferences(self, user_id: int) -> Dict:
        """Получить предпочтения пользователя"""
        return self.get_user_memory(user_id).get("preferences", {})
    
    def add_example(self, user_message: str, assistant_response: str, helpful: bool = True):
        """Добавить пример диалога для few-shot learning"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversation_examples (user_message, assistant_response, was_helpful, created_at)
            VALUES (?, ?, ?, ?)
        """, (user_message, assistant_response, 1 if helpful else 0, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def get_examples(self, limit: int = 5) -> List[Dict]:
        """Получить лучшие примеры диалогов"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_message, assistant_response 
            FROM conversation_examples 
            WHERE was_helpful = 1
            ORDER BY created_at DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{"user": row["user_message"], "assistant": row["assistant_response"]} for row in rows]
    
    def get_examples_text(self, limit: int = 3) -> str:
        """Получить примеры в виде текста для system prompt"""
        examples = self.get_examples(limit)
        if not examples:
            return ""
        
        text = "Примеры удачных диалогов:\n"
        for ex in examples:
            text += f"Пользователь: {ex['user']}\n"
            text += f"Ассистент: {ex['assistant']}\n\n"
        return text


# Global memory store instance
memory_store = MemoryStore()
