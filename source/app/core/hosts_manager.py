import os
import sys
import threading
import tempfile
import subprocess
import shutil
import time as _time
import re as _re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from app.core.logger import logger
from app.core.constants import (
    COLOR_ERROR,
    COLOR_SUCCESS,
    HOSTS_PATH,
    HOSTS_BACKUP_DIR,
    HOSTS_BACKUP_PREFIX,
    HOSTS_SOURCE_URLS,
)
from app.core.http_client import HttpClient
from app.utils.helpers import (
    is_windows_admin,
    safe_remove,
    sanitize_backup_action,
    extract_update_line,
)

# Предкомпилированный regex для проверки содержимого
_IP_LINE_RE = _re.compile(r"^\s*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+\S+", _re.MULTILINE)
# Код возврата UAC при отказе пользователя
_UAC_CANCELLED_EXIT_CODE = 1223
_MAX_HOSTS_SIZE = 5 * 1024 * 1024
_BACKUP_HEADER_LINES = 5
_MAX_BACKUPS = 10

_NO_WINDOW_KWARGS: dict = {}
if sys.platform == "win32":
    _NO_WINDOW_KWARGS = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _run_quiet(cmd, **kwargs):
    kwargs = {**_NO_WINDOW_KWARGS, **kwargs}
    return subprocess.run(cmd, **kwargs)


@dataclass(frozen=True)
class HostsStatusResult:
    key: str   # "not_installed" | "up_to_date" | "outdated"
    color: str
    date: str


