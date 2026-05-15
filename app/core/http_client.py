import threading
import time as _time
import urllib.request
from typing import Optional
from app.core.logger import logger
from app.core.constants import ADDITIONAL_HOSTS_URL, _HOSTS_VERSION_BLOCK_RE, _HOSTS_CONTENT_RE
from app.utils.helpers import extract_update_line
import textwrap as _tw

class HttpClient:
    _lock = threading.Lock()
    _cache: dict[str, tuple[float, str]] = {}
    CACHE_TTL = 300.0
    REMOTE_CACHE_TTL = 60.0
    _remote_main_line_cache: Optional[tuple[float, tuple[str, str]]] = None
    _remote_add_ver_cache: Optional[tuple[float, str]] = None

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
                headers={"User-Agent": "GoidaUnlocker/1.0"}
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
    def fetch_additional_hosts(cls) -> tuple[str, str]:
        raw = cls.fetch(ADDITIONAL_HOSTS_URL, bypass_cache=True)
        if not raw:
            return "", ""
        ver_match = _HOSTS_VERSION_BLOCK_RE.search(raw)
        hosts_match = _HOSTS_CONTENT_RE.search(raw)
        version = ver_match.group(1) if ver_match else ""
        hosts_block = hosts_match.group(1).strip() if hosts_match else ""
        hosts_block = _tw.dedent(hosts_block)
        if not hosts_block:
            version = ""
        return version, hosts_block

    @classmethod
    def get_remote_main_line_cached(cls) -> tuple[str, str]:
        now = _time.time()
        with cls._lock:
            if cls._remote_main_line_cache and now - cls._remote_main_line_cache[0] < cls.REMOTE_CACHE_TTL:
                return cls._remote_main_line_cache[1]
        try:
            url = f"https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts?t={int(now)}"
            data = urllib.request.urlopen(url, timeout=10).read()
            remote_line, remote_date = extract_update_line(data)
        except Exception:
            remote_line, remote_date = "", ""
        with cls._lock:
            cls._remote_main_line_cache = (now, (remote_line, remote_date))
        return remote_line, remote_date

    @classmethod
    def get_remote_add_version_cached(cls) -> str:
        now = _time.time()
        with cls._lock:
            if cls._remote_add_ver_cache and now - cls._remote_add_ver_cache[0] < cls.REMOTE_CACHE_TTL:
                return cls._remote_add_ver_cache[1]
        try:
            ver = cls.fetch_additional_hosts()[0]
        except Exception:
            ver = ""
        with cls._lock:
            cls._remote_add_ver_cache = (now, ver)
        return ver
