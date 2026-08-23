import threading
import time as _time
import urllib.request

from app.core.constants import HOSTS_SOURCE_URLS
from app.core.logger import logger
from app.utils.helpers import extract_update_line


class HttpClient:
    _lock = threading.Lock()
    _cache: dict[str, tuple[float, str]] = {}
    CACHE_TTL = 300.0
    REMOTE_CACHE_TTL = 60.0
    _remote_main_line_cache: dict[str, tuple[float, tuple[str, str]]] = {}

    @classmethod
    def fetch(cls, url: str, timeout: int = 10, bypass_cache: bool = False) -> str:
        now = _time.time()
        key = url
        with cls._lock:
            if not bypass_cache and key in cls._cache:
                ts, content = cls._cache[key]
                if now - ts < cls.CACHE_TTL:
                    return content
        try:
            req = urllib.request.Request(
                f"{url}?t={int(now)}" if bypass_cache else url,
                headers={"User-Agent": "GoidaUnlocker/1.0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read().decode("utf-8", errors="ignore")
            with cls._lock:
                cls._cache[key] = (now, data)
            return data
        except Exception as e:
            logger.error("HTTP fetch failed for %s: %s", url, e)
            return ""

    @classmethod
    def get_remote_main_line_cached(cls, provider: str = "dns.malw.link") -> tuple[str, str]:
        """Возвращает (строка_обновления, дата) из удалённого hosts с коротким кэшем."""
        now = _time.time()
        with cls._lock:
            if provider in cls._remote_main_line_cache:
                ts, val = cls._remote_main_line_cache[provider]
                if now - ts < cls.REMOTE_CACHE_TTL:
                    return val
        try:
            url = HOSTS_SOURCE_URLS.get(provider) or HOSTS_SOURCE_URLS["dns.malw.link"]
            req = urllib.request.Request(
                f"{url}?t={int(now)}",
                headers={"User-Agent": "GoidaUnlocker/1.0", "Range": "bytes=0-1024"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            remote_line, remote_date = extract_update_line(data)
        except Exception:
            remote_line, remote_date = "", ""
        with cls._lock:
            cls._remote_main_line_cache[provider] = (now, (remote_line, remote_date))
        return remote_line, remote_date
