from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_lead_generator.core.config import API_KEY
import os
import time
import threading

class APIKeyPoolManager:
    """
    Enterprise API Key Pool Manager.
    Handles multi-key registration, automatic key rotation on quota exceeded (403),
    usage tracking, and dynamic key addition.
    """
    _lock = threading.Lock()
    _keys = []
    _current_index = 0

    @classmethod
    def init(cls):
        with cls._lock:
            if cls._keys:
                return
            env_keys = os.environ.get("YOUTUBE_API_KEYS", "")
            keys_list = [k.strip() for k in env_keys.split(",") if k.strip()]
            if not keys_list and API_KEY:
                keys_list = [API_KEY]
            
            for k in keys_list:
                cls._keys.append({
                    "key": k,
                    "status": "active",
                    "usage_count": 0,
                    "last_used": None,
                    "exhausted_at": None
                })
            cls._current_index = 0

    @classmethod
    def add_key(cls, key_str: str) -> bool:
        """Dynamically registers a new YouTube API Key to the pool."""
        key_str = key_str.strip()
        if not key_str:
            return False
        with cls._lock:
            if any(k["key"] == key_str for k in cls._keys):
                return False
            cls._keys.append({
                "key": key_str,
                "status": "active",
                "usage_count": 0,
                "last_used": None,
                "exhausted_at": None
            })
            return True

    @classmethod
    def get_active_key_info(cls) -> dict:
        with cls._lock:
            if not cls._keys:
                cls.init()
            if not cls._keys:
                return {"key": None, "status": "none", "usage_count": 0}
            return cls._keys[cls._current_index]

    @classmethod
    def get_client(cls):
        """Returns a Google API client initialized with the current active key."""
        with cls._lock:
            if not cls._keys:
                cls.init()
            
            start_index = cls._current_index
            while cls._keys[cls._current_index]["status"] != "active":
                cls._current_index = (cls._current_index + 1) % len(cls._keys)
                if cls._current_index == start_index:
                    cls._reset_exhausted_keys_if_needed()
                    break

            active_info = cls._keys[cls._current_index]
            active_info["usage_count"] += 1
            active_info["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
            return build("youtube", "v3", developerKey=active_info["key"])

    @classmethod
    def mark_key_exhausted(cls, key_str=None):
        """Marks current or specified key as quota exhausted and rotates to next."""
        with cls._lock:
            target_key = key_str or cls._keys[cls._current_index]["key"]
            for k in cls._keys:
                if k["key"] == target_key:
                    k["status"] = "exhausted"
                    k["exhausted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            cls._current_index = (cls._current_index + 1) % len(cls._keys)

    @classmethod
    def execute_with_retry(cls, api_func, *args, **kwargs):
        """Executes a YouTube API call with automatic key rotation on 403 quotaExceeded."""
        attempts = 0
        max_attempts = max(1, len(cls._keys))
        
        while attempts < max_attempts:
            try:
                youtube_client = cls.get_client()
                return api_func(youtube_client, *args, **kwargs)
            except HttpError as e:
                if e.resp.status == 403 and ("quotaExceeded" in str(e) or "quota" in str(e).lower()):
                    print("[QUOTA WARNING] API Key Quota Exhausted! Rotating to next key in pool...")
                    cls.mark_key_exhausted()
                    attempts += 1
                else:
                    raise e
            except Exception as e:
                raise e

        raise RuntimeError("All registered YouTube API Keys in the pool have exhausted their daily quota!")

    @classmethod
    def get_pool_status(cls) -> list:
        with cls._lock:
            if not cls._keys:
                cls.init()
            return [dict(k) for k in cls._keys]

    @classmethod
    def _reset_exhausted_keys_if_needed(cls):
        """Resets key statuses if a new day has started."""
        for k in cls._keys:
            k["status"] = "active"


# Proxy object for backwards compatibility
class YouTubeClientProxy:
    def __getattr__(self, name):
        client = APIKeyPoolManager.get_client()
        return getattr(client, name)

youtube = YouTubeClientProxy()
APIKeyPoolManager.init()