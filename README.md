# Canvas Student Agent

An OpenAI-powered Canvas LMS companion tailored for student accounts. The project ships with a conversational CLI, a WebSocket service for machine-to-machine integrations, and a bulk file downloader that can populate OpenAI Vector Stores.

---

## Key Capabilities

- Student-safe Canvas API coverage with 20+ tools for courses, assignments, files, discussions, grades, and calendar data.
- Rich-powered command line chat experience (`canvas_chat.py`).
- Bulk file synchronization (`file_index_downloader.py`) with optional OpenAI Vector Store uploads.
- WebSocket bridge (`ws_server.py`) that exposes agent chat and download workflows with password + TOTP authentication.
- Example clients (`ws_test.py`, scripts in `examples/`) demonstrating common workflows.

---

## Repository Layout

```
canvas_ai/
├── canvas_chat.py            # Interactive console entry point
├── file_index_downloader.py  # Bulk download + optional vector store upload
├── ws_server.py              # Authenticated WebSocket bridge
├── ws_test.py                # Example sync WebSocket client
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
- An OpenAI API key (GPT-4o or compatible model)
- Optional: Assistants v2 Vector Store access if you plan to upload files

---

## Environment Configuration

Create a `.env` file (see `env_example.txt` for a template):

```env
# LLM provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key

# Canvas API
CANVAS_URL=https://your-school.instructure.com
CANVAS_ACCESS_TOKEN=your-canvas-token

# WebSocket server
CANVAS_WS_SECRET=choose-a-strong-password
CANVAS_WS_TOTP_SECRET=base32-totp-secret
CANVAS_WS_HOST=0.0.0.0              # Optional override
CANVAS_WS_PORT=8765                 # Optional override

# Test client overrides (optional)
CANVAS_WS_URI=ws://localhost:8765
CANVAS_WS_TEST_COURSE_IDS=43210,48765
CANVAS_WS_TEST_COURSE_INDICES=1,3
CANVAS_WS_TEST_SKIP=false
```

> **Generating a Canvas access token**
> 1. Log in to Canvas → Account → Settings → Approved Integrations
> 2. Click **+ New Access Token**
> 3. Add a description and (optionally) an expiration
> 4. Generate and copy the token immediately

For TOTP secrets you can use any authenticator app or `pyotp.random_base32()`.

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

Commands available inside the CLI: `help`, `status`, `examples`, `clear`, `exit`.

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

Authentication flow:

1. Client opens a WebSocket connection to `ws://host:port`
2. Client sends `{ "type": "auth", "password": "...", "totp": "123456" }`
3. Server verifies the secret and replies `{ "status": "authenticated" }`
4. Subsequent messages can be:
	 - Chat: `{ "type": "chat", "query": "List my courses" }`
	 - Download: staged workflow
		 - Request course list -> `{ "type": "download" }`
		 - Server responds with numbered courses
		 - Client selects -> `{ "type": "download", "course_indices": [1,3], "auto_confirm": true }`
		 - Server streams the final status and statistics

### Example client

```bash
# Chat mode
python ws_test.py

# Download mode (make sure CANVAS_WS_TEST_* envs are set)
python ws_test.py download
```

The test client authenticates once per session and prints responses to stdout. In download mode it displays the course roster before sending the follow-up selection.

---

## Example Scripts

- `examples/test_file_download.py` – Guided walkthrough of downloading Canvas files through the agent
- `examples/direct_file_download_test.py` – Low-level Canvas file operations
- `examples/test_vector_store_tools.py` – Demonstrates vector-store search and listing

---

## Troubleshooting

- **Authentication failed** → Verify `CANVAS_WS_SECRET` and `CANVAS_WS_TOTP_SECRET`; update your authenticator if the TOTP window drifts.
- **Missing dependencies** → Re-run `pip install -r requirements.txt`.
- **Canvas 401 errors** → Regenerate your Canvas access token or confirm the URL points to the correct subdomain.
- **Vector store upload errors** → Ensure `openai>=1.20.0` and that your account has Assistants v2 access.

---

## License and Contact

This project is provided for educational use. Reach out via GitHub Issues for feedback or questions.

- GitHub: [@MarkSong535](https://github.com/MarkSong535)
- GitHub: [@Deyu-Zhang](https://github.com/Deyu-Zhang)
- Email: marksong535@gmail.com

