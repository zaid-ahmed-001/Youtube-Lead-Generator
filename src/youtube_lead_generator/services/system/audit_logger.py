import time
from collections import deque

class AuditLogger:
    _logs = deque(maxlen=500)

    @classmethod
    def log(cls, username: str, action: str, details: str = ""):
        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "username": username or "System",
            "action": action,
            "details": details
        }
        cls._logs.appendleft(entry)
        print(f"AUDIT LOG [{entry['timestamp']}] User '{entry['username']}': {action} - {details}")

    @classmethod
    def get_logs(cls, limit: int = 100) -> list:
        return list(cls._logs)[:limit]
