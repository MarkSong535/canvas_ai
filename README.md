# Canvas Student Agent

An OpenAI-powered assistant for Canvas LMS designed for student accounts.

## Features

- 🎓 **Student Scope**: Tailored to the Canvas API permissions granted to students
- 🤖 **Conversational Interface**: Natural language chat powered by OpenAI GPT-4o
- 🛠️ **22+ API Tools**: Coverage for courses, assignments, files, discussions, and more
- 💬 **Interactive CLI**: Rich-powered console for real-time conversations
- 🔐 **Secure Configuration**: Environment variables keep credentials outside the codebase

## Canvas API Tools

### 📚 Course Management
- `canvas_list_courses` – List enrolled courses
- `canvas_get_modules` – Fetch course modules
- `canvas_get_module_items` – Fetch module items

### 📝 Assignments and Submissions
- `canvas_get_assignments` – List assignments
- `canvas_submit_assignment` – Submit an assignment

### 📁 File Management
- `canvas_get_files` – List files
- `canvas_get_file_info` – Get file metadata
- `canvas_download_file` – Download a file
- `canvas_get_folders` – List folders
- `canvas_get_folder_files` – List files inside a folder
- `canvas_search_files` – Search files by keyword

### 💬 Discussions and Announcements
- `canvas_get_discussions` – List discussion topics
- `canvas_post_discussion` – Reply to a discussion
- `canvas_get_announcements` – List announcements

### 📖 Course Content
- `canvas_get_pages` – List course pages
- `canvas_get_page_content` – Fetch page content

### 📊 Grades and Schedule
- `canvas_get_grades` – Retrieve grades
- `canvas_get_calendar_events` – List calendar events
- `canvas_get_todo_items` – Retrieve to-do items
- `canvas_get_upcoming_events` – List upcoming events

### 📝 Quizzes and Groups
- `canvas_get_quizzes` – List quizzes
- `canvas_get_groups` – List groups

## Quick Start

### 1. Configure Environment Variables

Create a `.env` file in the project root and configure both OpenAI and Canvas settings:

```env
# OpenAI public API
OPENAI_API_KEY=your-openai-api-key
# OPENAI_API_BASE=https://api.openai.com/v1        # Optional custom base URL
# OPENAI_ORGANIZATION=org-id                        # Optional
# OPENAI_PROJECT=project-id                         # Optional

# Canvas LMS
CANVAS_URL=https://your-school.instructure.com
CANVAS_ACCESS_TOKEN=your-canvas-token-here
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the Interactive Console

```bash
python canvas_chat.py
```

## Generate a Canvas Access Token

1. Sign in to your Canvas account
2. Open the **Account** menu on the left navigation
3. Choose **Settings**
4. Scroll to **Approved Integrations**
5. Click **+ New Access Token**
6. Provide a purpose and expiration (optional)
7. Click **Generate Token**
8. **Copy the token immediately**; Canvas will not show it again

## Usage Examples

### Option 1: Interactive Console

```bash
python canvas_chat.py
```

Sample dialog:
```
User: What courses am I enrolled in?
Assistant: [Lists courses]

User: Show me the assignments for Data Structures.
Assistant: [Shows due dates and statuses]
```

File workflow:
```
User: Find all PDF files.
Assistant: [Returns matching files]

User: Download file 12345.
Assistant: [Downloads and provides the file]
```

Assignment workflow:
```
User: What is on my to-do list?
Assistant: [Returns to-do items]

User: Submit assignment 1 with the following text...
Assistant: [Submits the assignment]
```

### Option 2: Example Scripts

#### Full Agent Walkthrough

```bash
# Guided download test (recommended)
python examples/test_file_download.py

# Download a specific file quickly
python examples/test_file_download.py <file_id>
```

#### Direct Tool Tests

```bash
# Interactive file-operations test
python examples/direct_file_download_test.py

# Quickly download a specific file
python examples/direct_file_download_test.py <file_id>
```

**Suggested testing flow:**
1. List available courses
2. Select a course and view its files
3. Inspect file metadata
4. Download files (text, PDF, images, etc.)
5. Search files by keyword

## Architecture

- **Framework**: Custom agent framework
- **AI Models**: OpenAI GPT-4o and compatible models
- **Async Runtime**: aiohttp + asyncio
- **CLI**: Rich for terminal rendering
- **Configuration**: python-dotenv

## Project Layout

```
canvas_ai/
├── src/
│   ├── agent/           # Core agent logic
│   ├── tools/           # Canvas API tools
│   ├── models/          # Model manager
│   ├── config/          # Configuration helpers
│   └── utils/           # Utility functions
├── configs/
│   └── canvas_agent_config.py  # Agent configuration
├── canvas_chat.py       # Interactive console entry point
├── requirements.txt     # Dependencies
└── .env                 # Environment variables (user-provided)
```

## Notes

1. **Permission scope**: All tools operate with student-level permissions
2. **Token security**: Do not commit `.env` or access tokens
3. **API limits**: Canvas enforces rate limits—add delays when batching requests
4. **File access**: Some files may require browser access if Canvas restricts downloads

## FAQ

### Q: How do I find my Canvas URL?
A: Use the domain you see in your browser when visiting Canvas, e.g., `https://canvas.university.edu`.

### Q: What if my access token expires?
A: Generate a new token in Canvas Settings and update your `.env` file.

### Q: Why can’t I download certain files?
A: Instructors can restrict downloads; use the Canvas web interface if you encounter a permission error.

## License

This project is provided for educational use only.

## Contact

- GitHub: [@Deyu-Zhang](https://github.com/Deyu-Zhang)
- GitHub: [@MarkSong535](https://github.com/marksong535)
- Email: marksong535@gmail.com

