# Canvas Student Agent

**Demo**: [https://markso.ng/demo/canvas](https://markso.ng/demo/canvas)

An OpenAI-powered ReAct Agent for Canvas LMS companion tailored for student accounts. The project ships with a conversational CLI, a secured WebSocket service for machine-to-machine integrations, and a bulk Canvas LMS file downloader that can populate OpenAI Vector Stores.

---

## Key Capabilities

- Student-safe Canvas API coverage with 20+ tools for courses, assignments, files, discussions, grades, and calendar data.
- Rich-powered command line chat experience (`canvas_chat.py`).
- Bulk file synchronization (`file_index_downloader.py`) with optional OpenAI Vector Store uploads.
- WebSocket bridge (`ws_server.py`) that exposes agent chat and download workflows to the web page (`frontend/index.html`), gated by Cloudflare Turnstile.
- React web client (`web/`), a Vite + TypeScript port of the web page with the same features.
- End-to-end tests (`tests/`) and example scripts (`examples/`).

---

## Repository Layout

```
canvas_ai/
├── canvas_chat.py            # Interactive console entry point
├── file_index_downloader.py  # Bulk download + optional vector store upload
├── ws_server.py              # Authenticated WebSocket bridge
├── frontend/index.html       # Web chat page (Turnstile + WebSocket)
├── web/                      # React client (Vite + TypeScript)
├── tests/                    # End-to-end tests (fake model, no network)
├── configs/
│   └── canvas_agent_config.py
├── src/
│   ├── agent/                # Agent builders and prompts
│   ├── tools/                # Canvas tool implementations
│   ├── models/               # Model manager + providers
│   ├── logger/               # Rich-based logging utilities
│   └── ...
├── examples/                 # Guided demos and tool exercises
├── requirements.txt
└── README.md
```

---

## Prerequisites

- Python 3.11+
- A Canvas LMS account with student-level API access
- An OpenAI API key (defaults to `gpt-6-luna`; see [Models](#models))
- Optional: Assistants v2 Vector Store access if you plan to upload files

---

## Environment Configuration

Create a `.env` file (see `env_example.txt` for a template):

```env
# LLM provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key

# Canvas API
CANVAS_URL=https://instituation.instructure.com/
CANVAS_ACCESS_TOKEN=your_canvas_access_token_here

# WebSocket Server Config (Cloudflare Turnstile)
TURNSTILE_SECRET=your_turnstile_secret_key_here
TURNSTILE_HOSTNAMES=markso.ng
TURNSTILE_ACTION=canvas_ws

# WSS Config
WSS_ENABLED=true
WSS_CERTFILE=your_certfile_here
WSS_KEYFILE=your_keyfile_here 

# Max duration of a session in minutes
SESSION_DURATION=10
```

> **Generating a Canvas access token**
> 1. Log in to Canvas → Account → Settings → Approved Integrations
> 2. Click **+ New Access Token**
> 3. Add a description and (optionally) an expiration
> 4. Generate and copy the token immediately

---

## Installation

```bash
pip install -r requirements.txt
```

Recommended extras (optional but useful during development):

```bash
pip install black ruff
```

---

## Running the CLI Chat

```bash
python canvas_chat.py
```

Sample interaction:

```
You: List every course I am enrolled in
Agent: Course 1 (ID 123), Course 2 (ID 456)

You: Show the upcoming assignments for Course 1
Agent: [Table of assignments with due dates and status]
```

Answers stream into the terminal as they are generated, with a status line showing which Canvas lookups the agent is making. The chat is multi-turn: follow-ups like "what about the second one?" see the earlier exchanges (the last `max_history_turns` turns, set in `configs/canvas_agent_config.py`).

Commands available inside the CLI: `help`, `new` (start a fresh conversation), `status`, `examples`, `clear`, `exit`.

---

## Models

Models are registered in `src/models/models.py`. Only models whose input **and** output price are at most $5 per 1M tokens are allowed; registration skips anything above `MAX_PRICE_PER_1M_TOKENS`. The current set is `gpt-6-luna` (default), `gpt-5.6-luna`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o-mini` and `o4-mini`. Pick one with `model_id` in `configs/canvas_agent_config.py`.

---

## Bulk File Downloader

Run locally:

```bash
python file_index_downloader.py           # Full download + optional vector upload
python file_index_downloader.py --upload-only  # Skip downloads, upload existing files
```

Features:

- Downloads per-course directory trees under `file_index/`
- Supports incremental runs (skips unchanged files)
- Optionally uploads supported formats to OpenAI Vector Stores (PDF, DOCX, PPTX, CSV, etc.)
- Produces a `download_report.json` summary and `vector_stores_mapping.json`

When driven via WebSocket automation the downloader skips interactive prompts and returns statistics in the response payload.

---

## WebSocket Service

Start the server (after configuring `.env`):

```bash
python ws_server.py
```

Connection flow:

1. The page opens a WebSocket from `https://markso.ng` (other origins are refused at the handshake)
2. Its first frame, within 15 seconds, is `{ "type": "verify", "token": "<Turnstile token>" }`; the server checks the token with Cloudflare (`TURNSTILE_*` settings)
3. Server replies `{ "status": "verified" }`. Only one connection is active at a time, and it closes after `SESSION_DURATION` minutes
4. Subsequent messages can be:
	 - Chat: `{ "type": "chat", "query": "List my courses" }`. The reply streams back as several frames:
		 - `{ "type": "tool", "name": "canvas_list_courses" }` while the agent calls a Canvas tool
		 - `{ "type": "delta", "text": "..." }` chunks of the answer as it is generated
		 - `{ "type": "retract" }` if the partial answer was rejected (clear it and keep listening)
		 - `{ "type": "answer", "answer": "...", "renders": { "<key>": "<svg>" } }` the complete final answer (or `{ "error": "..." }`). Answers are Markdown with LaTeX math (`\ce{}` for chemistry) and ` ```chemfig ` blocks for structures. The server compiles every snippet with real LaTeX + dvisvgm (`src/utils/latex_svg.py`, installed in the Docker image) and returns SVGs keyed `I:<tex>` (inline math), `D:<tex>` (display math) or `C:<code>` (chemfig, trimmed). Inline SVGs are sized in em and baseline-aligned; anything missing can be rendered client-side (the web UI falls back to KaTeX).
	 - The agent also has a `check_latex` tool that compiles a snippet with the same renderer and returns the LaTeX error, so it can fix complex formulas or structures before answering.
	 - New conversation: `{ "type": "reset" }` → `{ "status": "reset" }`. Each connection starts its own conversation; within it the agent remembers earlier exchanges.
	 - Download: staged workflow
		 - Request course list -> `{ "type": "download" }`
		 - Server responds with numbered courses
		 - Client selects -> `{ "type": "download", "course_indices": [1,3], "auto_confirm": true }`
		 - Server streams the final status and statistics

Turnstile tokens come from the browser widget, so the server can't be driven from a script. To exercise it without a browser, run the tests below; they call the same message handler directly.

---

## Web Client

`web/` is a React + TypeScript frontend, built with Vite. It connects with the backend with WebSocket protocol and renders Markdown, KaTeX and the server's LaTeX/chemfig SVGs.

```bash
cd web
npm install
npm run dev     # http://localhost:5173
npm run build   # type-checks, then writes static files to web/dist/
```

The WebSocket endpoint and Turnstile site key are read at build time from `web/.env.local` (see `web/.env.example`) and default to production. For UI work against a stand-in server, set `VITE_SKIP_TURNSTILE=1` (dev server only) to skip the challenge.

---

## Canvas Sandbox Mode

Set `CANVAS_SANDBOX=yes` in `.env` to run against a local copy of Canvas instead of the live site:

1. On start (or with `python -m src.canvas_sandbox sync`), if no complete sandbox exists yet, everything the tools could ask for is fetched with your access token. That covers courses in every enrollment state, assignments, modules, files and folders, pages, discussions, announcements across each course's history, quizzes, grades, the calendar, to-dos and groups. Every file is downloaded too, including files only linked from modules or page HTML.
2. A local Canvas look-alike then starts on `127.0.0.1` and `CANVAS_URL` is pointed at it, so the tools, the file downloader and the course picker are all answered locally. Errors Canvas returned are replayed as-is, and file search, calendar date ranges and multi-course announcements are filtered locally.
3. Writes never reach Canvas. The agent always has the submit-assignment and post-discussion tools, but the tools' request layer only lets a non-GET request through to the running local sandbox. There it's recorded in `writes.jsonl` and shows up in later reads. In live mode the request is blocked before anything is sent, and the agent tells the student to do it in Canvas.

4. Files are served by this platform, never by Canvas. Every Canvas file link in sandbox responses is rewritten to a signed, expiring link like `https://canvas.marksong.tech/files/<id>/<name>?expires=…&sig=…`. That covers file objects, module items, and links inside page, assignment and announcement HTML. Set `CANVAS_SANDBOX_PUBLIC_URL` to the public domain, and route its `/files/` path to `CANVAS_SANDBOX_FILES_PORT` (on `oci`, a Cloudflare Tunnel ingress rule). That port runs a files-only server, while the sandbox's API stays on loopback. Links last `CANVAS_SANDBOX_LINK_TTL_HOURS` (7 days by default) and are signed with `CANVAS_SANDBOX_LINK_SECRET`, which defaults to a random key stored in the sandbox folder.
5. Only the capture step uses the real `CANVAS_URL` and `CANVAS_ACCESS_TOKEN`. Once the sandbox starts, the process switches to the local server's URL and a simulated token that only the local server accepts; the real token gets a 401. Serving an existing sandbox needs no real credentials at all: on `oci` the production container runs with placeholders, and only the capture container (`python -m src.canvas_sandbox sync`) gets the real ones.

Everything lives in `CANVAS_SANDBOX_DIR` (default `workdir/canvas_sandbox`): `responses.json`, `files/`, `writes.jsonl`, and `requests.jsonl` (every request served, and whether it was a captured hit, filtered locally, a recorded write or not captured). `python -m src.canvas_sandbox status` summarizes it; set `CANVAS_SANDBOX_REFRESH=yes` or run `sync` again to re-fetch.

---

## Tests

```bash
pip install pytest
pytest tests
```

The end-to-end tests use a scripted fake OpenAI client, so they need no API key, Canvas account or network. They cover the model price cap, streaming, multi-turn memory, native tool-call history, the repeated-call guard, the WebSocket message handler (chat, `reset`), the terminal chat panel, and LaTeX extraction. Rendering tests also compile real LaTeX when `latex` and `dvisvgm` are installed, and are skipped otherwise. `python tests/test_end_to_end.py` runs them without pytest.

---

## Example Scripts

- `examples/test_file_download.py` – Guided walkthrough of downloading Canvas files through the agent
- `examples/direct_file_download_test.py` – Low-level Canvas file operations
- `examples/test_vector_store_tools.py` – Demonstrates vector-store search and listing

---

## Troubleshooting

- **Verification failed** → Check `TURNSTILE_SECRET` matches the page's site key, and that the page's hostname is in `TURNSTILE_HOSTNAMES`.
- **Missing dependencies** → Re-run `pip install -r requirements.txt`.
- **Canvas 401 errors** → Regenerate your Canvas access token or confirm the URL points to the correct subdomain.
- **Vector store upload errors** → Ensure `openai>=1.20.0` and that your account has Assistants v2 access.

---

## License and Contact

This project is provided for educational use. Reach out via GitHub Issues for feedback or questions.

