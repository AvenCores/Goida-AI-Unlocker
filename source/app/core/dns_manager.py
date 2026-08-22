import base64
import json
import platform
import re
import subprocess
import threading
import time
from dataclasses import dataclass

from app.core.constants import (
    XBOX_DNS_SERVERS,
    XBOX_DNS_SERVERS_IPV6,
    XBOX_DNS_SITE_URL,
    GEOHIDE_DNS_SERVERS,
    GEOHIDE_DNS_SERVERS_IPV6,
    GEOHIDE_DNS_SITE_URL,
    MALW_DNS_SERVERS,
    MALW_DNS_SERVERS_IPV6,
    MALW_DNS_SITE_URL,
)
from app.core.logger import logger
from app.core.settings import get_setting, set_setting
from app.utils.helpers import is_windows_admin

IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Ключ настроек, в котором хранятся оригинальные DNS-серверы для восстановления
_ORIGINAL_DNS_SETTING_KEY = "original_dns_servers"
# Маркер, который записывается в настройки при установке Xbox DNS
DNS_PROVIDER_ID = "xbox-dns"

# Реестр DNS-провайдеров: id -> (ключ перевода, IPv4-серверы, IPv6-серверы)
DNS_PROVIDERS = {
    "xbox-dns": {
        "name_key": "provider_xbox_dns",
        "ipv4": XBOX_DNS_SERVERS,
        "ipv6": XBOX_DNS_SERVERS_IPV6,
    },
    "geohide-dns": {
        "name_key": "provider_geohide_dns",
        "ipv4": GEOHIDE_DNS_SERVERS,
        "ipv6": GEOHIDE_DNS_SERVERS_IPV6,
    },
    "malw-dns": {
        "name_key": "provider_malw_dns",
        "ipv4": MALW_DNS_SERVERS,
        "ipv6": MALW_DNS_SERVERS_IPV6,
    },
}


def get_dns_providers() -> list:
    """Возвращает список (отображаемое имя, id) всех DNS-провайдеров."""
    from app.gui.localization import tr
    return [(tr(cfg["name_key"]), pid) for pid, cfg in DNS_PROVIDERS.items()]


def get_dns_provider_servers(provider_id: str) -> tuple:
    """Возвращает (ipv4, ipv6) серверы для указанного провайдера."""
    cfg = DNS_PROVIDERS.get(provider_id) or DNS_PROVIDERS[DNS_PROVIDER_ID]
    return cfg["ipv4"], cfg["ipv6"]

# Виртуальные/служебные адаптеры, которые нельзя трогать (VMware, VirtualBox и т.п.)
_VIRTUAL_ADAPTER_RE = re.compile(
    r"vmware|virtualbox|vbox|hyper-v|wsl|loopback|tap-|tunnel|vpn|"
    r"wi-fi direct|bluetooth|microsoft kernel|virtual",
    re.IGNORECASE,
)
# Код возврата UAC при отказе пользователя
_UAC_CANCELLED_EXIT_CODE = 1223


@dataclass(frozen=True)
class DnsStatusResult:
    key: str      # "not_installed" | "installed"
    color: str    # hex-цвет для GUI
    date: str     # дополнительная информация (адреса DNS)


