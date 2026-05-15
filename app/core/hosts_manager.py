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
    extract_update_line, extract_additional_version
)
from app.gui.localization import tr

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
        mtime = HOSTS_PATH.stat().st_mtime
        with self._lock:
            if self._cache and self._cache[0] == mtime:
                return self._cache[1]
        try:
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

    def is_installed(self) -> bool:
        return "dns.malw.link" in self.read()

    def get_local_add_version(self) -> str:
        return extract_additional_version(self.read())

    @staticmethod
    def validate_content(content: str) -> bool:
        lines = content.strip().splitlines()
        valid = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2 and _re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", parts[0]):
                valid += 1
        return valid > 0 or "localhost" in content

    def backup(self, action: str) -> Optional[Path]:
        try:
            data = HOSTS_PATH.read_bytes()
        except Exception as e:
            logger.error("Backup read error: %s", e)
            return None
        try:
            HOSTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            tag = sanitize_backup_action(action)
            ts = _time.strftime("%Y%m%d_%H%M%S")
            ns = _time.time_ns() % 1_000_000
            name = f"{HOSTS_BACKUP_PREFIX}{tag}_{ts}_{ns:06d}.txt"
            path = HOSTS_BACKUP_DIR / name
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
            logger.error("Backup write error: %s", e)
            return None

    def get_latest_backup(self) -> Optional[Path]:
        if not HOSTS_BACKUP_DIR.is_dir():
            return None
        files = [
            f for f in HOSTS_BACKUP_DIR.iterdir()
            if f.is_file()
            and f.name.lower().startswith(HOSTS_BACKUP_PREFIX)
            and f.name.lower().endswith(".txt")
        ]
        return max(files, key=lambda p: p.stat().st_mtime) if files else None

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

    def apply(self, content: str) -> bool:
        temp_path: Optional[str] = None
        ps_script_path: Optional[str] = None

        try:
            if not self.validate_content(content):
                logger.error("Hosts content validation failed")
                return False

            fd, temp_path = tempfile.mkstemp()
            os.close(fd)
            Path(temp_path).write_text(content, encoding="utf-8")

            if sys.platform == "win32":
                safe_src = temp_path.replace("'", "''")
                safe_dst = str(HOSTS_PATH).replace("'", "''")
                safe_script = ""
                ps = (
                    "$ErrorActionPreference = 'Stop'\n"
                    f"$source = '{safe_src}'\n"
                    f"$dest = '{safe_dst}'\n"
                    "try {\n"
                    "    Copy-Item -LiteralPath $source -Destination $dest -Force\n"
                    "    try { Clear-DnsClientCache | Out-Null } catch {}\n"
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
                except Exception:
                    elevated = False

                if not elevated:
                    raise PermissionError(tr("admin_hint_windows"))
            else:
                flush = (
                    "resolvectl flush-caches 2>/dev/null || "
                    "systemd-resolve --flush-caches 2>/dev/null || "
                    "/etc/init.d/nscd restart 2>/dev/null || "
                    "killall -HUP dnsmasq 2>/dev/null || true"
                )
                if os.geteuid() == 0:
                    shutil.copy(temp_path, HOSTS_PATH)
                    os.chmod(HOSTS_PATH, 0o644)
                    subprocess.run(flush, shell=True)
                else:
                    s_src = temp_path.replace("'", "'\\''")
                    s_dst = str(HOSTS_PATH).replace("'", "'\\''")
                    bash_cmd = f"cp '{s_src}' '{s_dst}' && chmod 644 '{s_dst}' && {flush}"
                    elevated = False

                    for launcher, args in (
                        ("pkexec", ["pkexec", "bash", "-c", bash_cmd]),
                        ("sudo", ["sudo", "bash", "-c", bash_cmd]),
                    ):
                        if shutil.which(launcher):
                            try:
                                r = subprocess.run(args, timeout=120)
                                elevated = r.returncode == 0
                                if elevated:
                                    break
                            except Exception:
                                continue

                    if not elevated:
                        for su_tool in ("gksudo", "kdesudo"):
                            if shutil.which(su_tool):
                                try:
                                    r = subprocess.run([su_tool, "bash", "-c", bash_cmd], timeout=120)
                                    elevated = r.returncode == 0
                                    if elevated:
                                        break
                                except Exception:
                                    continue

                    if not elevated:
                        raise PermissionError(tr("admin_hint_unix"))

            _time.sleep(0.5)
            self.invalidate_cache()
            if not self._verify_applied_content(content):
                logger.error("Hosts apply verification failed: target file content does not match expected content")
                return False
            return True
        except Exception as e:
            logger.error("Apply hosts failed: %s", e)
            return False
        finally:
            if temp_path:
                safe_remove(temp_path)
            if ps_script_path:
                safe_remove(ps_script_path)

    def update(self) -> bool:
        url = "https://raw.githubusercontent.com/ImMALWARE/dns.malw.link/refs/heads/master/hosts"
        if not self.backup("install"):
            return False
        content = HttpClient.fetch(url)
        if not content:
            return False
        add_ver, add_hosts = HttpClient.fetch_additional_hosts()
        if add_hosts:
            content += f"\n# additional_hosts_version {add_ver}\n{add_hosts.strip()}\n"
        return self.apply(content)

    def restore(self) -> bool:
        if not self.backup("uninstall"):
            return False
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
        return self.apply(default_hosts)

    def check_status(self) -> HostsStatusResult:
        if not HOSTS_PATH.exists() or not self.is_installed():
            return HostsStatusResult("not_installed", "#e06c75", "")

        try:
            raw = HOSTS_PATH.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
            local_line, local_date = extract_update_line(raw)
            local_add_ver = extract_additional_version(text)

            remote_line, remote_date = "", ""
            remote_add_ver = ""

            def fetch_main():
                nonlocal remote_line, remote_date
                remote_line, remote_date = HttpClient.get_remote_main_line_cached()

            def fetch_add():
                nonlocal remote_add_ver
                remote_add_ver = HttpClient.get_remote_add_version_cached()

            t1 = threading.Thread(target=fetch_main, daemon=True)
            t2 = threading.Thread(target=fetch_add, daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=15)
            t2.join(timeout=15)

            main_match = local_line == remote_line and local_line.startswith("#")
            add_match = (local_add_ver == remote_add_ver) if remote_add_ver else (local_add_ver == "")

            if main_match and add_match:
                return HostsStatusResult("up_to_date", "#43b581", remote_date)
            return HostsStatusResult("outdated", "#e06c75", remote_date)
        except Exception:
            logger.exception("Status check failed")
            return HostsStatusResult("outdated", "#e06c75", "")