class HostsManager:
    def __init__(self):
        self._cache: Optional[tuple[tuple[int, int], str]] = None
        self._lock = threading.Lock()
        self.backup_failed: bool = False
        # Флаг «служба DNS Client остановлена» на время агрессивной разблокировки;
        # apply() в finally перезапускает службу, если он установлен
        self._dnscache_stopped = False
        self._dnscache_was_running = False
        self._last_elevated_detail = ""

    # ------------------------------------------------------------------
    # Чтение и статус
    # ------------------------------------------------------------------

    def read(self) -> str:
        if not HOSTS_PATH.exists():
            return ""
        try:
            st = HOSTS_PATH.stat()
            key = (st.st_mtime_ns, st.st_size)
            with self._lock:
                if self._cache and self._cache[0] == key:
                    return self._cache[1]

            content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
            try:
                st2 = HOSTS_PATH.stat()
                key = (st2.st_mtime_ns, st2.st_size)
            except Exception:
                pass
            with self._lock:
                self._cache = (key, content)
            return content
        except Exception as e:
            logger.error("Failed to read hosts: %s", e)
            return ""

    def invalidate_cache(self):
        with self._lock:
            self._cache = None

    def is_installed(self, provider: str = "") -> bool:
        content = self.read()
        # Игнорируем комментарии: маркер в комментарии != установленный обход
        hosts_lines = [
            ln for ln in content.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        body = "\n".join(hosts_lines)
        if provider == "geohide":
            return "dns.geohide.ru" in body
        if provider == "dns.malw.link":
            return "dns.malw.link" in body and "dns.geohide.ru" not in body
        return "dns.malw.link" in body or "dns.geohide.ru" in body

    @staticmethod
    def validate_content(content: str) -> bool:
        if not content or len(content.encode("utf-8", errors="ignore")) > _MAX_HOSTS_SIZE:
            return False
        valid = 0
        for line in content.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if len(parts) < 2:
                continue
            ip = parts[0]
            # IPv4 с проверкой октетов
            m = _re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", ip)
            if m:
                try:
                    if all(0 <= int(g) <= 255 for g in m.groups()):
                        valid += 1
                        continue
                except ValueError:
                    pass
            # IPv6 / hostname-записи засчитываем мягко
            if ":" in ip or _re.match(r"^[0-9a-fA-F:.]+$", ip):
                valid += 1
        return valid >= 1

    def check_status(self, provider: str = "dns.malw.link") -> HostsStatusResult:
        if not HOSTS_PATH.exists():
            return HostsStatusResult("not_installed", COLOR_ERROR, "")
        try:
            text = self.read()
            if not self.is_installed(provider):
                return HostsStatusResult("not_installed", COLOR_ERROR, "")

            local_line, _ = extract_update_line(text)
            remote_line, remote_date = HttpClient.get_remote_main_line_cached(provider)

            if local_line == remote_line and local_line.startswith("#"):
                return HostsStatusResult("up_to_date", COLOR_SUCCESS, remote_date)
            return HostsStatusResult("outdated", COLOR_ERROR, remote_date)
        except Exception:
            logger.exception("Status check failed")
            return HostsStatusResult("outdated", COLOR_ERROR, "")

    # ------------------------------------------------------------------
    # Резервные копии
    # ------------------------------------------------------------------

    @staticmethod
    def _get_backup_dirs() -> list[Path]:
        candidates = [
            HOSTS_BACKUP_DIR,
            Path(tempfile.gettempdir()) / "goida-ai-unlocker-backups",
        ]
        for env_var in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env_var)
            if base:
                candidates.append(Path(base) / "goida-ai-unlocker" / "hosts-backups")
        return list(dict.fromkeys(candidates))

    def backup(self, action: str) -> Optional[Path]:
        data = None
        if HOSTS_PATH.exists():
            try:
                data = HOSTS_PATH.read_bytes()
            except Exception as e:
                logger.error("Backup read bytes error: %s", e)
                try:
                    data = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore").encode("utf-8")
                except Exception as e2:
                    logger.error("Backup read text error: %s", e2)

        if data is None:
            if HOSTS_PATH.exists():
                # hosts существует, но нечитаем — НЕ подменяем его заглушкой,
                # иначе restore() затрёт реальный hosts пользователя
                logger.error("Cannot backup: hosts file exists but is unreadable")
                return None
            # hosts отсутствует — сохраняем минимальный дефолт для restore()
            data = b"# Initial hosts file\n127.0.0.1       localhost\n::1             localhost\n"

        last_error = None
        for backup_dir in self._get_backup_dirs():
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                tag = sanitize_backup_action(action)
                ts = _time.strftime("%Y%m%d_%H%M%S")
                ns = _time.time_ns() % 1_000_000

                name = f"{HOSTS_BACKUP_PREFIX}{tag}_{ts}_{ns:06d}.txt"
                path = backup_dir / name
                created = _time.strftime("%Y-%m-%d %H:%M:%S")
                header = (
                    f"# Goida AI Unlocker hosts backup\n"
                    f"# action {tag}\n"
                    f"# created_at {created}\n"
                    f"# source {HOSTS_PATH}\n\n"
                ).encode("utf-8")
                path.write_bytes(header + data)
                try:
                    self._prune_backups(backup_dir)
                except Exception:
                    pass
                return path
            except Exception as e:
                logger.error("Backup attempt failed for %s: %s", backup_dir, e)
                last_error = e

        if last_error:
            logger.error("All backup attempts failed: %s", last_error)
        return None

    def _prune_backups(self, backup_dir: Path):
        """Ротация: держим только последние _MAX_BACKUPS бэкапов."""
        try:
            files = [
                f for f in backup_dir.iterdir()
                if f.is_file() and f.name.lower().startswith(HOSTS_BACKUP_PREFIX)
                and f.name.lower().endswith(".txt")
            ]
        except Exception:
            return
        if len(files) <= _MAX_BACKUPS:
            return

        def _key(p: Path):
            try:
                return p.stat().st_mtime_ns
            except Exception:
                return 0

        files.sort(key=_key)
        for old in files[:-_MAX_BACKUPS]:
            try:
                old.unlink()
            except Exception:
                pass

    def get_backups_list(self) -> list[Path]:
        all_files: list[Path] = []
        seen: set[tuple[str, str]] = set()
        for backup_dir in self._get_backup_dirs():
            if not backup_dir.is_dir():
                continue
            try:
                entries = list(backup_dir.iterdir())
            except Exception as e:
                logger.debug("Failed to list backups in %s: %s", backup_dir, e)
                continue
            for f in entries:
                try:
                    if (
                        f.is_file()
                        and f.name.lower().startswith(HOSTS_BACKUP_PREFIX)
                        and f.name.lower().endswith(".txt")
                    ):
                        key = (f.name, str(backup_dir))
                        if key not in seen:
                            seen.add(key)
                            all_files.append(f)
                except Exception:
                    continue

        def _key(p: Path):
            try:
                return p.stat().st_mtime_ns
            except Exception:
                return 0

        all_files.sort(key=_key, reverse=True)
        return all_files

    def get_latest_backup(self) -> Optional[Path]:
        files = self.get_backups_list()
        return files[0] if files else None

    # ------------------------------------------------------------------
    # Запись hosts
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_hosts_content(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()

    def _verify_applied_content(self, expected_content: str) -> bool:
        try:
            actual_content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error("Failed to read hosts for verification: %s", e)
            return False
        ok = self._normalize_hosts_content(actual_content) == self._normalize_hosts_content(expected_content)
        if not ok:
            # Диагностика расхождения вместо молчаливого False: длины и
            # первая различающаяся строка (обрезано для лога)
            try:
                exp_lines = self._normalize_hosts_content(expected_content).splitlines()
                act_lines = self._normalize_hosts_content(actual_content).splitlines()
                diff_at = next(
                    (i for i, (a, b) in enumerate(zip(exp_lines, act_lines)) if a != b),
                    min(len(exp_lines), len(act_lines)),
                )
                logger.error(
                    "Hosts verification mismatch: expected %d lines/%d chars, "
                    "actual %d lines/%d chars, first diff at line %d: %r vs %r",
                    len(exp_lines), len(expected_content),
                    len(act_lines), len(actual_content), diff_at + 1,
                    exp_lines[diff_at] if diff_at < len(exp_lines) else "<eof>",
                    act_lines[diff_at] if diff_at < len(act_lines) else "<eof>",
                )
            except Exception:
                pass
        return ok

    def _clear_readonly_attribute(self):
        if not HOSTS_PATH.exists():
            return
        try:
            import stat

            st = HOSTS_PATH.stat()
            os.chmod(HOSTS_PATH, st.st_mode | stat.S_IWUSR | stat.S_IWGRP)
        except Exception as e:
            logger.debug("Failed to remove read-only attribute: %s", e)

    def _try_direct_copy(self, temp_path: str, content: str, retries: int = 3) -> bool:
        """Прямое копирование файла с повторами. При исчерпании повторов
        перевыбрасывает последнюю ошибку."""
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                shutil.copyfile(temp_path, HOSTS_PATH)
                try:
                    os.chmod(HOSTS_PATH, 0o644)
                except Exception:
                    pass
                self.invalidate_cache()
                if self._verify_applied_content(content):
                    return True
                last_err = RuntimeError("Verification failed: content mismatch after write")
                logger.debug("Direct copy attempt %d: verification failed", attempt + 1)
            except (PermissionError, OSError) as e:
                last_err = e
                logger.debug("Direct copy attempt %d failed: %s", attempt + 1, e)
            if attempt < retries - 1:
                _time.sleep(0.5)
        if last_err:
            raise last_err
        return False

    def _try_cmd_copy(self, temp_path: str, content: str) -> bool:
        """Резерв: копирование через cmd /c copy."""
        if sys.platform != "win32":
            return False
        try:
            r = _run_quiet(
                ["cmd", "/c", "copy", "/Y", temp_path, str(HOSTS_PATH)],
                timeout=30,
                capture_output=True,
            )
            if r.returncode == 0:
                _time.sleep(0.2)
                self.invalidate_cache()
                if self._verify_applied_content(content):
                    return True
        except Exception:
            pass
        return False

    def _try_powershell_copy(self, temp_path: str, content: str) -> bool:
        """Резерв: копирование через PowerShell Copy-Item без shell-редиректа."""
        if sys.platform != "win32":
            return False
        try:
            import os as _os

            env = _os.environ.copy()
            env["GOIDA_SRC"] = temp_path
            env["GOIDA_DST"] = str(HOSTS_PATH)
            r = _run_quiet(
                [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "Copy-Item -LiteralPath $env:GOIDA_SRC -Destination $env:GOIDA_DST -Force",
                ],
                timeout=30,
                capture_output=True,
                env=env,
            )
            if r.returncode == 0:
                _time.sleep(0.2)
                self.invalidate_cache()
                if self._verify_applied_content(content):
                    return True
        except Exception:
            pass
        return False

    # _try_cmd_type удалён: shell=True + список + ">" не работает как редирект
    # и даёт инъекцию. Вместо него — _try_powershell_copy выше.

    def _try_winapi_write(self, temp_path: str, content: str) -> bool:
        """Последний резерв: запись через Windows API (CreateFileW + WriteFile),
        минуя большинство файловых фильтров и sharing violations."""
        if sys.platform != "win32":
            return False
        try:
            import ctypes
            from ctypes import wintypes

            GENERIC_WRITE = 0x40000000
            FILE_SHARE_READ = 0x00000001
            FILE_SHARE_WRITE = 0x00000002
            FILE_SHARE_DELETE = 0x00000004
            CREATE_ALWAYS = 2
            FILE_ATTRIBUTE_NORMAL = 0x80
            INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            kernel32.CreateFileW.restype = ctypes.c_void_p
            kernel32.CreateFileW.argtypes = [
                ctypes.c_wchar_p,          # lpFileName
                wintypes.DWORD,            # dwDesiredAccess
                wintypes.DWORD,            # dwShareMode
                ctypes.c_void_p,           # lpSecurityAttributes
                wintypes.DWORD,            # dwCreationDisposition
                wintypes.DWORD,            # dwFlagsAndAttributes
                ctypes.c_void_p,           # hTemplateFile
            ]

            handle = kernel32.CreateFileW(
                str(HOSTS_PATH),
                GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None,
                CREATE_ALWAYS,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if handle == INVALID_HANDLE_VALUE or handle is None:
                logger.debug("CreateFileW failed with error code: %d", ctypes.get_last_error())
                return False

            try:
                data = content.encode("utf-8")
                written = wintypes.DWORD(0)

                kernel32.WriteFile.argtypes = [
                    ctypes.c_void_p,                 # hFile
                    ctypes.c_char_p,                 # lpBuffer
                    wintypes.DWORD,                  # nNumberOfBytesToWrite
                    ctypes.POINTER(wintypes.DWORD),  # lpNumberOfBytesWritten
                    ctypes.c_void_p,                 # lpOverlapped
                ]
                kernel32.WriteFile.restype = wintypes.BOOL

                success = kernel32.WriteFile(handle, data, len(data), ctypes.byref(written), None)
                if not success or written.value != len(data):
                    logger.debug("WriteFile failed or incomplete write")
                    return False
            finally:
                kernel32.CloseHandle(handle)

            _time.sleep(0.2)
            self.invalidate_cache()
            if self._verify_applied_content(content):
                return True
        except Exception as e:
            logger.debug("WinAPI write failed: %s", e)
        return False

    # ------------------------------------------------------------------
    # Windows: последовательность стратегий записи
    # ------------------------------------------------------------------

    def _write_windows(self, temp_path: str, content: str) -> bool:
        uac_denied = False

        # 1. Прямое копирование с повторами
        try:
            if self._try_direct_copy(temp_path, content):
                self._flush_dns_windows()
                return True
        except (PermissionError, OSError, RuntimeError) as e:
            logger.debug("Direct copy failed: %s", e)

        # 2. Агрессивная разблокировка (остановка DNS Client, права) + повтор
        if is_windows_admin():
            logger.info("Attempting aggressive hosts unlock...")
            stopped = self._unlock_hosts_windows()
            # Флаг ставим только если реально остановили запущенную службу
            if stopped:
                self._dnscache_stopped = True
            try:
                if self._try_direct_copy(temp_path, content, retries=2):
                    self._flush_dns_windows()
                    return True
            except (PermissionError, OSError, RuntimeError) as e:
                logger.debug("Post-unlock direct copy failed: %s", e)

        # 3. Копирование с элевацией PowerShell (UAC при необходимости).
        # hosts часто transient-лочится антивирусом/фильтрами сразу после выдачи
        # UAC: одна попытка даёт ложный "UAC denied", повтор через секунду успех.
        elevated_granted = False
        for attempt in range(3):
            ok, uac_denied = self._try_elevated_copy(temp_path, content)
            if ok:
                self._flush_dns_windows()
                return True
            if uac_denied:
                break
            elevated_granted = True
            logger.debug("Elevated copy attempt %d failed transiently, retrying...", attempt + 1)
            _time.sleep(1.0)

        # 4-6. cmd copy → powershell copy → Windows API
        for writer in (self._try_cmd_copy, self._try_powershell_copy, self._try_winapi_write):
            if writer(temp_path, content):
                self._flush_dns_windows()
                return True

        if uac_denied:
            raise PermissionError("UAC elevation was denied by user")
        if elevated_granted:
            # UAC был выдан, но запись не прошла с трёх попыток: показываем
            # реальную причину из дочернего процесса, а не generic-текст
            detail = (self._last_elevated_detail or "").strip()
            hint = f" Child says: {detail}" if detail else ""
            raise RuntimeError(
                "Elevated hosts write failed (elevation was granted, but the "
                f"copy did not stick).{hint} The file may be locked by antivirus "
                "or a system filter — please retry the operation."
            )
        if not is_windows_admin():
            raise PermissionError("UAC elevation was denied or PowerShell execution failed")
        raise RuntimeError(
            "All write methods failed. The hosts file may be locked by another process "
            "or protected by security software. Try closing other programs and retrying."
        )

    def _is_dnscache_running(self) -> bool:
        try:
            r = _run_quiet(["sc", "query", "dnscache"], timeout=10, capture_output=True, text=True)
            return r.returncode == 0 and "RUNNING" in (r.stdout or "")
        except Exception:
            return False

    def _unlock_hosts_windows(self):
        """Минимальная разблокировка hosts без смены владельца и Everyone:F."""
        hosts_str = str(HOSTS_PATH)
        was_running = self._is_dnscache_running()
        self._dnscache_was_running = was_running
        stopped = False
        if was_running:
            try:
                r = _run_quiet(["net", "stop", "dnscache", "/y"], timeout=15, capture_output=True)
                stopped = r.returncode == 0
            except Exception as e:
                logger.debug("net stop dnscache failed: %s", e)
        steps = [
            # Права только Administrators, НЕ Everyone (S-1-1-0)
            ["icacls", hosts_str, "/grant", "*S-1-5-32-544:F", "/c"],
            ["attrib", "-R", hosts_str],
        ]
        for cmd in steps:
            try:
                r = _run_quiet(cmd, timeout=15, capture_output=True)
                if r.returncode != 0:
                    logger.debug(
                        "Unlock step %s returned %d: %s",
                        cmd[0], r.returncode, (r.stderr or b"")[:200] if isinstance(r.stderr, bytes) else str(r.stderr)[:200],
                    )
            except Exception as e:
                logger.debug("Unlock step %s failed: %s", cmd[0], e)
        # Возвращаем True только если реально остановили работавшую службу
        return stopped

    def _restore_dns_service_windows(self):
        """Перезапуск службы DNS Client только если останавливали её мы."""
        if not self._dnscache_stopped or not self._dnscache_was_running:
            return
        try:
            _run_quiet(["net", "start", "dnscache"], timeout=15, capture_output=True)
        except Exception:
            pass

    def _try_elevated_copy(self, temp_path: str, content: str) -> tuple[bool, bool]:
        """Копирование hosts через PowerShell с элевацией.

        Возвращает (успех, отказ_в_UAC). Детали последней попытки кладутся
        в self._last_elevated_detail — иначе причина провала (текст ошибки
        дочернего процесса) теряется и пользователю показывается generic.
        """
        ps_script_path: Optional[str] = None
        log_path: Optional[str] = None
        self._last_elevated_detail = ""
        try:
            safe_src = temp_path.replace("'", "''")
            safe_dst = str(HOSTS_PATH).replace("'", "''")
            fd, log_path = tempfile.mkstemp(prefix="goida_ps_", suffix=".log")
            os.close(fd)
            safe_log = log_path.replace("'", "''")
            ps = (
                "$ErrorActionPreference = 'Stop'\n"
                f"$source = '{safe_src}'\n"
                f"$dest = '{safe_dst}'\n"
                f"$elog = '{safe_log}'\n"
                "$out = @()\n"
                "try {\n"
                "    if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {\n"
                "        $alt = Join-Path $env:SystemRoot 'Sysnative\\drivers\\etc\\hosts'\n"
                "        if (Test-Path -LiteralPath $alt) { $dest = $alt }\n"
                "    }\n"
                "    $out += \"DEST=$dest\"\n"
                "    $out += \"SRC_EXISTS=$(Test-Path -LiteralPath $source)\"\n"
                "    if (Test-Path -LiteralPath $dest) {\n"
                "        Set-ItemProperty -LiteralPath $dest -Name IsReadOnly -Value $false -ErrorAction SilentlyContinue\n"
                "    }\n"
                "    Copy-Item -LiteralPath $source -Destination $dest -Force\n"
                "    $out += 'COPIED'\n"
                "    try { ipconfig /flushdns | Out-Null } catch {}\n"
                "    $out += 'FLUSHED'\n"
                "    $out | Out-File -LiteralPath $elog -Encoding utf8\n"
                "    exit 0\n"
                "} catch {\n"
                "    $out += (\"ERROR: \" + $_.Exception.Message)\n"
                "    try { $out | Out-File -LiteralPath $elog -Encoding utf8 } catch {}\n"
                "    exit 1\n"
                "}\n"
            )
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ps1", encoding="utf-8") as f:
                f.write(ps)
                ps_script_path = f.name
            safe_script = ps_script_path.replace("'", "''")

            if is_windows_admin():
                r = _run_quiet(
                    [
                        "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                        "-ExecutionPolicy", "Bypass", "-File", ps_script_path,
                    ],
                    timeout=60,
                    capture_output=True,
                )
                if r.returncode != 0:
                    err = r.stderr.decode(errors="ignore") if isinstance(r.stderr, bytes) else (r.stderr or "")
                    logger.debug("PowerShell script failed (admin): %s", err)
            else:
                cmd = [
                    "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                    "-ExecutionPolicy", "Bypass", "-Command",
                    "$ErrorActionPreference = 'Stop'; "
                    "try { "
                    "$p = Start-Process powershell -Verb runAs -WindowStyle Hidden "
                    f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{safe_script}\"' "
                    "-Wait -PassThru -ErrorAction Stop; "
                    "if ($null -eq $p) { exit 1 }; "
                    "exit $p.ExitCode "
                    "} catch [System.OperationCanceledException] { "
                    f"exit {_UAC_CANCELLED_EXIT_CODE} "  # пользователь нажал «Нет» в UAC
                    "} catch { "
                    "exit 1 "
                    "}",
                ]
                r = _run_quiet(cmd, timeout=90, capture_output=True)

            elevated = r.returncode == 0
            uac_denied = r.returncode == _UAC_CANCELLED_EXIT_CODE
            child_tail = self._read_child_log_tail(log_path)
            if child_tail:
                self._last_elevated_detail = child_tail
            if not elevated and not uac_denied:
                err = r.stderr.decode(errors="ignore") if isinstance(r.stderr, bytes) else (r.stderr or "")
                logger.debug(
                    "PowerShell elevated copy failed: rc=%d stderr=%s child=%s",
                    r.returncode, err, child_tail,
                )
            if elevated:
                # Верификация с повторами: сразу после записи файл может
                # быть transient-залочен (Defender/фильтр) и чтение вернёт
                # старое содержимое — без повтора это ложный провал
                for i in range(3):
                    _time.sleep(0.5)
                    self.invalidate_cache()
                    if self._verify_applied_content(content):
                        return True, False
                logger.debug(
                    "Elevated copy reported success but verification failed "
                    "(transient lock?), child=%s — will retry outer loop",
                    child_tail,
                )
            return False, uac_denied
        except Exception as e:
            logger.debug("PowerShell elevated copy failed: %s", e)
            self._last_elevated_detail = str(e)
            return False, False
        finally:
            if ps_script_path:
                safe_remove(ps_script_path)
            if log_path:
                safe_remove(log_path)

    @staticmethod
    def _read_child_log_tail(log_path: Optional[str], limit: int = 500) -> str:
        """Хвост лога дочернего PowerShell (там реальная причина провала)."""
        if not log_path:
            return ""
        try:
            data = Path(log_path).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
        tail = "\n".join([ln for ln in data.splitlines() if ln.strip()][-6:])
        return tail[:limit]

    def _flush_dns_windows(self):
        try:
            _run_quiet(["ipconfig", "/flushdns"], timeout=10, capture_output=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # macOS / Linux
    # ------------------------------------------------------------------

    @staticmethod
    def _sh_quote(s: str) -> str:
        return "'" + s.replace("'", "'\\''") + "'"

    def _write_macos(self, temp_path: str) -> bool:
        import shlex

        flush = (
            "dscacheutil -flushcache 2>/dev/null; "
            "killall -HUP mDNSResponder 2>/dev/null || true"
        )
        s_src = self._sh_quote(temp_path)
        s_dst = self._sh_quote(str(HOSTS_PATH))
        shell_cmd = f"cp {s_src} {s_dst} && chmod 644 {s_dst} && {flush}"

        if shutil.which("osascript"):
            # Экранируем для AppleScript "..."
            as_cmd = shell_cmd.replace("\\", "\\\\").replace('"', '\\"')
            applescript = f'do shell script "{as_cmd}" with administrator privileges'
            try:
                r = subprocess.run(
                    ["osascript", "-e", applescript],
                    timeout=120,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if r.returncode == 0:
                    return True
            except Exception:
                pass

        if shutil.which("sudo"):
            try:
                # Без shell: sudo cp + chmod напрямую
                r1 = subprocess.run(["sudo", "cp", temp_path, str(HOSTS_PATH)], timeout=120)
                if r1.returncode == 0:
                    subprocess.run(["sudo", "chmod", "644", str(HOSTS_PATH)], timeout=30)
                    subprocess.run(["dscacheutil", "-flushcache"], timeout=15)
                    return True
            except Exception:
                pass
        return False

    def _write_linux(self, temp_path: str) -> bool:
        s_src = self._sh_quote(temp_path)
        s_dst = self._sh_quote(str(HOSTS_PATH))
        flush = (
            "resolvectl flush-caches 2>/dev/null || "
            "systemd-resolve --flush-caches 2>/dev/null || true"
        )
        bash_cmd = f"cp {s_src} {s_dst} && chmod 644 {s_dst} && {flush}"

        launchers = [("pkexec", ["pkexec"]), ("sudo", ["sudo"])]
        launchers += [(tool, [tool]) for tool in ("gksudo", "kdesudo")]
        for launcher, prefix in launchers:
            if shutil.which(launcher):
                try:
                    r = subprocess.run([*prefix, "bash", "-c", bash_cmd], timeout=120)
                    if r.returncode == 0:
                        return True
                except Exception:
                    continue
        return False

    # ------------------------------------------------------------------
    # Установка / восстановление
    # ------------------------------------------------------------------

    def apply(self, content: str) -> bool:
        """Записывает content в hosts. True при успехе, иначе RuntimeError/PermissionError."""
        if not self.validate_content(content):
            raise RuntimeError("Hosts content validation failed")

        self._clear_readonly_attribute()
        fd, temp_path = tempfile.mkstemp()
        os.close(fd)
        Path(temp_path).write_text(content, encoding="utf-8")

        try:
            if sys.platform == "win32":
                written = self._write_windows(temp_path, content)
            elif sys.platform == "darwin":
                written = self._write_macos(temp_path)
                if not written:
                    raise PermissionError("macOS elevation failed (osascript/sudo)")
            else:
                written = self._write_linux(temp_path)
                if not written:
                    raise PermissionError("Linux elevation failed (pkexec/sudo)")

            if not written:
                raise RuntimeError("Failed to write hosts file: no available write method succeeded")

            _time.sleep(0.3)
            self.invalidate_cache()
            if not self._verify_applied_content(content):
                raise RuntimeError(
                    "Hosts file write verification failed: the file may be locked by another process "
                    "or protected by security software"
                )
            return True
        finally:
            if self._dnscache_stopped:
                self._dnscache_stopped = False
                self._restore_dns_service_windows()
            safe_remove(temp_path)

    def update(self, provider: str = "dns.malw.link") -> bool:
        url = HOSTS_SOURCE_URLS.get(provider) or HOSTS_SOURCE_URLS["dns.malw.link"]
        self.backup_failed = not self.backup("install")
        if self.backup_failed:
            logger.warning("Failed to create hosts backup before install, proceeding anyway")

        content = HttpClient.fetch(url, bypass_cache=True)
        if not content:
            raise RuntimeError("Failed to download hosts file from remote repository")

        return self.apply(content)

    def restore(self, mode: str = "backup") -> bool:
        """Удаляет обход, восстанавливая hosts.

        mode: "backup" — восстановить из чистого бэкапа (fallback — дефолт);
        "clean" — записать полностью чистый hosts, игнорируя бэкапы.
        """
        self.backup_failed = not self.backup("uninstall")
        if self.backup_failed:
            logger.warning("Failed to create hosts backup before uninstall, proceeding anyway")

        if mode == "clean":
            return self.apply(self._default_hosts_content())

        original_content = self._find_clean_original_backup()

        if original_content is None:
            original_content = self._default_hosts_content()

        return self.apply(original_content)

    def _find_clean_original_backup(self) -> Optional[str]:
        """Ищет свежайший бэкап без записей обхода — это оригинальный hosts."""
        backups = self.get_backups_list()
        for backup_path in backups:
            try:
                content = backup_path.read_text(encoding="utf-8", errors="ignore")
                # Шапка бэкапа отделена пустой строкой — ищем разделитель, а не lines[5:]
                if content.startswith("# Goida AI Unlocker hosts backup"):
                    sep = content.find("\n\n")
                    actual_hosts = content[sep + 2:] if sep != -1 else content
                else:
                    actual_hosts = content

                if "dns.malw.link" not in actual_hosts and "dns.geohide.ru" not in actual_hosts:
                    if self.validate_content(actual_hosts):
                        logger.info("Found clean original hosts backup: %s", backup_path)
                        return actual_hosts
            except Exception as e:
                logger.error("Failed to read/parse backup %s: %s", backup_path, e)
        return None

    @staticmethod
    def _default_hosts_content() -> str:
        if sys.platform == "win32":
            return (
                "# Copyright (c) 1993-2009 Microsoft Corp.\n#\n"
                "# This is a sample HOSTS file used by Microsoft TCP/IP for Windows.\n#\n"
                "# This file contains the mappings of IP addresses to host names. Each\n"
                "# entry should be kept on an individual line. The IP address should\n"
                "# be placed in the first column followed by the corresponding host name.\n"
                "# The IP address and the host name should be separated by at least one\n# space.\n#\n"
                "# Additionally, comments (such as these) may be inserted on individual\n"
                "# lines or following the machine name denoted by a '#' symbol.\n#\n"
                "# For example:\n#\n#      102.54.94.97     rhino.acme.com          # source server\n"
                "#       38.25.63.10     x.acme.com              # x client host\n\n"
                "# localhost name resolution is handled within DNS itself.\n"
                "#   127.0.0.1       localhost\n#   ::1             localhost"
            )
        return "127.0.0.1       localhost\n::1             localhost\n"
