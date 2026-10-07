import base64
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from keep_context.hosted import EXTENSION_ID


def test_archive_has_exact_origin_and_no_development_material(tmp_path):
    archive = tmp_path / "extension.zip"
    subprocess.run(
        [
            sys.executable,
            "scripts/package_extension.py",
            "--server",
            "https://keep.example.test",
            "--out",
            str(archive),
        ],
        check=True,
        capture_output=True,
    )
    with ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {
            "manifest.json",
            "config.js",
            "bridge.js",
            "worker.js",
            "consent.js",
            "popup.html",
            "popup.css",
            "popup.js",
            "icons/16.png",
            "icons/32.png",
            "icons/48.png",
            "icons/128.png",
        }
        manifest = json.loads(zipped.read("manifest.json"))
        assert manifest["host_permissions"] == ["https://keep.example.test/*"]
        assert manifest["optional_host_permissions"] == ["https://accounts.google.com/*"]
        assert "cookies" not in manifest["permissions"]
        # The icon opens a persistent setup tab; a dismissible popup would
        # reintroduce the sign-in handoff we are removing.
        assert "default_popup" not in manifest["action"]
        assert manifest["content_scripts"] == [
            {
                "matches": ["https://keep.example.test/connect*"],
                "js": ["consent.js"],
                "run_at": "document_idle",
                "all_frames": False,
            }
        ]
        assert "externally_connectable" not in manifest
        for size, name in manifest["icons"].items():
            png = zipped.read(name)
            assert png[:8] == b"\x89PNG\r\n\x1a\n"
            assert png[12:16] == b"IHDR"
            assert struct.unpack(">II", png[16:24]) == (int(size), int(size))
        assert all(
            name in manifest["icons"].values()
            for name in manifest["action"]["default_icon"].values()
        )
        assert "127.0.0.1" not in zipped.read("config.js").decode()
        hashed = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
        assert "".join(chr(97 + int(x, 16)) for x in hashed) == EXTENSION_ID
    # A failed rebuild cannot replace a previously approved artifact.
    first = archive.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "scripts/package_extension.py",
            "--server",
            "https://other.example.test",
            "--out",
            str(archive),
        ],
        capture_output=True,
    )
    assert result.returncode != 0 and archive.read_bytes() == first


def test_static_extension_security_boundaries():
    worker = Path("extension/worker.js").read_text()
    bridge = Path("extension/bridge.js").read_text()
    assert 'sender.url === chrome.runtime.getURL("popup.html")' in worker
    assert "sender.frameId === 0" in worker
    assert "connectionTicket(sender.url, bridge.server)" in worker
    assert "TRUSTED_CONTEXTS" in worker
    assert "console." not in bridge + worker
    assert "innerHTML" not in Path("extension/popup.js").read_text()
