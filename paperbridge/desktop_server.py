"""Own the local HTTP service started by the macOS desktop application.

Models and user documents stay in the existing workspace.  This launcher only
owns its own listener and descendants; it never kills a service occupying a port.
"""
import argparse
import errno
import json
import os
from pathlib import Path
import signal
import socket
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager

import psutil
import uvicorn

from .paths import ROOT
from .file_lock import lock_file
INSTANCE_ENV = "PAPERBRIDGE_DESKTOP_INSTANCE_ID"
PARENT_ENV = "PAPERBRIDGE_DESKTOP_PARENT_PID"


def bind_listener(ports=range(8765, 8776)):
    """Keep the bound socket until Uvicorn takes over, avoiding a port race."""
    last_error = None
    for port in ports:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
            listener.set_inheritable(False)
            return listener
        except OSError as exc:
            listener.close()
            if exc.errno != errno.EADDRINUSE:
                raise
            last_error = exc
    raise OSError(errno.EADDRINUSE, "本机端口 8765–8775 均已占用，请稍后重试") from last_error


@contextmanager
def state_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        lock_file(descriptor)
        yield
    finally:
        os.close(descriptor)


def write_state(path, state):
    path = Path(path)
    with state_lock(path):
        descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(state, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def remove_owned_state(path, instance_id):
    """The lock also protects against another launch replacing our state."""
    path = Path(path)
    with state_lock(path):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        if not isinstance(state, dict) or state.get("instance_id") != instance_id:
            return False
        path.unlink()
        return True


def parent_identity(pid):
    if pid <= 1:
        raise ValueError("桌面应用父进程无效")
    process = psutil.Process(pid)
    if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
        raise ValueError("桌面应用已经退出")
    return pid, process.create_time()


def parent_is_alive(identity):
    try:
        process = psutil.Process(identity[0])
        return (process.create_time() == identity[1] and process.is_running()
                and process.status() != psutil.STATUS_ZOMBIE)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


def watch_parent(identity, finished, on_exit, interval=0.5):
    while not finished.wait(interval):
        if not parent_is_alive(identity):
            on_exit()
            return


def terminate_descendants(timeout=2):
    """psutil Process objects guard against PID reuse before sending signals."""
    owner = psutil.Process(os.getpid())
    try:
        children = owner.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return
    for child in reversed(children):
        try:
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, remaining = psutil.wait_procs(children, timeout=timeout)
    for child in remaining:
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(remaining, timeout=timeout)


def stop_application_workers():
    module = sys.modules.get("paperbridge.app")
    if module is not None:
        # Prevent another queued translation from starting during cleanup.
        module.executor.shutdown(wait=False, cancel_futures=True)
    terminate_descendants()
    # Reap a helper created while the first snapshot was being collected.
    terminate_descendants(timeout=0.5)


class DesktopServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # Uvicorn normally re-raises SIGTERM after serving, which bypasses our
        # final cleanup. Restore handlers but let run() finish normally instead.
        handlers = {sig: signal.signal(sig, self.handle_exit)
                    for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            yield
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="译研桌面本地服务")
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    arguments = parser.parse_args(argv)
    listener = None
    finished = threading.Event()
    instance_id = uuid.uuid4().hex
    try:
        if arguments.parent_pid != os.getppid():
            raise ValueError("父进程必须是启动本服务的桌面应用")
        identity = parent_identity(arguments.parent_pid)
        listener = bind_listener()
        port = listener.getsockname()[1]
        os.environ[INSTANCE_ENV] = instance_id
        os.environ[PARENT_ENV] = str(arguments.parent_pid)
        state = {"pid": os.getpid(), "parent_pid": arguments.parent_pid, "port": port,
                 "workspace": str(ROOT.resolve()), "instance_id": instance_id}
        server = DesktopServer(uvicorn.Config("paperbridge.app:app", host="127.0.0.1", port=port,
                               access_log=False, timeout_graceful_shutdown=5))

        def parent_exited():
            server.should_exit = True
            stop_application_workers()

        write_state(arguments.state_file, state)
        watcher = threading.Thread(target=watch_parent, args=(identity, finished, parent_exited),
                                   name="paperbridge-desktop-parent", daemon=True)
        watcher.start()
        server.run(sockets=[listener])
        return 0
    except (OSError, ValueError, psutil.Error) as exc:
        print(f"译研启动失败：{exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        finished.set()
        stop_application_workers()
        if listener is not None:
            listener.close()
        try:
            remove_owned_state(arguments.state_file, instance_id)
        except OSError as exc:
            print(f"无法清除本次启动状态：{exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    result = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # Native model/ONNX finalizers and cancelled executor threads must not keep
    # an orphaned desktop service alive after all owned children were reclaimed.
    os._exit(result)
