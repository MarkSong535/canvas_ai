# Vector Store Tooling Guide

## 📚 Overview

Canvas AI Agent ships with **four vector store tools** that help you organize and search course knowledge bases.

### 1️⃣ VectorStoreList — List Knowledge Bases
**Purpose**: Enumerate every available vector store (course knowledge base)

**Parameters**: none

**Returns**:
- Vector store ID
- Name
- File count
- Creation time

**Prompts you can use**:
```
"List all available knowledge bases."
"Which course libraries do I have?"
```

---

### 2️⃣ VectorStoreSearch — Semantic Search
**Purpose**: Run a semantic search against a specific knowledge base

**Parameters**:
- `vector_store_id` (required): target vector store ID
- `query` (required): natural language search query
- `max_results` (optional): maximum number of results (default 5)

**Returns**:
- Relevance score
- Source file
- Content snippet

**Prompts you can use**:
```
"Search vector store vs_xxx for Agent-Based Modeling content."
"What are the key topics in this course?"
"What are the requirements for the first assignment?"
```

---

### 3️⃣ VectorStoreListFiles — List Files ⭐ New
**Purpose**: Display every file stored inside a knowledge base

**Parameters**:
- `vector_store_id` (required): target vector store ID
- `read_content` (optional): include file previews (default False)
- `limit` (optional): maximum number of files (default 20)

**Returns**:
- File ID
- File name
- File status
- Creation time
- File size
- Content preview (when enabled)

**Prompts you can use**:
```
"List every file inside vector store vs_xxx."
"Show me the files stored in this knowledge base."
"Display the files and include previews."
```

---

### 4️⃣ VectorStoreGetFile — Read File ⭐ New
**Purpose**: Retrieve metadata and the full contents of a file by `file_id`

**Parameters**:
- `file_id` (required): OpenAI file identifier
- `max_length` (optional): maximum number of characters to return (default 5000)

**Returns**:
- Detailed file metadata (name, size, status, etc.)
- Full text content for text-based files
- File-type detection (PDF, Office documents, and more)

**Prompts you can use**:
```
"Read the contents of file-xxx."
"Show me the details for this file."
"Display the file, up to 10,000 characters."
```

---

## 🎯 Typical Workflows

### Workflow 1: Browse Course Materials
```
1. User: "List every knowledge base."
   → Agent calls VectorStoreList()

2. User: "List all files in the first knowledge base."
   → Agent calls VectorStoreListFiles(vector_store_id="vs_xxx")

3. User: "Read the first file."
   → Agent calls VectorStoreGetFile(file_id="file-xxx")
```

### Workflow 2: Search for Specific Content
```
1. User: "What does this course cover?"
   → Agent calls VectorStoreList() to locate the right knowledge base
   → Agent calls VectorStoreSearch(vector_store_id="vs_xxx", query="course topics")

2. User: "Show me the full contents of that file."
   → Agent calls VectorStoreGetFile(file_id="file-xxx")
```

### Workflow 3: Locate Assignment Material
```
1. User: "What are the requirements for Assignment 1?"
   → Agent calls VectorStoreSearch(query="assignment 1 requirements")

2. User: "List the files in that knowledge base."
   → Agent calls VectorStoreListFiles(vector_store_id="vs_xxx")

3. User: "Read the assignment instructions."
   → Agent calls VectorStoreGetFile(file_id="file-xxx")
```

---

## 💡 Tips

### 1. File Types
- ✅ **Text files**: .txt, .md, .py, .java, .cpp, .json, etc.
- ✅ **PDF documents**: recognized but not rendered inline (process separately)
- ✅ **Office documents**: .docx, .xlsx, .pptx (type detection only)

### 2. Content Length Controls
- `VectorStoreListFiles` previews the first 1,000 characters by default
- `VectorStoreGetFile` returns up to 5,000 characters by default
- Adjust `max_length` to expand or shrink the output

### 3. Batch Operations
- Use the `limit` argument on `VectorStoreListFiles` to control batch size
- Default limit is 20 files per call

### 4. Search Quality
- Use precise keywords or questions
- Reference specific topics or weeks
- Combine search results with file reads for deeper context

---

## 🔧 Command-Line Tests

### Test Script 1: Direct Tool Tests
```bash
python examples/test_vector_store_tools.py
```

**Highlights**:
- Exercise each tool individually
- Interactive menu
- Invoke tools directly or dispatch via the agent

### Test Script 2: Search Walkthrough
```bash
python test_vector_store_search.py
```

**Highlights**:
- List vector stores
- Run interactive searches
- Try fast search mode

---

## 📊 Tool Comparison

| Tool | Primary Use | Input | Output |
|------|-------------|-------|--------|
| VectorStoreList | Discover knowledge bases | None | Knowledge base roster |
| VectorStoreSearch | Semantic retrieval | Query text | Relevant passages |
| VectorStoreListFiles | Browse stored files | Vector store ID | File list |
| VectorStoreGetFile | Read a file | File ID | Full file content |

---

## 🚀 Quick Start

### 1. Upload Course Materials to a Vector Store
```bash
python file_index_downloader.py --upload-only
```

### 2. Launch Canvas Chat
```bash
python canvas_chat.py
```

### 3. Ask Questions
```
📝 You: List every knowledge base.

🤖 Assistant: Here are the knowledge bases I found:
1. [vs_abc123] Agent-Based Modeling
   📁 Files: 45

📝 You: Search the first knowledge base for NetLogo.

🤖 Assistant: 🔍 Query: "NetLogo"
📊 Found 3 relevant results...

📝 You: List the files in that knowledge base.

🤖 Assistant: 📚 Returned 45 files...

📝 You: Read the first file.

🤖 Assistant: 📄 File details and contents...
```

---

## ⚙️ Configuration

Ensure your `.env` file contains:

```env
# OpenAI API (required for vector stores)
OPENAI_API_KEY=sk-your-key-here

# Canvas API (required for downloading course files)
CANVAS_URL=https://your-canvas-domain.instructure.com
CANVAS_ACCESS_TOKEN=your-canvas-token
```

---

## 📖 Related Docs

- [Canvas API Reference](https://canvas.instructure.com/doc/api/)
- [Canvas API Guides](https://community.canvaslms.com/t5/Canvas-Developers/ct-p/developers)
- [Project README](./README.md)

---

## 🎓 Real-World Scenarios

### Scenario 1: Review Course Material
```
"What did we cover in Week 1?"
→ Agent searches the knowledge base for Week 1 lecture notes.
```

### Scenario 2: Confirm Assignment Requirements
```
"What files are tied to Assignment 2?"
→ Agent lists the relevant files and opens the assignment brief.
```

### Scenario 3: Prepare for Exams
```
"What should I study for the final?"
→ Agent searches the syllabus and exam announcements.
```

### Scenario 4: Locate References
```
"Where can I find sources on multi-agent systems?"
→ Agent searches for the topic, lists files, and previews relevant documents.
```

---

**Notes**:
- Reading file contents consumes OpenAI API quota.
- Large files may be truncated based on `max_length`.
- Binary files (PDF, images, etc.) are not rendered inline.
- Vector store search is semantic; it does not perform exact string matching.

Enjoy exploring your course knowledge bases! 🎉
