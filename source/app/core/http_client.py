import base64
import http.client
import io
import os
import socket
import ssl
import struct
import threading
import time as _time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache

from app.core.constants import (
    GEOHIDE_DNS_DOT_HOST,
    GEOHIDE_DNS_PRIMARY_IPV4,
    GEOHIDE_DNS_SECONDARY_IPV4,
    GEOHIDE_DNS_TERTIARY_IPV4,
    HOSTS_SOURCE_URLS,
    XBOX_DNS_DOT_HOST,
    XBOX_DNS_PRIMARY_IPV4,
    XBOX_DNS_SECONDARY_IPV4,
)
from app.core.logger import logger
from app.core.settings import get_setting
from app.utils.helpers import extract_update_line

_USER_AGENT = "GoidaUnlocker/1.0"
# Настройки DoH-резолвера (читаются на каждый резолв, применяются сразу)
DOH_ENABLED_SETTING = "doh_enabled"
DOH_PROVIDER_SETTING = "doh_provider"
DOH_DEFAULT_PROVIDER = "auto"
DOH_RESOLVER_OPTIONS = ("auto", "cloudflare", "google", "xbox-dns", "geohide-dns")
_DOH_AUTO_PROVIDERS = ("cloudflare", "google")
# Кандидаты подключения: (host, port, SNI|None). SNI задаётся при коннекте по
# фиксированному IP, чтобы сертификат проверялся по доменному имени.
# Доменные кандидаты не используются: их резолв идёт через системный DNS
# (тот самый suspect-компонент, ради обхода которого существует DoH) и не
# ограничивается сокетным таймаутом на этапе getaddrinfo.
# dns.malw.link не включён: его DoH требует HTTP/2 (RFC 8484 §5.2), а
# http.client из stdlib поддерживает только HTTP/1.1.
_DOH_RESOLVERS: dict[str, tuple[tuple[str, int, str | None], ...]] = {
    "cloudflare": (("1.1.1.1", 443, None),),
    "google": (("8.8.8.8", 443, None),),
    "xbox-dns": (
        (XBOX_DNS_PRIMARY_IPV4, 443, XBOX_DNS_DOT_HOST),
        (XBOX_DNS_SECONDARY_IPV4, 443, XBOX_DNS_DOT_HOST),
    ),
    "geohide-dns": (
        (GEOHIDE_DNS_PRIMARY_IPV4, 444, GEOHIDE_DNS_DOT_HOST),
        (GEOHIDE_DNS_SECONDARY_IPV4, 444, GEOHIDE_DNS_DOT_HOST),
        (GEOHIDE_DNS_TERTIARY_IPV4, 444, GEOHIDE_DNS_DOT_HOST),
    ),
}
_DOH_RFC8484_PATH = "/dns-query?dns={dns}"
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


def _doh_enabled() -> bool:
    return bool(get_setting(DOH_ENABLED_SETTING, True))


def _doh_auto_resolvers() -> tuple[tuple[str, int, str | None], ...]:
    return tuple(r for name in _DOH_AUTO_PROVIDERS for r in _DOH_RESOLVERS[name])


def _doh_resolvers() -> tuple[tuple[str, int, str | None], ...]:
    """Кандидаты подключения для резолвера, выбранного в настройках."""
    provider = get_setting(DOH_PROVIDER_SETTING, DOH_DEFAULT_PROVIDER)
    if provider == DOH_DEFAULT_PROVIDER:
        return _doh_auto_resolvers()
    if provider not in _DOH_RESOLVERS:
        logger.warning(
            "Unknown DoH resolver %r in settings, falling back to %s", provider, DOH_DEFAULT_PROVIDER
        )
        return _doh_auto_resolvers()
    return _DOH_RESOLVERS[provider]


def _encode_dns_query(hostname: str) -> tuple[int, bytes]:
    """Собирает DNS-запрос типа A по RFC 1035 (переносится через DoH, RFC 8484).

    Возвращает (query_id, пакет). Кидаем ValueError на некорректных именах:
    молча искажать имя (например, выкидывая не-ASCII символы) нельзя —
    иначе разрешится чужой хост, а ответ кэшируется под исходным именем.
    """
    wire_name = b""
    for label in hostname.strip(".").split("."):
        if not label:
            continue
        if label.isascii():
            raw = label.encode("ascii")
        else:
            try:
                raw = label.encode("idna")
            except UnicodeError as e:
                raise ValueError(f"invalid hostname label {label!r}: {e}") from None
        if len(raw) > 63:
            raise ValueError(f"hostname label too long: {label!r}")
        wire_name += bytes([len(raw)]) + raw
    if not wire_name or len(wire_name) + 1 > 253:
        raise ValueError(f"invalid hostname: {hostname!r}")
    query_id = int.from_bytes(os.urandom(2), "big")
    header = struct.pack(">HHHHHH", query_id, 0x0100, 1, 0, 0, 0)
    return query_id, header + wire_name + b"\x00" + struct.pack(">HH", 1, 1)