def _run_command(cmd, timeout=30):
    """Запускает команду и возвращает (returncode, stdout+stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        return -1, "command not found"
    except subprocess.TimeoutExpired:
        return -1, "command timed out"
    except Exception as e:
        return -1, str(e)


class DnsManager:
    """Менеджер разблокировки через смену системных DNS-серверов (Xbox DNS).

    Повторяет интерфейс HostsManager (update/restore/is_installed/check_status),
    чтобы воркеры и GUI могли работать с обоими менеджерами полиморфно.
    """

    def __init__(self):
        self.threading_lock = threading.Lock()
        self.backup_failed = False
        # Кэш результата is_installed: каждый вызов запускает PowerShell (~1 сек),
        # поэтому без кэша UI «тормозит» при каждом обновлении статуса
        self._install_cache = {}          # provider_id -> bool
        self._install_cache_ts = {}       # provider_id -> timestamp
        self._install_cache_ttl = 5.0     # секунды

    # ------------------------------------------------------------------
    # Публичный интерфейс (совместим с HostsManager)
    # ------------------------------------------------------------------

    def is_installed(self, provider: str = DNS_PROVIDER_ID) -> bool:
        """Проверяет, установлены ли DNS-серверы выбранного провайдера.

        Результат кэшируется на несколько секунд: каждая проверка запускает
        PowerShell (~1 сек), что заметно тормозило UI.
        """
        if provider not in DNS_PROVIDERS:
            return False
        now = time.monotonic()
        ts = self._install_cache_ts.get(provider)
        if ts is not None and (now - ts) < self._install_cache_ttl:
            return self._install_cache[provider]
        ipv4_servers, _ = get_dns_provider_servers(provider)
        active = self._get_active_interfaces()
        result = False
        for iface in active:
            current = self._get_interface_dns(iface)
            if current and all(server in current for server in ipv4_servers):
                result = True
                break
        self._install_cache[provider] = result
        self._install_cache_ts[provider] = now
        return result

    def invalidate_install_cache(self):
        """Сбрасывает кэш is_installed (после установки/удаления DNS)."""
        self._install_cache.clear()
        self._install_cache_ts.clear()

    def update(self, provider: str = DNS_PROVIDER_ID) -> bool:
        """Устанавливает DNS-серверы выбранного провайдера на все активные интерфейсы."""
        if provider not in DNS_PROVIDERS:
            raise RuntimeError(f"Unknown DNS provider: {provider}")
        ipv4_servers, ipv6_servers = get_dns_provider_servers(provider)
        with self.threading_lock:
            self._save_original_dns()
            ok = self._apply_dns_to_all(list(ipv4_servers), list(ipv6_servers))
            if ok:
                self._flush_dns_cache()
            self.invalidate_install_cache()
            return ok

    def restore(self) -> bool:
        """Восстанавливает оригинальные DNS-серверы (или DHCP/авто)."""
        with self.threading_lock:
            ok = self._restore_original_dns()
            if ok:
                self._flush_dns_cache()
                set_setting(_ORIGINAL_DNS_SETTING_KEY, None)
            self.invalidate_install_cache()
            return ok

    def check_status(self, provider: str = DNS_PROVIDER_ID) -> DnsStatusResult:
        ipv4_servers, _ = get_dns_provider_servers(provider)
        if self.is_installed(provider):
            return DnsStatusResult("installed", "#4caf50", ", ".join(ipv4_servers))
        return DnsStatusResult("not_installed", "#9e9e9e", ", ".join(ipv4_servers))

    def apply(self, _content: str) -> bool:
        """Для совместимости с HostsWorker: у DNS-механизма нет контента."""
        return self.update(DNS_PROVIDER_ID)

    def invalidate_cache(self):
        pass

    def read(self) -> str:
        """Для совместимости: возвращает текущее состояние DNS в текстовом виде."""
        lines = [f"# Xbox DNS status ({XBOX_DNS_SITE_URL})"]
        for iface in self._get_active_interfaces():
            dns = self._get_interface_dns(iface)
            lines.append(f"{iface}: {', '.join(dns) if dns else 'auto (DHCP)'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Сохранение/восстановление оригинальных DNS
    # ------------------------------------------------------------------

    def _save_original_dns(self):
        """Сохраняет оригинальные настройки DNS перед установкой.

        Важно различать DHCP и статику: если адрес получен по DHCP,
        при восстановлении нужно вернуть режим «авто», а не вписывать
        адрес роутера как статический.
        """
        try:
            snapshot = {}
            for iface in self._get_active_interfaces():
                dns = self._get_interface_dns(iface)
                if not dns:
                    # Нет статических записей — DNS по DHCP (или авто)
                    snapshot[iface] = {"source": "dhcp", "servers": []}
                    continue
                static = self._is_interface_dns_static(iface)
                source = "static" if static else "dhcp"
                snapshot[iface] = {"source": source, "servers": dns}
            set_setting(_ORIGINAL_DNS_SETTING_KEY, snapshot)
        except Exception:
            logger.exception("Failed to save original DNS servers")

    def _restore_original_dns(self) -> bool:
        snapshot = get_setting(_ORIGINAL_DNS_SETTING_KEY) or {}
        active = self._get_active_interfaces()
        if not active:
            raise RuntimeError("No active network interfaces found")
        ok = True
        for iface in active:
            original = snapshot.get(iface)
            if original and original.get("source") == "static" and original.get("servers"):
                # Статические настройки — восстанавливаем сохранённые адреса
                ok = self._set_interface_dns(iface, original["servers"], []) and ok
            else:
                # DHCP/авто — сбрасываем на автоматический режим
                ok = self._reset_interface_dns(iface) and ok
        return ok

    # ------------------------------------------------------------------
    # Определение интерфейсов и текущих DNS
    # ------------------------------------------------------------------

    def _get_active_interfaces(self) -> list:
        if IS_WINDOWS:
            return self._get_active_interfaces_windows()
        if IS_MACOS:
            return self._get_active_services_macos()
        return self._get_active_interfaces_linux()

    def _get_active_interfaces_windows(self) -> list:
        ps_script = (
            "Get-NetAdapter | Where-Object { $_.Status -eq 'Up' } | "
            "Select-Object -ExpandProperty Name"
        )
        code, output = _run_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        )
        if code != 0:
            return []
        ifaces = [line.strip() for line in output.splitlines() if line.strip()]
        # Исключаем виртуальные/служебные адаптеры (VMware, VirtualBox и т.п.)
        return [i for i in ifaces if not _VIRTUAL_ADAPTER_RE.search(i)]

    def _get_active_services_macos(self) -> list:
        code, output = _run_command(["networksetup", "-listallnetworkservices"])
        if code != 0:
            return []
        services = []
        for line in output.splitlines()[1:]:
            name = line.strip()
            if name and not name.startswith("*"):
                services.append(name)
        return services

    def _get_active_interfaces_linux(self) -> list:
        code, output = _run_command(["ip", "-o", "link", "show", "up"])
        if code != 0:
            return []
        ifaces = []
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) >= 2:
                name = parts[1].strip()
                if name and name != "lo":
                    ifaces.append(name)
        return ifaces

    def _get_interface_dns(self, iface: str) -> list:
        if IS_WINDOWS:
            return self._get_interface_dns_windows(iface)
        if IS_MACOS:
            return self._get_interface_dns_macos(iface)
        return self._get_interface_dns_linux(iface)

    def _get_interface_dns_windows(self, iface: str) -> list:
        ps_script = (
            f"(Get-DnsClientServerAddress -InterfaceAlias '{iface}' -AddressFamily IPv4 | "
            "Select-Object -ExpandProperty ServerAddresses)"
        )
        code, output = _run_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        )
        if code != 0:
            return []
        return [line.strip() for line in output.splitlines() if line.strip()]

    def _is_interface_dns_static(self, iface: str) -> bool:
        """Определяет, задан ли DNS статически (True) или по DHCP/авто (False)."""
        if IS_WINDOWS:
            # Тип адресации надёжнее определять через реестр интерфейса:
            # пустой NameServer = DHCP, непустой = статические адреса
            ps_script = (
                "$guid = (Get-NetAdapter -InterfaceAlias '" + iface + "').InterfaceGuid; "
                "$reg = 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters\\Interfaces\\' + $guid; "
                "(Get-ItemProperty -Path $reg -Name NameServer -ErrorAction SilentlyContinue).NameServer"
            )
            code, output = _run_command(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
            )
            if code != 0:
                # Не смогли определить — считаем DHCP (безопаснее: сброс на авто)
                return False
            value = output.strip()
            # Пустая строка = DNS по DHCP; непустая = статические адреса
            return bool(value)
        if IS_MACOS:
            # networksetup: если DNS задан, getdnsservers возвращает адреса,
            # иначе сообщение "There aren't any DNS Servers set"
            dns = self._get_interface_dns_macos(iface)
            return bool(dns)
        # Linux: resolvectl показывает текущие DNS независимо от источника;
        # считаем статикой, если записи есть (resolvectl revert вернёт авто)
        dns = self._get_interface_dns_linux(iface)
        return bool(dns)

    def _get_interface_dns_macos(self, service: str) -> list:
        code, output = _run_command(
            ["networksetup", "-getdnsservers", service]
        )
        if code != 0:
            return []
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        # networksetup выводит "There aren't any DNS Servers set on ..." при авто-режиме
        if len(lines) == 1 and "aren't any" in lines[0]:
            return []
        return lines

    def _get_interface_dns_linux(self, iface: str) -> list:
        code, output = _run_command(["resolvectl", "dns", iface])
        if code != 0:
            return []
        # Формат: "Link 2 (eth0): 111.88.96.50 111.88.96.51"
        if ":" in output:
            part = output.split(":", 1)[1].strip()
            return part.split()
        return []

    # ------------------------------------------------------------------
    # Применение DNS
    # ------------------------------------------------------------------

    def _apply_dns_to_all(self, ipv4_servers, ipv6_servers) -> bool:
        active = self._get_active_interfaces()
        if not active:
            raise RuntimeError("No active network interfaces found")
        ok = True
        for iface in active:
            ok = self._set_interface_dns(iface, list(ipv4_servers), list(ipv6_servers)) and ok
        return ok

    def _set_interface_dns(self, iface: str, ipv4: list, ipv6: list) -> bool:
        if IS_WINDOWS:
            return self._set_interface_dns_windows(iface, ipv4, ipv6)
        if IS_MACOS:
            return self._set_interface_dns_macos(iface, ipv4 + ipv6)
        return self._set_interface_dns_linux(iface, ipv4 + ipv6)

    def _set_interface_dns_windows(self, iface: str, ipv4: list, ipv6: list) -> bool:
        servers = ipv4 + ipv6
        quoted = ", ".join(f"'{s}'" for s in servers)
        ps_script = (
            f"Set-DnsClientServerAddress -InterfaceAlias '{iface}' "
            f"-ServerAddresses ({quoted})"
        )
        code, output = _run_command(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script]
        )
        if code == 0:
            return True

        # Прямой вызов требует прав администратора (CIM PermissionDenied).
        # Если мы не админ — сразу элевация через UAC (скрытое окно),
        # чтобы не тратить время на заведомо бесполезные попытки.
        if not is_windows_admin():
            return self._set_interface_dns_elevated(iface, servers)

        logger.warning("Direct Set-DnsClientServerAddress failed on %s: %s", iface, output.strip())
        # Мы уже админ — пробуем netsh как альтернативу
        if self._set_interface_dns_netsh(iface, ipv4):
            return True
        logger.error("Failed to set DNS on %s even with admin rights", iface)
        return False

    def _set_interface_dns_elevated(self, iface: str, servers: list) -> bool:
        """Устанавливает DNS через UAC-элевацию (скрытое окно, как в hosts_manager)."""
        quoted_servers = ", ".join(f"'{s}'" for s in servers)
        inner = (
            f"Set-DnsClientServerAddress -InterfaceAlias '{iface}' "
            f"-ServerAddresses ({quoted_servers})"
        )
        encoded = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
        launcher = (
            "$ErrorActionPreference = 'Stop'; "
            "try { "
            "$p = Start-Process powershell -Verb runAs -WindowStyle Hidden "
            f"-ArgumentList '-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {encoded}' "
            "-Wait -PassThru -ErrorAction Stop; "
            "if ($null -eq $p) { exit 1 }; "
            "exit $p.ExitCode "
            "} catch [System.OperationCanceledException] { "
            "exit 1223 "
            "} catch { "
            "exit 1 "
            "}"
        )
        code, output = _run_command(
            ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-NonInteractive",
             "-Command", launcher],
            timeout=120,
        )
        if code == 0:
            return True
        if code == _UAC_CANCELLED_EXIT_CODE:
            raise PermissionError("UAC elevation cancelled by user")
        logger.error("Elevated Set-DnsClientServerAddress failed on %s (code=%s): %s",
                     iface, code, output.strip())
        return False

    def _reset_interface_dns_elevated(self, iface: str) -> bool:
        """Сбрасывает DNS через UAC-элевацию (скрытое окно)."""
        inner = (
            f"Set-DnsClientServerAddress -InterfaceAlias '{iface}' -ResetServerAddresses"
        )
        encoded = base64.b64encode(inner.encode("utf-16-le")).decode("ascii")
        launcher = (
            "$ErrorActionPreference = 'Stop'; "
            "try { "
            "$p = Start-Process powershell -Verb runAs -WindowStyle Hidden "
            f"-ArgumentList '-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {encoded}' "
            "-Wait -PassThru -ErrorAction Stop; "
            "if ($null -eq $p) { exit 1 }; "
            "exit $p.ExitCode "
            "} catch [System.OperationCanceledException] { "
            "exit 1223 "
            "} catch { "
            "exit 1 "
            "}"
        )
        code, output = _run_command(
            ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-NonInteractive",
             "-Command", launcher],
            timeout=120,
        )
        if code == 0:
            return True
        if code == _UAC_CANCELLED_EXIT_CODE:
            raise PermissionError("UAC elevation cancelled by user")
        logger.error("Elevated DNS reset failed on %s (code=%s): %s",
                     iface, code, output.strip())
        return False

    def _set_interface_dns_netsh(self, iface: str, ipv4: list) -> bool:
        ok = True
        if ipv4:
            code, output = _run_command(
                [
                    "netsh", "interface", "ip", "set", "dns",
                    f"name={iface}", "source=static",
                    f"addr={ipv4[0]}", "register=primary", "validate=no",
                ]
            )
            ok = code == 0 and ok
            for extra in ipv4[1:]:
                code, output = _run_command(
                    [
                        "netsh", "interface", "ip", "add", "dns",
                        f"name={iface}", f"addr={extra}", "index=2", "validate=no",
                    ]
                )
                ok = code == 0 and ok
        else:
            ok = self._reset_interface_dns(iface) and ok
        return ok

    def _set_interface_dns_macos(self, service: str, servers: list) -> bool:
        code, output = _run_command(
            ["networksetup", "-setdnsservers", service, *servers]
        )
        if code != 0:
            logger.error("Failed to set DNS on %s: %s", service, output.strip())
            return False
        return True

    def _set_interface_dns_linux(self, iface: str, servers: list) -> bool:
        code, output = _run_command(["resolvectl", "dns", iface, *servers])
        if code != 0:
            logger.error("Failed to set DNS on %s: %s", iface, output.strip())
            return False
        return True

    def _reset_interface_dns(self, iface: str) -> bool:
        """Сбрасывает DNS на автоматический (DHCP)."""
        if IS_WINDOWS:
            code, output = _run_command(
                [
                    "netsh", "interface", "ip", "set", "dns",
                    f"name={iface}", "source=dhcp", "validate=no",
                ]
            )
            if code == 0:
                return True
            logger.warning("Direct netsh reset failed on %s: %s", iface, output.strip())
            if not is_windows_admin():
                return self._reset_interface_dns_elevated(iface)
            logger.error("Failed to reset DNS on %s even with admin rights", iface)
            return False
        if IS_MACOS:
            code, output = _run_command(["networksetup", "-setdnsservers", iface, "Empty"])
            if code != 0:
                logger.error("Failed to reset DNS on %s: %s", iface, output.strip())
                return False
            return True
        code, output = _run_command(["resolvectl", "revert", iface])
        if code != 0:
            logger.error("Failed to reset DNS on %s: %s", iface, output.strip())
            return False
        return True

    # ------------------------------------------------------------------
    # Сброс DNS-кэша
    # ------------------------------------------------------------------

    def _flush_dns_cache(self):
        try:
            if IS_WINDOWS:
                _run_command(["ipconfig", "/flushdns"])
            elif IS_MACOS:
                _run_command(["dscacheutil", "-flushcache"])
                _run_command(["killall", "-HUP", "mDNSResponder"])
            else:
                _run_command(["resolvectl", "flush-caches"])
        except Exception:
            logger.exception("Failed to flush DNS cache")
