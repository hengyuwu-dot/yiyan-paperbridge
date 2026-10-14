import asyncio
import errno
import json
import signal
import threading
from pathlib import Path
from types import SimpleNamespace

import psutil
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

import paperbridge.app as app_module
import paperbridge.desktop_server as desktop


def test_listener_retries_occupied_ports_and_holds_selected_socket(monkeypatch):
    sockets = []

    class FakeSocket:
        def __init__(self, *args):
            self.closed = False
            self.listening = False
            sockets.append(self)
        def setsockopt(self, *args): pass
        def bind(self, address):
            self.address = address
            if address[1] == 8765:
                raise OSError(errno.EADDRINUSE, "occupied")
        def listen(self, size): self.listening = True
        def set_inheritable(self, value): self.inheritable = value
        def close(self): self.closed = True

    monkeypatch.setattr(desktop.socket, "socket", FakeSocket)
    selected = desktop.bind_listener()
    assert sockets[0].closed and selected is sockets[1]
    assert selected.address == ("127.0.0.1", 8766)
    assert selected.listening and not selected.closed and not selected.inheritable


@pytest.mark.parametrize("error", [errno.EACCES, errno.EADDRINUSE])
def test_listener_errors_close_sockets_without_killing_other_service(monkeypatch, error):
    closed = []
    class FailedSocket:
        def setsockopt(self, *args): pass
        def bind(self, address): raise OSError(error, "cannot bind")
        def close(self): closed.append(True)
    monkeypatch.setattr(desktop.socket, "socket", lambda *args: FailedSocket())
    with pytest.raises(OSError) as caught:
        desktop.bind_listener([8765, 8766])
    assert caught.value.errno == error
    assert len(closed) == (2 if error == errno.EADDRINUSE else 1)


def test_state_is_atomic_private_and_cleanup_does_not_remove_newer_instance(tmp_path):
    path = tmp_path / "desktop" / "server.json"
    desktop.write_state(path, {"instance_id": "first", "port": 8765})
    assert json.loads(path.read_text()) == {"instance_id": "first", "port": 8765}
    assert path.stat().st_mode & 0o777 == 0o600
    desktop.write_state(path, {"instance_id": "second", "port": 8766})
    assert not desktop.remove_owned_state(path, "first")
    assert json.loads(path.read_text())["instance_id"] == "second"
    assert desktop.remove_owned_state(path, "second")
    assert not path.exists() and not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("content", ["not json", "[]", '{"port":8765}'])
def test_invalid_state_is_not_deleted(tmp_path, content):
    path = tmp_path / "server.json"
    path.write_text(content)
    assert not desktop.remove_owned_state(path, "ours")
    assert path.read_text() == content


@pytest.mark.parametrize("created,running,status,expected", [
    (10.0, True, psutil.STATUS_RUNNING, True),
    (11.0, True, psutil.STATUS_RUNNING, False),
    (10.0, False, psutil.STATUS_RUNNING, False),
    (10.0, True, psutil.STATUS_ZOMBIE, False),
])
def test_parent_identity_checks_pid_reuse_and_zombies(monkeypatch, created, running, status, expected):
    parent = SimpleNamespace(create_time=lambda: created, is_running=lambda: running, status=lambda: status)
    monkeypatch.setattr(desktop.psutil, "Process", lambda pid: parent)
    assert desktop.parent_is_alive((4321, 10.0)) is expected


def test_parent_monitor_exits_once_and_can_be_stopped(monkeypatch):
    monkeypatch.setattr(desktop, "parent_is_alive", lambda identity: False)
    exits = []
    desktop.watch_parent((4321, 10.0), threading.Event(), lambda: exits.append(True), interval=0)
    assert exits == [True]
    finished = threading.Event(); finished.set()
    desktop.watch_parent((4321, 10.0), finished, lambda: pytest.fail("normal shutdown"), interval=0)


def test_missing_parent_is_dead(monkeypatch):
    def missing(pid): raise psutil.NoSuchProcess(pid)
    monkeypatch.setattr(desktop.psutil, "Process", missing)
    assert not desktop.parent_is_alive((4321, 10.0))
    with pytest.raises(ValueError): desktop.parent_identity(1)


def test_cleanup_targets_only_this_process_descendants_and_kills_stubborn_child(monkeypatch):
    calls = []
    child = SimpleNamespace(terminate=lambda: calls.append("term"), kill=lambda: calls.append("kill"))
    owner = SimpleNamespace(children=lambda recursive: [child])
    monkeypatch.setattr(desktop.os, "getpid", lambda: 123)
    monkeypatch.setattr(desktop.psutil, "Process", lambda pid: owner if pid == 123 else pytest.fail("foreign process"))
    monkeypatch.setattr(desktop.psutil, "wait_procs", lambda processes, timeout: ([], processes))
    desktop.terminate_descendants(timeout=0)
    assert calls == ["term", "kill"]


def test_restricted_process_enumeration_does_not_break_state_cleanup(monkeypatch):
    def denied(recursive): raise PermissionError("process enumeration restricted")
    monkeypatch.setattr(desktop.psutil, "Process", lambda pid: SimpleNamespace(children=denied))
    desktop.terminate_descendants()


