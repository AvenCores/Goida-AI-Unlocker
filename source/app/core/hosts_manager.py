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
    HOSTS_PATH, HOSTS_BACKUP_DIR, HOSTS_BACKUP_PREFIX
)
from app.core.http_client import HttpClient
from app.utils.helpers import (
    is_windows_admin, safe_remove, sanitize_backup_action,
    extract_update_line
)

# Pre-compile regex for performance
_IP_RE = _re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

@dataclass(frozen=True)
class HostsStatusResult:
    key: str
    color: str
    date: str

class HostsManager:
    def __init__(self):
        self._cache: Optional[tuple[float, str]] = None
        self._lock = threading.Lock()

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
        elif provider == "dns.malw.link":
            return "dns.malw.link" in content and "dns.geohide.ru" not in content
        else:
            return "dns.malw.link" in content or "dns.geohide.ru" in content

    @staticmethod
    def validate_content(content: str) -> bool:
        if "localhost" in content:
            return True
        if _re.search(r"^\s*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\s+\S+", content, _re.MULTILINE):
            return True
        return False

    def backup(self, action: str) -> Optional[Path]:
        try:
            data = HOSTS_PATH.read_bytes()
        except Exception as e:
            logger.error("Backup read error: %s", e)
            return None

        # Try multiple locations for backup if primary fails
        dirs_to_try = [HOSTS_BACKUP_DIR]
        try:
            temp_fallback = Path(tempfile.gettempdir()) / "goida-ai-unlocker-backups"
            if temp_fallback != HOSTS_BACKUP_DIR:
                dirs_to_try.append(temp_fallback)
        except Exception:
            pass

        last_error = None
        for backup_dir in dirs_to_try:
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                tag = sanitize_backup_action(action)
                ts = _time.strftime("%Y%m%d_%H%M%S")
                # Fallback for time_ns if not available (Python < 3.7)
                try:
                    ns = _time.time_ns() % 1_000_000
                except (AttributeError, NotImplementedError):
                    ns = int((_time.time() * 1_000_000) % 1_000_000)

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
        # Try primary backup dir and fallback
        dirs_to_check = [HOSTS_BACKUP_DIR]
        try:
            temp_fallback = Path(tempfile.gettempdir()) / "goida-ai-unlocker-backups"
            if temp_fallback != HOSTS_BACKUP_DIR:
                dirs_to_check.append(temp_fallback)
        except Exception:
            pass

        all_files = []
        for backup_dir in dirs_to_check:
            if backup_dir.is_dir():
                files = [
                    f for f in backup_dir.iterdir()
                    if f.is_file()
                    and f.name.lower().startswith(HOSTS_BACKUP_PREFIX)
                    and f.name.lower().endswith(".txt")
                ]
                all_files.extend(files)

        all_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return all_files

    def get_latest_backup(self) -> Optional[Path]:
        files = self.get_backups_list()
        return files[0] if files else None

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

    def _try_direct_copy(self, temp_path: str, content: str, retries: int = 3) -> bool:
        """Try direct file copy with retries. Returns True on success, raises on final failure."""
        last_err = None
        for attempt in range(retries):
            try:
                shutil.copy(temp_path, HOSTS_PATH)
                if sys.platform == "win32":
                    subprocess.run(["ipconfig", "/flushdns"], creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                else:
                    self._flush_dns()
                self.invalidate_cache()
                if self._verify_applied_content(content):
                    return True
                last_err = RuntimeError("Verification failed: content mismatch after write")
            except (PermissionError, OSError) as e:
                last_err = e
            if attempt < retries - 1:
                _time.sleep(0.5)
        if last_err:
            raise last_err
        return False

    def _try_cmd_copy(self, temp_path: str, content: str) -> bool:
        """Fallback: use cmd /c copy on Windows."""
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

    def _unlock_hosts_windows(self) -> bool:
        """Aggressively unlock hosts file: stop DNS cache, take ownership, grant full control."""
        hosts_str = str(HOSTS_PATH)
        steps = [
            # Stop DNS Client service (it holds a lock on hosts)
            ["net", "stop", "dnscache", "/y"],
            # Take ownership of the file
            ["takeown", "/f", hosts_str],
            # Grant Administrators full control
            ["icacls", hosts_str, "/grant", "*S-1-5-32-544:F", "/c"],
            # Also grant current user full control
            ["icacls", hosts_str, "/grant", "*S-1-1-0:F", "/c"],
            # Remove read-only attribute via attrib
            ["attrib", "-R", hosts_str],
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
            except Exception as e:
                logger.debug("Unlock step %s failed: %s", cmd[0], e)
        return any_success

    def _restore_dns_service_windows(self):
        """Restart DNS Client service after hosts modification."""
        try:
            subprocess.run(
                ["net", "start", "dnscache"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=15,
                capture_output=True,
            )
        except Exception:
            pass

    def _try_winapi_write(self, content: str) -> bool:
        """Ultimate fallback: write hosts file directly via Windows API (CreateFileW + WriteFile).
        This bypasses most file system filter drivers and sharing violations."""
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

            # Set proper return type for 64-bit handle
            kernel32.CreateFileW.restype = ctypes.c_void_p
            kernel32.CreateFileW.argtypes = [
                ctypes.c_wchar_p,  # lpFileName
                wintypes.DWORD,    # dwDesiredAccess
                wintypes.DWORD,    # dwShareMode
                ctypes.c_void_p,   # lpSecurityAttributes
                wintypes.DWORD,    # dwCreationDisposition
                wintypes.DWORD,    # dwFlagsAndAttributes
                ctypes.c_void_p,   # hTemplateFile
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
                err = ctypes.get_last_error()
                logger.debug("CreateFileW failed with error code: %d", err)
                return False

            try:
                data = content.encode("utf-8")
                written = wintypes.DWORD(0)

                kernel32.WriteFile.argtypes = [
                    ctypes.c_void_p,        # hFile
                    ctypes.c_char_p,        # lpBuffer
                    wintypes.DWORD,         # nNumberOfBytesToWrite
                    ctypes.POINTER(wintypes.DWORD),  # lpNumberOfBytesWritten
                    ctypes.c_void_p,        # lpOverlapped
                ]
                kernel32.WriteFile.restype = wintypes.BOOL

                success = kernel32.WriteFile(
                    handle,
                    data,
                    len(data),
                    ctypes.byref(written),
                    None,
                )
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

    def apply(self, content: str) -> bool:
        """Apply content to hosts file. Returns True on success, raises RuntimeError on failure."""
        temp_path: Optional[str] = None
        ps_script_path: Optional[str] = None
        dns_stopped = False

        try:
            if not self.validate_content(content):
                raise RuntimeError("Hosts content validation failed")

            # Try to remove Read-Only attribute if hosts file exists
            if HOSTS_PATH.exists():
                try:
                    import stat
                    os.chmod(HOSTS_PATH, stat.S_IWRITE)
                except Exception as e:
                    logger.debug("Failed to remove read-only attribute: %s", e)

            fd, temp_path = tempfile.mkstemp()
            os.close(fd)
            Path(temp_path).write_text(content, encoding="utf-8")

            # --- Attempt 1: Direct copy with retries ---
            try:
                if self._try_direct_copy(temp_path, content):
                    return True
            except (PermissionError, OSError) as e:
                logger.debug("Direct copy failed: %s", e)
            except RuntimeError as e:
                logger.debug("Direct copy verification failed: %s", e)

            if sys.platform == "win32":
                # --- Attempt 2: Unlock hosts (stop DNS cache, takeown, icacls) + retry ---
                if is_windows_admin():
                    logger.info("Attempting aggressive hosts unlock...")
                    self._unlock_hosts_windows()
                    dns_stopped = True
                    try:
                        if self._try_direct_copy(temp_path, content, retries=2):
                            self._flush_dns_windows()
                            return True
                    except (PermissionError, OSError, RuntimeError) as e:
                        logger.debug("Post-unlock direct copy failed: %s", e)

                # --- Attempt 3: PowerShell elevated copy ---
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

                elevated = False
                try:
                    if is_windows_admin():
                        r = subprocess.run(
                            [
                                "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                                "-ExecutionPolicy", "Bypass", "-File", ps_script_path
                            ],
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=60
                        )
                    else:
                        cmd = [
                            "powershell", "-WindowStyle", "Hidden", "-NoProfile",
                            "-ExecutionPolicy", "Bypass", "-Command",
                            "$ErrorActionPreference = 'Stop'; "
                            "try { "
                            f"$p = Start-Process powershell -Verb runAs -WindowStyle Hidden "
                            f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{safe_script}\"' "
                            "-Wait -PassThru -ErrorAction Stop; "
                            "if ($null -eq $p) { exit 1 }; "
                            "exit $p.ExitCode "
                            "} catch { "
                            "exit 1 "
                            "}"
                        ]
                        r = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
                    elevated = r.returncode == 0
                except Exception as e:
                    logger.debug("PowerShell elevated copy failed: %s", e)
                    elevated = False

                if elevated:
                    _time.sleep(0.3)
                    self.invalidate_cache()
                    if self._verify_applied_content(content):
                        self._flush_dns_windows()
                        return True

                # --- Attempt 4: cmd /c copy ---
                if self._try_cmd_copy(temp_path, content):
                    self._flush_dns_windows()
                    return True

                # --- Attempt 5: Windows API direct write (ultimate fallback) ---
                if self._try_winapi_write(content):
                    self._flush_dns_windows()
                    return True

                # All attempts exhausted
                if not elevated and not is_windows_admin():
                    raise PermissionError("UAC elevation was denied or PowerShell execution failed")
                raise RuntimeError(
                    "All write methods failed. The hosts file may be locked by another process "
                    "or protected by security software. Try closing other programs and retrying."
                )

            elif sys.platform == "darwin":
                elevated = self._apply_macos_elevated(temp_path)
                if not elevated:
                    raise PermissionError("macOS elevation failed (osascript/sudo)")
            else:
                elevated = self._apply_unix_elevated(temp_path)
                if not elevated:
                    raise PermissionError("Linux elevation failed (pkexec/sudo)")

            _time.sleep(0.3)
            self.invalidate_cache()
            if not self._verify_applied_content(content):
                raise RuntimeError(
                    "Hosts file write verification failed: the file may be locked by another process "
                    "or protected by security software"
                )
            return True
        except (PermissionError, RuntimeError):
            raise
        except Exception as e:
            logger.error("Apply hosts failed: %s", e)
            raise RuntimeError(f"Failed to write hosts file: {e}")
        finally:
            if dns_stopped:
                self._restore_dns_service_windows()
            if temp_path:
                safe_remove(temp_path)
            if ps_script_path:
                safe_remove(ps_script_path)

    def _flush_dns_windows(self):
        """Flush DNS cache on Windows."""
        try:
            subprocess.run(
                ["ipconfig", "/flushdns"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10,
                capture_output=True,
            )
        except Exception:
            pass

    def _flush_dns(self):
        if sys.platform == "darwin":
            flush = (
                "dscacheutil -flushcache 2>/dev/null; "
                "killall -HUP mDNSResponder 2>/dev/null || true"
            )
        else:
            flush = (
                "resolvectl flush-caches 2>/dev/null || "
                "systemd-resolve --flush-caches 2>/dev/null || "
                "/etc/init.d/nscd restart 2>/dev/null || "
                "killall -HUP dnsmasq 2>/dev/null || true"
            )
        subprocess.run(flush, shell=True)

    def _apply_macos_elevated(self, temp_path: str) -> bool:
        flush = (
            "dscacheutil -flushcache 2>/dev/null; "
            "killall -HUP mDNSResponder 2>/dev/null || true"
        )
        s_src = temp_path.replace("'", "'\\''")
        s_dst = str(HOSTS_PATH).replace("'", "'\\''")
        shell_cmd = f"cp '{s_src}' '{s_dst}' && chmod 644 '{s_dst}' && {flush}"
        applescript = f'do shell script "{shell_cmd}" with administrator privileges'

        if shutil.which("osascript"):
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
                r = subprocess.run(
                    ["sudo", "bash", "-c", shell_cmd],
                    timeout=120,
                )
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    def _apply_unix_elevated(self, temp_path: str) -> bool:
        flush = (
            "resolvectl flush-caches 2>/dev/null || "
            "systemd-resolve --flush-caches 2>/dev/null || "
            "/etc/init.d/nscd restart 2>/dev/null || "
            "killall -HUP dnsmasq 2>/dev/null || true"
        )
        s_src = temp_path.replace("'", "'\\''")
        s_dst = str(HOSTS_PATH).replace("'", "'\\''")
        bash_cmd = f"cp '{s_src}' '{s_dst}' && chmod 644 '{s_dst}' && {flush}"

        for launcher, args in (
            ("pkexec", ["pkexec", "bash", "-c", bash_cmd]),
            ("sudo", ["sudo", "bash", "-c", bash_cmd]),
        ):
            if shutil.which(launcher):
                try:
                    r = subprocess.run(args, timeout=120)
                    if r.returncode == 0:
                        return True
                except Exception:
                    continue

        for su_tool in ("gksudo", "kdesudo"):
            if shutil.which(su_tool):
                try:
                    r = subprocess.run([su_tool, "bash", "-c", bash_cmd], timeout=120)
                    if r.returncode == 0:
                        return True
                except Exception:
                    continue
        return False


    def update(self, provider: str = "dns.malw.link") -> bool:
        if provider == "geohide":
            url = "https://github.com/Internet-Helper/GeoHideDNS/raw/refs/heads/main/hosts/hosts"
        else:
            url = "https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts"
        if not self.backup("install"):
            raise RuntimeError("Failed to create hosts backup before install")

        content = HttpClient.fetch(url, bypass_cache=True)
        if not content:
            raise RuntimeError("Failed to download hosts file from remote repository")

        return self.apply(content)

    def restore(self) -> bool:
        if not self.backup("uninstall"):
            raise RuntimeError("Failed to create hosts backup before uninstall")

        # Try to find a backup of the original hosts file
        original_content = None
        backups = self.get_backups_list()

        for backup_path in backups:
            try:
                content = backup_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()
                if len(lines) >= 5 and lines[0].startswith("# Goida AI Unlocker hosts backup"):
                    actual_hosts = "\n".join(lines[5:])
                else:
                    actual_hosts = content

                # If this backup does not contain any bypass entries, it's our original hosts file!
                if "dns.malw.link" not in actual_hosts and "dns.geohide.ru" not in actual_hosts:
                    original_content = actual_hosts
                    logger.info("Found clean original hosts backup: %s", backup_path)
                    break
            except Exception as e:
                logger.error("Failed to read/parse backup %s: %s", backup_path, e)

        if original_content is not None:
            # Let's ensure it has at least localhost entries just to be safe
            if not self.validate_content(original_content):
                original_content = None

        if original_content is None:
            # Fallback to default clean hosts if no backup was found or if it was invalid
            default_hosts = "127.0.0.1       localhost\n::1             localhost\n"
            if sys.platform == "win32":
                default_hosts = (
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
            original_content = default_hosts

        return self.apply(original_content)

    def check_status(self, provider: str = "dns.malw.link") -> HostsStatusResult:
        if not HOSTS_PATH.exists():
            return HostsStatusResult("not_installed", "#e06c75", "")

        try:
            text = self.read()
            if not self.is_installed(provider):
                return HostsStatusResult("not_installed", "#e06c75", "")

            local_line, local_date = extract_update_line(text)
            remote_line, remote_date = HttpClient.get_remote_main_line_cached(provider)

            main_match = local_line == remote_line and local_line.startswith("#")

            if main_match:
                return HostsStatusResult("up_to_date", "#43b581", remote_date)
            return HostsStatusResult("outdated", "#e06c75", remote_date)
        except Exception:
            logger.exception("Status check failed")
            return HostsStatusResult("outdated", "#e06c75", "")
