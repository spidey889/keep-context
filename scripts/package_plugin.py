"""Build a private-test ChatGPT plugin ZIP for one hosted MCP origin.

This contains connection metadata only. Public directory submission still needs
verified publisher identity, store assets, terms, and real review evidence.
"""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from keep_context.cli import public_url

SCHEMA = "https://agent-plugins.org/schemas/1.0.0/"
WEBSITE = "https://spidey889.github.io/keep-context/"
REPOSITORY = "https://github.com/spidey889/keep-context"


def package(server: str, output: Path) -> None:
    base = public_url(server)
    version = json.loads(
        (Path(__file__).resolve().parents[1] / "extension/manifest.json").read_text()
    )["version"]
    files = {
        "plugin.json": {
            "$schema": SCHEMA + "plugin.schema.json",
            "name": "keep-context",
            "version": version,
            "description": "Search and read your connected Google Keep notes in ChatGPT.",
            "homepage": WEBSITE,
            "repository": REPOSITORY,
            "license": "MIT",
            "extensions": {
                "com.openai": {
                    "interface": {
                        "displayName": "Keep Context",
                        "shortDescription": "Your Keep notes in ChatGPT",
                        "longDescription": (
                            "Search titles, note text and checklists; read full notes; browse "
                            "recent notes and labels; find likely tasks. Connect Google Keep "
                            "with the companion extension, then approve ChatGPT. Read access "
                            "only. Consumer Keep access is unofficial. This is a private-test "
                            "preview, not a published directory listing."
                        ),
                        "category": "Productivity",
                        "capabilities": ["Search notes", "Read notes"],
                        "websiteURL": WEBSITE,
                        "supportURL": WEBSITE + "connect.html",
                        "privacyPolicyURL": WEBSITE + "privacy.html",
                    }
                }
            },
        },
        "mcp.json": {
            "$schema": SCHEMA + "mcp.schema.json",
            "mcpServers": {"keep": {"type": "streamable-http", "url": base + "/mcp"}},
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Never bundle headers, OAuth secrets, Google credentials or a local process.
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for name, content in files.items():
            entry = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, json.dumps(content, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True, help="Trusted hosted origin, without /mcp.")
    parser.add_argument("--out", type=Path, default=Path("dist/keep-context-plugin.zip"))
    args = parser.parse_args()
    package(args.server, args.out)
    print(f"Private-test plugin archive: {args.out}")
