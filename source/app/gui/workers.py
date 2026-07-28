import json
from PySide6.QtCore import QObject, Signal, QRunnable
from app.core.logger import logger
from app.core.hosts_manager import HostsManager
from app.core.http_client import HttpClient
from app.core.constants import APP_VERSION, GITHUB_RELEASES_API_URL, GITHUB_RELEASES_PAGE_URL
from app.gui.localization import tr

class WorkerSignals(QObject):
    finished = Signal(str, bool, str)
    status_ready = Signal(object)
    update_ready = Signal(str, str, str)
    no_update = Signal(str, str)
    message = Signal(str, bool, bool)

    def __init__(self, parent=None):
        super().__init__(None)

class HostsWorker(QRunnable):
    def __init__(self, action: str, manager: HostsManager, provider: str = "dns.malw.link", parent=None):
        super().__init__()
        self.action = action
        self.manager = manager
        self.provider = provider
        self.signals = WorkerSignals()
        self.save_content: str = ""

    def run(self):
        try:
            if self.action in ("install", "update"):
                result = self.manager.update(self.provider)
            elif self.action == "uninstall":
                result = self.manager.restore()
            elif self.action == "save":
                result = self.manager.apply(self.save_content)
            else:
                result = False
            self.signals.finished.emit(self.action, result, "")
        except Exception as e:
            logger.exception("Hosts operation failed")
            self.signals.finished.emit(self.action, False, str(e))

class VersionWorker(QRunnable):
    def __init__(self, manager: HostsManager, provider: str = "dns.malw.link", parent=None):
        super().__init__()
        self.manager = manager
        self.provider = provider
        self.signals = WorkerSignals()

    def run(self):
        status = self.manager.check_status(self.provider)
        self.signals.status_ready.emit(status)

class AppUpdateWorker(QRunnable):
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

            def parse(v):
                return tuple(int(x) for x in v.strip("vV").split(".") if x.isdigit())

            if parse(remote_ver) > parse(local_ver):
                self.signals.update_ready.emit(local_ver, remote_ver, download_url)
            else:
                self.signals.no_update.emit(local_ver, remote_ver)
        except Exception as e:
            err = f"{tr('updates_check_failed')}\n{e}"
            self.signals.message.emit(err, False, True)
