# Vector Store 工具使用说明

## 📚 工具概览

Canvas AI Agent 现在包含 **4 个 Vector Store 工具**，用于管理和搜索课程知识库：

### 1️⃣ VectorStoreList - 列出知识库
**功能**：列出所有可用的 Vector Stores（课程知识库）

**参数**：无

**输出**：
- Vector Store ID
- 名称
- 文件数量
- 创建时间

**使用示例**：
```
"列出所有可用的知识库"
"我有哪些课程的资料库？"
```

---

### 2️⃣ VectorStoreSearch - 语义搜索
**功能**：在指定的知识库中进行语义搜索，找到相关内容

**参数**：
- `vector_store_id` (必需): Vector Store ID
- `query` (必需): 搜索查询
- `max_results` (可选): 最大结果数（默认5）

**输出**：
- 相关性分数
- 来源文件
- 内容片段

**使用示例**：
```
"在知识库 vs_xxx 中搜索关于 Agent-Based Modeling 的内容"
"这门课的主要内容是什么？"
"第一次作业的要求是什么？"
```

---

### 3️⃣ VectorStoreListFiles - 列出文件 ⭐ 新增
**功能**：列出指定知识库中的所有文件

**参数**：
- `vector_store_id` (必需): Vector Store ID
- `read_content` (可选): 是否读取文件内容（默认 False）
- `limit` (可选): 最大文件数（默认 20）

**输出**：
- File ID
- 文件名
- 文件状态
- 创建时间
- 文件大小
- 内容预览（如果启用）

**使用示例**：
```
"列出知识库 vs_xxx 中的所有文件"
"查看这个知识库有哪些文件"
"显示知识库文件，并读取内容"
```

---

### 4️⃣ VectorStoreGetFile - 读取文件 ⭐ 新增
**功能**：根据 file_id 获取文件详细信息并读取完整内容

**参数**：
- `file_id` (必需): OpenAI File ID
- `max_length` (可选): 最大显示长度（默认 5000 字符）

**输出**：
- 文件详细信息（名称、大小、状态等）
- 完整文件内容（支持文本文件）
- 文件类型识别（PDF、Office 文档等）

**使用示例**：
```
"读取文件 file-xxx 的内容"
"显示这个文件的详细信息"
"查看文件内容，最多显示 10000 字符"
```

---

## 🎯 典型使用流程

### 流程 1：浏览课程资料

```
1. 用户: "列出所有知识库"
   → Agent 调用 VectorStoreList()

2. 用户: "列出第一个知识库的所有文件"
   → Agent 调用 VectorStoreListFiles(vector_store_id="vs_xxx")

3. 用户: "读取第一个文件的内容"
   → Agent 调用 VectorStoreGetFile(file_id="file-xxx")
```

### 流程 2：搜索特定内容

```
1. 用户: "这门课讲了什么内容？"
   → Agent 调用 VectorStoreList() 找到相关知识库
   → Agent 调用 VectorStoreSearch(vector_store_id="vs_xxx", query="课程内容")

2. 用户: "给我看看这个文件的完整内容"
   → Agent 调用 VectorStoreGetFile(file_id="file-xxx")
```

### 流程 3：查找作业资料

```
1. 用户: "作业1的要求是什么？"
   → Agent 调用 VectorStoreSearch(query="作业1要求")

2. 用户: "列出这个知识库的所有文件"
   → Agent 调用 VectorStoreListFiles(vector_store_id="vs_xxx")

3. 用户: "读取作业1相关的文件"
   → Agent 调用 VectorStoreGetFile(file_id="file-xxx")
```

---

## 💡 使用技巧

### 1. 文件类型支持
- ✅ **文本文件**: .txt, .md, .py, .java, .cpp, .json 等
- ✅ **PDF 文档**: 识别但不直接显示（需专门处理）
- ✅ **Office 文档**: .docx, .xlsx, .pptx（识别文件类型）