def _read_dns_name(payload: bytes, offset: int) -> tuple[str, int, int] | None:
    """Читает доменное имя из DNS-пакета с разбором сжатия (RFC 1035 §4.1.4).

    Возвращает (имя, offset после имени в записи, новый offset) или None на
    битом имени; прыжки по compression-указателям ограничены, чтобы
    цикл в указателях не мог подвесить разбор.
    """
    labels: list[str] = []
    jumps = 0
    after_name = None
    i = offset
    while True:
        if i >= len(payload):
            return None
        length = payload[i]
        if length == 0:
            joined = ".".join(labels).lower()
            return (joined, after_name if after_name is not None else i + 1, i + 1)
        if length & 0xC0 == 0xC0:
            if i + 1 >= len(payload):
                return None
            if after_name is None:
                after_name = i + 2
            jumps += 1
            if jumps > 16:
                return None
            i = int.from_bytes(payload[i:i + 2], "big") & 0x3FFF
            continue
        if length & 0xC0 or i + 1 + length > len(payload):
            return None
        labels.append(payload[i + 1:i + 1 + length].decode("ascii", errors="replace"))
        i += 1 + length


def _decode_dns_ipv4(payload: bytes, query_id: int, hostname: str) -> str | None:
    """Достаёт первый A-адрес из DNS-ответа, сверяя query ID и вопрос с запросом."""
    if len(payload) < 12:
        return None
    if int.from_bytes(payload[0:2], "big") != query_id:
        return None
    if int.from_bytes(payload[2:4], "big") & 0x8000 == 0 or payload[3] & 0x0F:
        return None  # не ответ либо NXDOMAIN/SERVFAIL и т.п.
    question = _read_dns_name(payload, 12)
    if question is None or question[0] != hostname.strip(".").lower():
        return None
    offset = question[1]
    qtype, qclass = payload[offset:offset + 2], payload[offset + 2:offset + 4]
    if qtype != b"\x00\x01" or qclass != b"\x00\x01":
        return None
    offset += 4
    for _ in range(int.from_bytes(payload[6:8], "big")):
        record = _read_dns_name(payload, offset)
        if record is None:
            return None
        offset = record[1]
        if offset + 10 > len(payload):
            return None
        rtype, rdlength = int.from_bytes(payload[offset:offset + 2], "big"), int.from_bytes(payload[offset + 8:offset + 10], "big")
        data_start = offset + 10
        if data_start + rdlength > len(payload):
            return None
        if rtype == 1 and rdlength == 4:
            return socket.inet_ntoa(payload[data_start:data_start + 4])
        offset = data_start + rdlength
    return None


def _doh_resolve(hostname: str, timeout: int = 5) -> str | None:
    """Резолвит имя через DoH выбранным в настройках сервером (RFC 8484).

    У сертификатов Cloudflare/Google IP-адреса включены в SAN, поэтому TLS
    проходит при коннекте напрямую по IP без системного DNS. Резолверы из
    constants (xbox-dns, geohide-dns) дают тот же обход: SNI/проверка
    сертификата идут по доменному имени при коннекте по их IP. Все кандидаты
    перебираются в рамках общего дедлайна timeout сек, чтобы недоступный
    провайдер не складывал таймауты друг на друга.
    """
    if not _doh_enabled():
        return None
    try:
        query_id, query = _encode_dns_query(hostname)
    except ValueError as e:
        logger.warning("Skipping DoH resolve for invalid hostname %s: %s", hostname, e)
        return None
    ctx = _ssl_context()
    deadline = _time.monotonic() + max(1, timeout)
    dns_param = base64.urlsafe_b64encode(query).rstrip(b"=").decode("ascii")
    query_path = _DOH_RFC8484_PATH.format(dns=dns_param)
    for host, port, sni in _doh_resolvers():
        remaining = deadline - _time.monotonic()
        if remaining < 1:
            logger.debug("DoH resolve budget exhausted for %s", hostname)
            break
        step_timeout = max(1, min(_DOH_STEP_TIMEOUT_CAP, remaining))
        conn = None
        try:
            if sni:
                conn = _PinnedHTTPSConnection(host, sni, port=port, timeout=step_timeout)
            else:
                conn = http.client.HTTPSConnection(host, port=port, timeout=step_timeout, context=ctx)
            conn.request(
                "GET",
                query_path,
                headers={
                    "accept": "application/dns-message",
                    "user-agent": _USER_AGENT,
                    "host": sni or host,
                },
            )
            resp = conn.getresponse()
            if resp.status == 200:
                ip = _decode_dns_ipv4(resp.read(), query_id, hostname)
                if ip:
                    return ip
            logger.debug("DoH resolve via %s:%s returned HTTP %s for %s", host, port, resp.status, hostname)
        except Exception as e:
            logger.debug("DoH resolve via %s:%s failed for %s: %s", host, port, hostname, e)
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS-соединение с фиксированным IP, но SNI/Host от исходного имени."""

    def __init__(self, ip: str, hostname: str, port: int = 443, timeout: int = 5):
        super().__init__(ip, port=port, timeout=timeout, context=_ssl_context())
        self._pinned_hostname = hostname

    def connect(self):
        sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock = self._context.wrap_socket(
            sock, server_hostname=self._pinned_hostname
        )


def _resolve_hostname(hostname: str, timeout: int) -> str | None:
    """DoH-резолв с TTL-кэшем (успех и неудача кэшируются раздельно)."""
    now = _time.time()
    provider = get_setting(DOH_PROVIDER_SETTING, DOH_DEFAULT_PROVIDER)
    key = f"{provider}|{hostname}"
    with _dns_cache_lock:
        cached = _dns_cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
    ip = _doh_resolve(hostname, timeout)
    ttl = _POSITIVE_DNS_TTL if ip else _NEGATIVE_DNS_TTL
    with _dns_cache_lock:
        _dns_cache[key] = (now + ttl, ip)
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
        conn = _PinnedHTTPSConnection(ip, hostname, timeout=timeout)
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
            if not _doh_enabled():
                raise
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