@pytest.mark.parametrize("job_status,active,install,busy", [
    ("ready", False, "idle", False), ("complete", False, "complete", False),
    ("queued", False, "idle", True), ("running", False, "idle", True),
    ("exporting", False, "idle", True), ("complete", True, "idle", True),
    ("ready", False, "running", True),
])
def test_status_has_identity_and_busy_without_resource_scan(monkeypatch, tmp_path, job_status, active, install, busy):
    monkeypatch.setattr(app_module, "ROOT", tmp_path)
    monkeypatch.setattr(app_module, "jobs", {"one": {"status": job_status}})
    monkeypatch.setattr(app_module, "active_operations", {"one"} if active else set())
    monkeypatch.setattr(app_module, "install_state", {"status": install})
    monkeypatch.setenv(desktop.INSTANCE_ENV, "desktop-instance")
    monkeypatch.setenv(desktop.PARENT_ENV, "4321")
    monkeypatch.setattr(app_module, "memory_usage", lambda: pytest.fail("expensive resource scan"))
    monkeypatch.setattr(app_module, "disk_usage", lambda *args: pytest.fail("expensive resource scan"))
    with TestClient(app_module.app) as client:
        response = client.get("/api/desktop/status")
    assert response.status_code == 200
    result = response.json()
    assert result == {"application": "PaperBridge", "workspace": str(tmp_path.resolve()),
                      "instance_id": "desktop-instance", "pid": desktop.os.getpid(),
                      "parent_pid": 4321, "busy": busy}


def test_plain_server_status_does_not_claim_desktop_ownership(monkeypatch):
    monkeypatch.delenv(desktop.INSTANCE_ENV, raising=False)
    monkeypatch.delenv(desktop.PARENT_ENV, raising=False)
    result = app_module.desktop_status()
    assert result["instance_id"] == "" and result["parent_pid"] is None


def test_sigterm_returns_to_cleanup_instead_of_reraising(monkeypatch):
    import uvicorn
    server = desktop.DesktopServer(uvicorn.Config("paperbridge.app:app"))
    original = signal.getsignal(signal.SIGTERM)
    with server.capture_signals():
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert server.should_exit
    assert signal.getsignal(signal.SIGTERM) == original


def test_web_upload_stays_busy_and_protects_cleanup_until_job_is_saved(monkeypatch):
    monkeypatch.setattr(app_module, "active_operations", set())
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "install_state", {"status": "idle"})
    phases = []

    def assert_protected(phase):
        phases.append(phase)
        assert app_module.desktop_status()["busy"]
        with pytest.raises(HTTPException) as error:
            app_module.manual_cleanup()
        assert error.value.status_code == 409

    class Request:
        headers = {"x-filename": "paper.pdf"}
        async def stream(self):
            assert_protected("receiving")
            yield b"%PDF-"

    def analyze_and_save(raw, name):
        assert raw == b"%PDF-" and name == "paper.pdf"
        assert_protected("analyzing-and-saving")
        return {"saved": True}

    monkeypatch.setattr(app_module, "add_document", analyze_and_save)
    assert asyncio.run(app_module.upload(Request())) == {"saved": True}
    assert phases == ["receiving", "analyzing-and-saving"]
    assert not app_module.desktop_status()["busy"] and not app_module.active_operations


@pytest.mark.parametrize("failure", ["stream", "filename", "analysis", "cancel"])
def test_web_upload_releases_only_its_activity_on_every_failure(monkeypatch, failure):
    monkeypatch.setattr(app_module, "active_operations", {"another-job"})

    class Request:
        headers = {"x-filename": "paper.txt" if failure == "filename" else "paper.pdf"}
        async def stream(self):
            assert len(app_module.active_operations) == 2
            if failure == "stream": raise RuntimeError("connection interrupted")
            if failure == "cancel": raise asyncio.CancelledError()
            yield b"%PDF-"

    def analyze_and_save(raw, name):
        raise RuntimeError("invalid PDF")

    monkeypatch.setattr(app_module, "add_document", analyze_and_save)
    expected = asyncio.CancelledError if failure == "cancel" else HTTPException if failure == "filename" else RuntimeError
    with pytest.raises(expected):
        asyncio.run(app_module.upload(Request()))
    assert app_module.active_operations == {"another-job"}


@pytest.mark.parametrize("worker_fails", [False, True])
def test_cancelled_upload_keeps_analysis_protected_and_retrieves_late_failure(monkeypatch, worker_fails):
    monkeypatch.setattr(app_module, "active_operations", set())
    monkeypatch.setattr(app_module, "upload_tasks", set())
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "install_state", {"status": "idle"})
    started, release = threading.Event(), threading.Event()

    class Request:
        headers = {"x-filename": "paper.pdf"}
        async def stream(self): yield b"%PDF-"

    def analyze_and_save(raw, name):
        started.set()
        assert release.wait(3), "test worker was not released"
        if worker_fails: raise RuntimeError("late PDF failure")
        return {"saved": True}

    monkeypatch.setattr(app_module, "add_document", analyze_and_save)

    async def scenario():
        warnings = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: warnings.append(context))
        request = asyncio.create_task(app_module.upload(Request()))
        try:
            async with asyncio.timeout(2):
                while not started.is_set(): await asyncio.sleep(0.005)
            retained = list(app_module.upload_tasks)
            assert len(retained) == 1
            request.cancel()
            with pytest.raises(asyncio.CancelledError): await request
            assert not retained[0].done()
            assert app_module.desktop_status()["busy"]
            with pytest.raises(HTTPException) as error: app_module.manual_cleanup()
            assert error.value.status_code == 409
        finally:
            release.set()
        async with asyncio.timeout(2):
            while app_module.upload_tasks: await asyncio.sleep(0.005)
        assert not app_module.active_operations
        assert not app_module.desktop_status()["busy"]
        # asyncio records unretrieved exceptions here; the completion callback
        # must consume even a failure that occurs after the request went away.
        assert not retained[0]._log_traceback
        assert not warnings

    asyncio.run(scenario())