### 2. 内容长度控制
- `VectorStoreListFiles` 默认显示 1000 字符预览
- `VectorStoreGetFile` 默认显示 5000 字符
- 可通过 `max_length` 参数调整

### 3. 批量处理
- `VectorStoreListFiles` 的 `limit` 参数可控制返回文件数
- 默认 20 个文件，可根据需要调整

### 4. 搜索优化
- 使用具体的关键词
- 指定特定主题或章节
- 组合使用搜索和文件读取

---

## 🔧 命令行测试

### 测试脚本 1：直接工具测试
```bash
python examples/test_vector_store_tools.py
```

**功能**：
- 测试单个工具功能
- 交互式菜单
- 直接调用工具或通过 Agent

### 测试脚本 2：搜索测试
```bash
python test_vector_store_search.py
```

**功能**：
- 列出 Vector Stores
- 交互式搜索
- 快速搜索模式

---

## 📊 工具对比

| 工具 | 主要用途 | 输入 | 输出 |
|------|----------|------|------|
| VectorStoreList | 发现知识库 | 无 | 知识库列表 |
| VectorStoreSearch | 语义搜索 | 查询语句 | 相关内容片段 |
| VectorStoreListFiles | 浏览文件 | Vector Store ID | 文件列表 |
| VectorStoreGetFile | 读取文件 | File ID | 完整文件内容 |

---

## 🚀 快速开始

### 1. 上传课程资料到 Vector Store
```bash
python file_index_downloader.py --upload-only
```

### 2. 启动 Canvas Chat
```bash
python canvas_chat.py
```

### 3. 开始提问
```
📝 你: 列出所有知识库

🤖 助手: 我找到了以下知识库：
1. [vs_abc123] Agent-Based Modeling 课程
   📁 文件数量: 45

📝 你: 在第一个知识库中搜索关于 NetLogo 的内容

🤖 助手: 🔍 搜索查询: "NetLogo"
📊 找到 3 个相关结果...

📝 你: 列出这个知识库的所有文件

🤖 助手: 📚 找到 45 个文件...

📝 你: 读取第一个文件的内容

🤖 助手: 📄 文件详细信息...
```

---

## ⚙️ 配置要求

确保 `.env` 文件包含：

```env
# OpenAI API（用于 Vector Store）
OPENAI_API_KEY=sk-your-key-here

# Canvas API（用于下载课程文件）
CANVAS_URL=https://your-canvas-domain.instructure.com
CANVAS_ACCESS_TOKEN=your-canvas-token

# Azure OpenAI（用于 Agent LLM）
AZURE_OPENAI_ENDPOINT=your-endpoint
AZURE_OPENAI_API_KEY=your-azure-key
```

---

## 📖 相关文档

- [Canvas API 完整文档](./Canvas_API_完整文档.md)
- [Canvas API 快速参考](./Canvas_API_快速参考.md)
- [项目 README](./README.md)

---

## 🎓 实际应用场景

### 场景 1：复习课程内容
```
"这门课第一周讲了什么？"
→ Agent 搜索知识库找到第一周的讲义
```

### 场景 2：查找作业要求
```
"作业2有哪些文件？"
→ Agent 列出作业相关文件
→ Agent 读取作业说明文件
```

### 场景 3：准备考试
```
"期末考试会考什么内容？"
→ Agent 搜索课程大纲
→ Agent 搜索考试相关公告
```

### 场景 4：查找参考资料
```
"关于多智能体系统的参考文献在哪里？"
→ Agent 搜索相关主题
→ Agent 列出相关文件
→ Agent 显示文件内容
```

---

**注意事项**：
- 文件内容读取需要 OpenAI API 权限
- 大文件可能会被截断显示
- 二进制文件（PDF、图片等）无法直接显示全文
- Vector Store 搜索使用语义相似度，不是精确匹配

祝您使用愉快！🎉

