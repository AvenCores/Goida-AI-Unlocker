import json
from typing import Callable
from PySide6.QtCore import QObject, Signal, QRunnable
from app.core.logger import logger
from app.core.hosts_manager import HostsManager
from app.core.http_client import HttpClient
from app.gui.localization import tr

class WorkerSignals(QObject):
    finished = Signal(str, bool, str)
    status_ready = Signal(object)
    update_ready = Signal(str, str, str)
    no_update = Signal(str, str)
    message = Signal(str, bool, bool)

class HostsWorker(QRunnable):
    def __init__(self, action: str, manager: HostsManager):
        super().__init__()
        self.action = action
        self.manager = manager
        self.signals = WorkerSignals()

    def run(self):
        try:
            if self.action in ("install", "update"):
                result = self.manager.update()
            else:
                result = self.manager.restore()
            self.signals.finished.emit(self.action, result, "")
        except Exception as e:
            logger.exception("Hosts operation failed")
            self.signals.finished.emit(self.action, False, str(e))

class VersionWorker(QRunnable):
    def __init__(self, manager: HostsManager):
        super().__init__()
        self.manager = manager
        self.signals = WorkerSignals()

    def run(self):
        status = self.manager.check_status()
        self.signals.status_ready.emit(status)

class AppUpdateWorker(QRunnable):
    def __init__(self, resource_path_func: Callable[[str], str]):
        super().__init__()
        self.resource_path = resource_path_func
        self.signals = WorkerSignals()

    def run(self):
        try:
            with open(self.resource_path("app_info.json"), "r", encoding="utf-8") as f:
                local = json.load(f)
            local_ver = local.get("version", "0.0.0")
            remote_url = local.get("update_info_url")
            if not remote_url:
                raise RuntimeError(tr("update_url_missing"))
            remote_content = HttpClient.fetch(remote_url)
            if not remote_content:
                raise RuntimeError(tr("update_info_unavailable"))
            remote_data = json.loads(remote_content)
            remote_ver = remote_data.get("version", "0.0.0")
            download_url = remote_data.get("download_url", "https://github.com/AvenCores/Goida-AI-Unlocker")

            def parse(v):
                return tuple(int(x) for x in v.strip("vV").split(".") if x.isdigit())

            if parse(remote_ver) > parse(local_ver):
                self.signals.update_ready.emit(local_ver, remote_ver, download_url)
            else:
                self.signals.no_update.emit(local_ver, remote_ver)
        except Exception as e:
            err = f"{tr('updates_check_failed')}\n{e}"
            self.signals.message.emit(err, False, True)
