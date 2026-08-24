import http.client
import io
import json as _json
import socket
import ssl
import threading
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

from app.core.constants import HOSTS_SOURCE_URLS
from app.core.logger import logger
from app.utils.helpers import extract_update_line

_USER_AGENT = "GoidaUnlocker/1.0"
_DOH_RESOLVER_IPS = ("1.1.1.1", "8.8.8.8")
_DOH_QUERY_PATH = "/dns-query?name={host}&type=A"
_DOH_STEP_TIMEOUT_CAP = 5      # сек: ограничение таймаута каждого DoH-шага
_POSITIVE_DNS_TTL = 300.0      # сек: кэш успешных резолвов
_NEGATIVE_DNS_TTL = 60.0       # сек: кэш неудачных резолвов
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_MAX_REDIRECTS = 3

_dns_cache: dict[str, tuple[float, str | None]] = {}
_dns_cache_lock = threading.Lock()


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    """Контекст с гарантированным набором корневых сертификатов.

    В frozen-сборке (PyInstaller onefile) бандловый OpenSSL может не найти
    системное хранилище CA (особенно на Fedora/OpenSUSE), из-за чего HTTPS
    падает с CERTIFICATE_VERIFY_FAILED. Используем certifi как основной
    источник и системный контекст как запасной.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        logger.debug("certifi unavailable, falling back to system CA store")
        return ssl.create_default_context()


def _doh_resolve(hostname: str, timeout: int = 5) -> str | None:
    """Резолвит имя через DoH-серверы по известным IP (Cloudflare/Google).

    У сертификатов 1.1.1.1 и 8.8.8.8 IP-адреса включены в SAN, поэтому
    TLS-проверка проходит без обращения к системному DNS. Позволяет обойти
    и сломанный/фильтрующий DNS провайдера (EAI_NODATA/EAI_NONAME), и
    записи в /etc/hosts.
    """
    ctx = _ssl_context()
    step_timeout = max(1, min(timeout, _DOH_STEP_TIMEOUT_CAP))
    for ip in _DOH_RESOLVER_IPS:
        conn = None
        try:
            conn = http.client.HTTPSConnection(ip, timeout=step_timeout, context=ctx)
            conn.request(
                "GET",
                _DOH_QUERY_PATH.format(host=hostname),
                headers={"accept": "application/dns-json", "User-Agent": _USER_AGENT},
            )
            resp = conn.getresponse()
            payload = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            for answer in payload.get("Answer", []):
                if answer.get("type") == 1:
                    return answer["data"]
        except Exception as e:
            logger.debug("DoH resolve via %s failed for %s: %s", ip, hostname, e)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS-соединение с фиксированным IP, но SNI/Host от исходного имени."""

    def __init__(self, ip: str, hostname: str, timeout: int):
        super().__init__(ip, timeout=timeout, context=_ssl_context())
        self._pinned_hostname = hostname

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(
            sock, server_hostname=self._pinned_hostname
        )


def _resolve_hostname(hostname: str, timeout: int) -> str | None:
    """DoH-резолв с TTL-кэшем (успех и неудача кэшируются раздельно)."""
    now = _time.time()
    with _dns_cache_lock:
        cached = _dns_cache.get(hostname)
        if cached and cached[0] > now:
            return cached[1]
    ip = _doh_resolve(hostname, timeout)
    ttl = _POSITIVE_DNS_TTL if ip else _NEGATIVE_DNS_TTL
    with _dns_cache_lock:
        _dns_cache[hostname] = (now + ttl, ip)
    return ip


def _fetch_via_doh(url: str, headers: dict, timeout: int):
    """Выполняет GET напрямую по IP, полученному через DoH.

    Проверяет статус ответа и следует редиректам (до _MAX_REDIRECTS),
    как это делал бы обычный urlopen. Возвращает file-like объект с телом
    ответа; при неудаче поднимает исключение.
    """
    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        parts = urllib.parse.urlsplit(current_url)
        hostname = parts.hostname
        scheme = parts.scheme.lower()
        if not hostname or scheme != "https":
            raise urllib.error.URLError(f"Unsupported URL for DoH fetch: {current_url}")
        ip = _resolve_hostname(hostname, timeout)
        if not ip:
            raise urllib.error.URLError(f"DNS lookup failed and DoH fallback unavailable for {hostname}")
        logger.warning("Falling back to direct connection via DoH-resolved %s (%s)", hostname, ip)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        request_headers = {"Host": hostname}
        request_headers.update(headers)
        conn = _PinnedHTTPSConnection(ip, hostname, timeout)
        try:
            conn.request("GET", target, headers=request_headers)
            resp = conn.getresponse()
            body = resp.read()
            status = resp.status
            resp_headers = resp.getheaders()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        if status in _REDIRECT_STATUSES:
            location = dict(resp_headers).get("Location")
            if not location:
                raise urllib.error.HTTPError(current_url, status, "Redirect without Location", resp_headers, io.BytesIO(body))
            current_url = urllib.parse.urljoin(current_url, location)
            continue
        if not 200 <= status < 300:
            raise urllib.error.HTTPError(current_url, status, resp.reason if hasattr(resp, "reason") else "", resp_headers, io.BytesIO(body))
        return io.BytesIO(body)
    raise urllib.error.HTTPError(url, 310, "Too many redirects", [], io.BytesIO(b""))


class HttpClient:
    _lock = threading.Lock()
    _cache: dict[str, tuple[float, str]] = {}
    CACHE_TTL = 300.0
    REMOTE_CACHE_TTL = 60.0
    _remote_main_line_cache: dict[str, tuple[float, tuple[str, str]]] = {}

    @classmethod
    def _urlopen(cls, url: str, headers: dict[str, str], timeout: int):
        """Открывает URL; при сетевом сбое повторяет через DoH-фолбэк.

        HTTPError (4xx/5xx) пробрасывается как есть — это валидный ответ,
        а вот проблемы соединения/DNS/hosts компенсируются прямым
        подключением к IP, полученному через DoH.
        """
        req = urllib.request.Request(url, headers=headers)
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            logger.warning("Direct fetch failed for %s: %s; trying DoH fallback", url, e)
            return _fetch_via_doh(url, headers, timeout)

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
            headers = {"User-Agent": _USER_AGENT}
            with cls._urlopen(
                f"{url}?t={int(now)}" if bypass_cache else url, headers, timeout
            ) as resp:
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
        remote_line, remote_date = "", ""
        try:
            url = HOSTS_SOURCE_URLS.get(provider) or HOSTS_SOURCE_URLS["dns.malw.link"]
            headers = {"User-Agent": _USER_AGENT, "Range": "bytes=0-1024"}
            with cls._urlopen(f"{url}?t={int(now)}", headers, 10) as resp:
                data = resp.read()
            remote_line, remote_date = extract_update_line(data)
        except Exception:
            pass
        with cls._lock:
            cls._remote_main_line_cache[provider] = (now, (remote_line, remote_date))
        return remote_line, remote_date
