import json

from PySide6.QtCore import QObject, Signal, QRunnable

from app.core.logger import logger
from app.core.constants import (
    APP_VERSION,
    GITHUB_RELEASES_API_URL,
    GITHUB_RELEASES_PAGE_URL,
)
from app.core.http_client import HttpClient
from app.gui.localization import tr


class WorkerSignals(QObject):
    finished = Signal(str, bool, str, bool)   # action, ok, error, backup_failed
    status_ready = Signal(object)
    update_ready = Signal(str, str, str)
    no_update = Signal(str, str)
    message = Signal(str, bool, bool)

    def __init__(self, parent=None):
        super().__init__(None)


class HostsWorker(QRunnable):
    """Выполняет операцию менеджера (install/update/uninstall/save) в фоне."""

    def __init__(self, action: str, manager, provider: str = "dns.malw.link", parent=None):
        super().__init__()
        self.action = action
        self.manager = manager
        self.provider = provider
        self.signals = WorkerSignals()
        self.save_content: str = ""
        # Способ восстановления hosts при uninstall: "" | "backup" | "clean"
        # (актуально только для HostsManager; DnsManager его игнорирует)
        self.restore_mode: str = ""
        # Сохранить текущий hosts в бэкап перед записью save_content
        self.pre_backup: bool = False

    def run(self):
        try:
            if self.action in ("install", "update"):
                result = self.manager.update(self.provider)
            elif self.action == "uninstall":
                if self.restore_mode in ("backup", "clean"):
                    result = self.manager.restore(self.restore_mode)
                else:
                    result = self.manager.restore()
            elif self.action == "save":
                if self.pre_backup:
                    try:
                        self.manager.backup("manual")
                    except Exception as e:
                        logger.warning("Pre-save backup failed: %s", e)
                result = self.manager.apply(self.save_content)
            else:
                result = False
            self.signals.finished.emit(self.action, result, "", self.manager.backup_failed)
        except Exception as e:
            logger.exception("Unlock operation failed")
            self.signals.finished.emit(self.action, False, str(e), self.manager.backup_failed)


class VersionWorker(QRunnable):
    """Асинхронная проверка статуса hosts/DNS (не блокирует UI)."""

    def __init__(self, manager, provider: str = "dns.malw.link", parent=None):
        super().__init__()
        self.manager = manager
        self.provider = provider
        self.signals = WorkerSignals()

    def run(self):
        status = self.manager.check_status(self.provider)
        self.signals.status_ready.emit(status)


def _parse_version(version: str) -> tuple:
    return tuple(int(x) for x in version.strip("vV").split(".") if x.isdigit())


class AppUpdateWorker(QRunnable):
    """Проверка обновлений приложения через GitHub API."""

    def __init__(self, parent=None):
        super().__init__()
        self.signals = WorkerSignals()

    def run(self):
        try:
            local_ver = APP_VERSION
            remote_content = HttpClient.fetch(GITHUB_RELEASES_API_URL, bypass_cache=True)
            if not remote_content:
                raise RuntimeError(tr("update_info_unavailable"))
            remote_data = json.loads(remote_content)
            remote_ver = remote_data.get("tag_name", "").lstrip("vV")
            if not remote_ver:
                raise RuntimeError(tr("update_info_unavailable"))
            download_url = remote_data.get("html_url", GITHUB_RELEASES_PAGE_URL)

            if _parse_version(remote_ver) > _parse_version(local_ver):
                self.signals.update_ready.emit(local_ver, remote_ver, download_url)
            else:
                self.signals.no_update.emit(local_ver, remote_ver)
        except Exception as e:
            err = f"{tr('updates_check_failed')}\n{e}"
            self.signals.message.emit(err, False, True)
