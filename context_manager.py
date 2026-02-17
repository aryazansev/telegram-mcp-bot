import json
import tiktoken
from typing import List, Dict, Any, Optional

enc = None

def get_encoder(model: str = "gpt-4") -> tiktoken.Encoding:
    global enc
    if enc is None:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            enc = None
    return enc

def count_tokens(text: str, model: str = "gpt-4") -> int:
    encoder = get_encoder(model)
    if encoder:
        return len(encoder.encode(str(text)))
    return len(str(text)) // 4

def count_messages_tokens(messages: List[Dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    total += count_tokens(item.get("text", ""))
                else:
                    total += count_tokens(str(item))
        else:
            total += count_tokens(str(content))
        total += count_tokens(msg.get("role", "user"))
    return total

def estimate_tokens(obj: Any) -> int:
    return count_tokens(json.dumps(obj, ensure_ascii=False))

def trim_messages(messages: List[Dict], max_tokens: int = 120000) -> List[Dict]:
    if not messages:
        return []
    
    total_tokens = count_messages_tokens(messages)
    if total_tokens <= max_tokens:
        return messages
    
    trimmed = []
    total = 0
    
    for msg in reversed(messages):
        msg_tokens = estimate_tokens(msg)
        if total + msg_tokens > max_tokens:
            break
        trimmed.insert(0, msg)
        total += msg_tokens
    
    return trimmed

def summarize_old_messages(
    messages: List[Dict], 
    ai_handler,
    max_tokens: int = 80000
) -> List[Dict]:
    if not messages:
        return []
    
    recent = []
    older = []
    
    for msg in messages:
        if msg.get("role") == "system":
            recent.append(msg)
        elif msg.get("summary"):
            recent.append(msg)
        else:
            older.append(msg)
    
    if not older:
        return messages
    
    if count_messages_tokens(recent + older) <= max_tokens:
        return messages
    
    older_summary = f"[История из {len(older)} сообщений]"
    
    if older:
        sample = older[-3:] if len(older) > 3 else older
        summary_parts = []
        for msg in sample:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                content = "..." + str(content[-100:]) if len(str(content)) > 100 else str(content)
            summary_parts.append(f"{role}: {content}")
        
        older_summary = "\n".join(summary_parts[:5])
    
    return recent + [{"role": "user", "content": older_summary, "summary": True}]

class ContextManager:
    def __init__(
        self, 
        max_tokens: int = 120000,
        max_tool_results_tokens: int = 30000,
        summarize_threshold: int = 100000
    ):
        self.max_tokens = max_tokens
        self.max_tool_results_tokens = max_tool_results_tokens
        self.summarize_threshold = summarize_threshold
        self.model = "gpt-4"
    
    def prepare_messages(
        self, 
        messages: List[Dict], 
        system_message: Optional[Dict] = None,
        current_message: Optional[str] = None,
        tool_results: Optional[List[Dict]] = None
    ) -> List[Dict]:
        result = []
        
        if system_message:
            result.append(system_message)
        
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]
        
        available = self.max_tokens - estimate_tokens(system_message or {})
        
        if tool_results:
            tr_tokens = estimate_tokens(tool_results)
            if tr_tokens > self.max_tool_results_tokens:
                tool_results = self._trim_tool_results(tool_results)
                tr_tokens = estimate_tokens(tool_results)
            available -= tr_tokens
        
        trimmed = trim_messages(user_messages + assistant_messages, available)
        
        result.extend(trimmed)
        
        if tool_results:
            result.extend(tool_results)
        
        if current_message:
            result.append({"role": "user", "content": current_message})
        
        return result
    
    def _trim_tool_results(self, tool_results: List[Dict]) -> List[Dict]:
        trimmed = []
        total = 0
        
        for tr in reversed(tool_results):
            content = tr.get("content", "")
            
            if isinstance(content, str):
                if len(content) > 2000:
                    content = content[:1997] + "..."
            
            tr = {**tr, "content": content}
            tokens = estimate_tokens(tr)
            
            if total + tokens > self.max_tool_results_tokens:
                break
            
            trimmed.insert(0, tr)
            total += tokens
        
        return trimmed
    
    def get_stats(self, messages: List[Dict]) -> Dict[str, Any]:
        return {
            "total_messages": len(messages),
            "total_tokens": count_messages_tokens(messages),
            "max_tokens": self.max_tokens
        }
