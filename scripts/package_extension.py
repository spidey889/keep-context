"""Build a dependency-free MV3 archive tied to one trusted hosted origin."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from keep_context.cli import public_url

FILES = (
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
)


def package(server: str, output: Path) -> None:
    base = public_url(server)
    source = Path(__file__).resolve().parents[1] / "extension"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["host_permissions"] = [base + "/*"]
    manifest["content_scripts"][0]["matches"] = [base + "/connect*"]
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: do not silently overwrite an artifact being tested/distributed.
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            if name == "manifest.json":
                content = json.dumps(manifest, indent=2) + "\n"
            elif name == "config.js":
                content = "export const SERVER = " + json.dumps(base) + ";\n"
            else:
                content = (source / name).read_bytes()
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="Stable hosted HTTPS origin, without /mcp.")
    parser.add_argument("--out", type=Path, default=Path("dist/keep-context-extension.zip"))
    args = parser.parse_args()
    package(args.server, args.out)
    print(f"Extension archive: {args.out}")
