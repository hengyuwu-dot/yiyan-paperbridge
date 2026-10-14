import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile


def load_publisher():
    path = Path(__file__).parents[1] / "scripts/publish_offline_ci.py"
    spec = importlib.util.spec_from_file_location("publisher", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_streamed_parts_restore_files_modes_and_symlinks(tmp_path):
    publisher = load_publisher()
    app = tmp_path / "译研.app"
    app.mkdir()
    binary = app / "程序"
    binary.write_bytes(bytes(range(256)) * 20)
    binary.chmod(0o755)
    (app / "链接").symlink_to("程序")
    received = []
    def receive(path):
        received.append(path.read_bytes())
    writer = publisher.PartWriter(tmp_path / "parts", "application.tar.gz", receive, part_size=193)
    with tarfile.open(fileobj=writer, mode="w|gz", dereference=False) as archive:
        archive.add(app, arcname=app.name)
    writer.finish_part()
    restored = b"".join(received)
    assert len(writer.parts) > 1
    assert writer.total == len(restored)
    assert writer.full_hash.hexdigest() == hashlib.sha256(restored).hexdigest()
    for data, record in zip(received, writer.parts):
        assert record["bytes"] == len(data)
        assert record["sha256"] == hashlib.sha256(data).hexdigest()
    with tarfile.open(fileobj=io.BytesIO(restored)) as archive:
        assert archive.extractfile("译研.app/程序").read() == binary.read_bytes()
        assert archive.getmember("译研.app/程序").mode == 0o755
        link = archive.getmember("译研.app/链接")
        assert link.issym() and link.linkname == "程序"
    assert not list((tmp_path / "parts").iterdir())


def test_publisher_refuses_to_run_on_a_workstation(monkeypatch):
    publisher = load_publisher()
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="authorized repository"):
        publisher.require_runner()
