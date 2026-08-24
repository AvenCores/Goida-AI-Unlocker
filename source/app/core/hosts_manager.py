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


@dataclass(frozen=True)
class HostsStatusResult:
    key: str   # "not_installed" | "up_to_date" | "outdated"
    color: str
    date: str


class HostsManager:
    def __init__(self):
        self._cache: Optional[tuple[float, str]] = None
        self._lock = threading.Lock()
        self.backup_failed: bool = False
        # Флаг «служба DNS Client остановлена» на время агрессивной разблокировки;
        # apply() в finally перезапускает службу, если он установлен
        self._dnscache_stopped = False

    # ------------------------------------------------------------------
    # Чтение и статус
    # ------------------------------------------------------------------

    def read(self) -> str:
        if not HOSTS_PATH.exists():
            return ""
        try:
            mtime = HOSTS_PATH.stat().st_mtime
            with self._lock:
                if self._cache and self._cache[0] == mtime:
                    return self._cache[1]

            content = HOSTS_PATH.read_text(encoding="utf-8", errors="ignore")
            with self._lock:
                self._cache = (mtime, content)
            return content
        except Exception as e:
            logger.error("Failed to read hosts: %s", e)
            return ""

    def invalidate_cache(self):
        with self._lock:
            self._cache = None

    def is_installed(self, provider: str = "") -> bool:
        content = self.read()
        if provider == "geohide":
            return "dns.geohide.ru" in content
        if provider == "dns.malw.link":
            return "dns.malw.link" in content and "dns.geohide.ru" not in content
        return "dns.malw.link" in content or "dns.geohide.ru" in content

    @staticmethod
    def validate_content(content: str) -> bool:
        if "localhost" in content:
            return True
        return bool(_IP_LINE_RE.search(content))

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
                return path
            except Exception as e:
                logger.error("Backup attempt failed for %s: %s", backup_dir, e)
                last_error = e

        if last_error:
            logger.error("All backup attempts failed: %s", last_error)
        return None

    def get_backups_list(self) -> list[Path]:
        all_files: list[Path] = []
        seen_names: set[str] = set()
        for backup_dir in self._get_backup_dirs():
            if not backup_dir.is_dir():
                continue
            try:
                for f in backup_dir.iterdir():
                    if (
                        f.is_file()
                        and f.name.lower().startswith(HOSTS_BACKUP_PREFIX)
                        and f.name.lower().endswith(".txt")
                        and f.name not in seen_names
                    ):
                        seen_names.add(f.name)
                        all_files.append(f)
            except Exception as e:
                logger.debug("Failed to list backups in %s: %s", backup_dir, e)

        all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
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
        return self._normalize_hosts_content(actual_content) == self._normalize_hosts_content(expected_content)

    def _clear_readonly_attribute(self):
        if not HOSTS_PATH.exists():
            return
        try:
            import stat

            os.chmod(HOSTS_PATH, stat.S_IWRITE)
        except Exception as e:
            logger.debug("Failed to remove read-only attribute: %s", e)

    def _try_direct_copy(self, temp_path: str, content: str, retries: int = 3) -> bool:
        """Прямое копирование файла с повторами. При исчерпании повторов
        перевыбрасывает последнюю ошибку."""
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                shutil.copy(temp_path, HOSTS_PATH)
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
        try:
            r = subprocess.run(
                ["cmd", "/c", "copy", "/Y", temp_path, str(HOSTS_PATH)],
                creationflags=subprocess.CREATE_NO_WINDOW,
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

    def _try_cmd_type(self, temp_path: str, content: str) -> bool:
        """Резерв: перезапись через cmd /c type (обходит некоторые блокировки копирования)."""
        try:
            r = subprocess.run(
                ["cmd", "/c", "type", temp_path, ">", str(HOSTS_PATH)],
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=30,
                capture_output=True,
                shell=True,
            )
            if r.returncode == 0:
                _time.sleep(0.2)
                self.invalidate_cache()
                if self._verify_applied_content(content):
                    return True
        except Exception:
            pass
        return False

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

        # 2. Агрессивная разблокировка (остановка DNS Client, takeown, icacls) + повтор
        if is_windows_admin():
            logger.info("Attempting aggressive hosts unlock...")
            self._unlock_hosts_windows()
            self._dnscache_stopped = True
            try:
                if self._try_direct_copy(temp_path, content, retries=2):
                    self._flush_dns_windows()
                    return True
            except (PermissionError, OSError, RuntimeError) as e:
                logger.debug("Post-unlock direct copy failed: %s", e)

        # 3. Копирование с элевацией PowerShell (UAC при необходимости)
        ok, uac_denied = self._try_elevated_copy(temp_path, content)
        if ok:
            self._flush_dns_windows()
            return True

        # 4–6. cmd copy → cmd type → Windows API
        for writer in (self._try_cmd_copy, self._try_cmd_type, self._try_winapi_write):
            if writer(temp_path, content):
                self._flush_dns_windows()
                return True

        if uac_denied:
            raise PermissionError("UAC elevation was denied by user")
        if not is_windows_admin():
            raise PermissionError("UAC elevation was denied or PowerShell execution failed")
        raise RuntimeError(
            "All write methods failed. The hosts file may be locked by another process "
            "or protected by security software. Try closing other programs and retrying."
        )

    def _unlock_hosts_windows(self):
        """Агрессивная разблокировка hosts: остановка DNS Client, смена владельца, права."""
        hosts_str = str(HOSTS_PATH)
        steps = [
            ["net", "stop", "dnscache", "/y"],
            ["takeown", "/f", hosts_str],
            ["icacls", hosts_str, "/grant", "*S-1-5-32-544:F", "/c"],
            ["icacls", hosts_str, "/grant", "*S-1-1-0:F", "/c"],
            ["attrib", "-R", hosts_str],
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Set-ItemProperty -Path '{hosts_str}' -Name IsReadOnly -Value $false -ErrorAction SilentlyContinue",
            ],
        ]
        any_success = False
        for cmd in steps:
            try:
                r = subprocess.run(
                    cmd,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=15,
                    capture_output=True,
                )
                if r.returncode == 0:
                    any_success = True
                else:
                    logger.debug(
                        "Unlock step %s returned %d: %s",
                        cmd[0], r.returncode, r.stderr.decode(errors="ignore")[:200],
                    )
            except Exception as e:
                logger.debug("Unlock step %s failed: %s", cmd[0], e)
        return any_success

    def _restore_dns_service_windows(self):
        """Перезапуск службы DNS Client после изменения hosts."""
        try:
            subprocess.run(
                ["net", "start", "dnscache"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=15,
                capture_output=True,
            )
        except Exception:
            pass

    def _try_elevated_copy(self, temp_path: str, content: str) -> tuple[bool, bool]:
        """Копирование hosts через PowerShell с элевацией.

        Возвращает (успех, отказ_в_UAC).
        """
        ps_script_path: Optional[str] = None
        try:
            safe_src = temp_path.replace("'", "''")
            safe_dst = str(HOSTS_PATH).replace("'", "''")
            ps = (
                "$ErrorActionPreference = 'Stop'\n"
                f"$source = '{safe_src}'\n"
                f"$dest = '{safe_dst}'\n"
                "try {\n"
                "    if (Test-Path $dest) {\n"
                "        Set-ItemProperty -Path $dest -Name IsReadOnly -Value $false -ErrorAction SilentlyContinue\n"
                "    }\n"
                "    Copy-Item -LiteralPath $source -Destination $dest -Force\n"
                "    try { ipconfig /flushdns | Out-Null } catch {}\n"
                "    exit 0\n"
                "} catch {\n"
                "    exit 1\n"
                "}\n"
            )
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".ps1", encoding="utf-8") as f:
                f.write(ps)
                ps_script_path = f.name
            safe_script = ps_script_path.replace("'", "''")

            if is_windows_admin():
                r = subprocess.run(
                    [
                        "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                        "-ExecutionPolicy", "Bypass", "-File", ps_script_path,
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=60,
                    capture_output=True,
                )
                if r.returncode != 0:
                    logger.debug("PowerShell script failed (admin): %s", r.stderr.decode(errors="ignore"))
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
                r = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=90, capture_output=True)

            elevated = r.returncode == 0
            uac_denied = r.returncode == _UAC_CANCELLED_EXIT_CODE
            if not elevated and not uac_denied:
                logger.debug(
                    "PowerShell elevated copy failed: rc=%d stderr=%s",
                    r.returncode, r.stderr.decode(errors="ignore"),
                )
            if elevated:
                _time.sleep(0.3)
                self.invalidate_cache()
                if self._verify_applied_content(content):
                    return True, False
            return False, uac_denied
        except Exception as e:
            logger.debug("PowerShell elevated copy failed: %s", e)
            return False, False
        finally:
            if ps_script_path:
                safe_remove(ps_script_path)

    def _flush_dns_windows(self):
        try:
            subprocess.run(
                ["ipconfig", "/flushdns"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
                capture_output=True,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # macOS / Linux
    # ------------------------------------------------------------------

    def _write_macos(self, temp_path: str) -> bool:
        flush = (
            "dscacheutil -flushcache 2>/dev/null; "
            "killall -HUP mDNSResponder 2>/dev/null || true"
        )
        s_src = temp_path.replace("'", "'\\''")
        s_dst = str(HOSTS_PATH).replace("'", "'\\''")
        shell_cmd = f"cp '{s_src}' '{s_dst}' && chmod 644 '{s_dst}' && {flush}"

        if shutil.which("osascript"):
            applescript = f'do shell script "{shell_cmd}" with administrator privileges'
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
                r = subprocess.run(["sudo", "bash", "-c", shell_cmd], timeout=120)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    def _write_linux(self, temp_path: str) -> bool:
        flush = (
            "resolvectl flush-caches 2>/dev/null || "
            "systemd-resolve --flush-caches 2>/dev/null || "
            "/etc/init.d/nscd restart 2>/dev/null || "
            "killall -HUP dnsmasq 2>/dev/null || true"
        )
        s_src = temp_path.replace("'", "'\\''")
        s_dst = str(HOSTS_PATH).replace("'", "'\\''")
        bash_cmd = f"cp '{s_src}' '{s_dst}' && chmod 644 '{s_dst}' && {flush}"

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
                lines = content.splitlines()
                if len(lines) >= 5 and lines[0].startswith("# Goida AI Unlocker hosts backup"):
                    actual_hosts = "\n".join(lines[5:])
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
