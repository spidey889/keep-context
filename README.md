<p><img src="site/icon.svg" width="48" height="48" alt=""></p>

# Keep Context

**Your Google Keep notes. One conversation.**

[Website](https://spidey889.github.io/keep-context/) · [Get started](#quick-start) · [Authentication guide](docs/AUTHENTICATION.md) · [Verification](docs/VERIFICATION.md)

Search and read your Google Keep notes in ChatGPT. One account per server, five read-only tools, no database or paid AI API required.

Keep Context reads from your connected Google Keep account and refreshes an in-memory snapshot as needed. New notes become available on the next request after the one-minute refresh interval. It never writes a notes database.

Ask things like **“What did I write about my garden?”**, **“Search my notes for weekend trip”**, or **“What do I still need to do?”**

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.11 or newer. From a terminal:

```sh
git clone https://github.com/spidey889/keep-context.git
cd keep-context
uv sync --locked
uv run keep-context connect
uv run keep-context doctor
```

`connect` walks you through one manual Google sign-in and asks for a hidden token input. It verifies Keep access, saves setup progress in the OS vault, and asks you to choose a separate password for connecting ChatGPT. Invalid passwords retry in place. If interrupted during that step, rerun the same command to resume without another browser sign-in. **Never paste Google tokens into ChatGPT.** See [authentication instructions](docs/AUTHENTICATION.md).

To expose a temporary HTTPS endpoint, install [cloudflared](https://developers.cloudflare.com/tunnel/downloads/) (Windows: `winget install -e --id Cloudflare.cloudflared`), then run:

```sh
uv run keep-context serve --tunnel
```

Copy the printed `https://…/mcp` URL into ChatGPT's **Plugins → Add custom MCP server**. Select **OAuth** and **dynamic client registration (DCR)** when offered. Leave static client credentials empty. Approve access using the separate connection password from setup. Install the plugin, select it with `@` in a new chat, and ask about your notes. Account/workspace policies may control whether custom plugins are available. [Current OpenAI instructions](https://developers.openai.com/api/docs/guides/custom-mcp-server).

Keep the terminal running. `Ctrl+C` stops the server and its tunnel. The temporary URL changes on each restart, so recreate the ChatGPT connection then. For daily use, point a stable HTTPS proxy/tunnel at loopback port 8000 and run:

```sh
uv run keep-context serve --public-url https://keep.example.com
```

With a stable URL, encrypted OAuth state preserves connections across restarts. See [ChatGPT and deployment details](docs/CHATGPT.md).

## Try it without a Google account

```sh
uv run keep-context doctor --demo
uv run keep-context serve --demo --tunnel
```

The demo uses two sample notes and the deliberately public connection password `demo-only-no-google-account`. It never loads Google credentials. Omit `--demo` for your account.

For local MCP clients such as Codex or Claude Desktop:

```sh
uv run keep-context serve --transport stdio
```

See [stdio configuration](docs/CHATGPT.md#local-stdio-clients). ChatGPT's web connection uses HTTP rather than stdio.

## Tools

| Tool | What it returns |
| --- | --- |
| `search` | Ranked matches across titles, bodies and checklist items, with excerpts, labels, timestamps and source URLs. |
| `fetch` | Full note text, labels, timestamps, and every checklist item with its checked state and parent ID. |
| `list_recent_notes` | Recently modified notes, newest first. |
| `list_labels` | All configured label names and note counts, including unused labels. |
| `find_tasks` | Unchecked checklist/Markdown items plus likely tasks detected from English TODO wording. |

Lists support `limit` and `offset`; follow `next_offset` until it is null. Search includes archived notes by default; recent notes and tasks exclude them unless requested. Trashed notes are always excluded. Labels match exact names without case sensitivity. Search uses all supplied keywords, with title matches ranked first. `fetch` does not truncate note text. Data refreshes on the next call after the 60-second cache expires; `doctor` makes a fresh connection.

## Why authentication has a manual step

Google's [official Keep API](https://developers.google.com/workspace/keep/api/guides) is intended for enterprise/domain-wide access, not a consumer OAuth connect flow. This project uses the maintained [gkeepapi](https://github.com/kiwiz/gkeepapi) and [gpsoauth](https://github.com/simon-weber/gpsoauth) libraries for consumer accounts. Their authentication requires a Google master token; it cannot safely be replaced with an ordinary OAuth button. ChatGPT connects to this server using separate, scoped MCP OAuth tokens. [Research and alternatives](docs/RESEARCH.md).

## Privacy and limits

- Google master tokens have broad account access. They remain in your OS credential vault, or explicit deployment secrets; the server never returns them through MCP.
- No note cache is written to disk. OAuth clients/tokens are stored encrypted in ignored `.keep-context/oauth.enc`, with encryption derived from the Google master token. HTTP access logs and upstream debug logging are disabled.
- No tools can write notes. A network guard rejects node/label mutation payloads even if future code accidentally edits a gkeepapi object.
- Notes read by ChatGPT are shared with ChatGPT. The server is for one trusted owner, not shared multi-user hosting.
- Access is unofficial and can break if Google changes its private API or blocks authentication. Checklist extraction is exact; English prose task detection is heuristic. Search is keyword-based, not semantic. Images, drawings, audio and reminders are not transcribed or fetched.

## Develop and verify

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Tests exercise the real gkeepapi parser with mocked Google responses, OAuth/PKCE, secrets redaction, and real stdio and TCP HTTP server processes using the official MCP client. No Google account or browser automation is required. [Verification report](docs/VERIFICATION.md), [current behavior](LOGIC.md), [change history](CHANGELOG.md).

Optional live HTTPS smoke (demo data only, requires cloudflared): `uv run python scripts/smoke_https.py`.

## Website

The minimal project site lives in `site/`. It uses plain HTML/CSS and a local SVG, with no JavaScript, tracking or external font requests. GitHub Actions publishes only this folder to [GitHub Pages](https://spidey889.github.io/keep-context/), on changes to the site or its publishing workflow. The site explains setup; each user's authenticated MCP server runs separately.

To preview locally, run `python -m http.server 8080 --directory site` and open `http://localhost:8080`. Changes to server code do not redeploy the site. The live website is independent of your temporary MCP tunnel.

MIT licensed. Dependencies retain their respective licenses.
