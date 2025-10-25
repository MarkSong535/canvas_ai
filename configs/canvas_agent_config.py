"""
Canvas Student Agent 配置文件

这个配置文件定义了一个专门用于 Canvas LMS 的学生助手 Agent
集成了所有学生权限的 Canvas API 工具
"""

from src.tools.canvas_tools import (
    CanvasListCourses,
    CanvasGetAssignments,
    CanvasSubmitAssignment,
    CanvasGetModules,
    CanvasGetModuleItems,
    CanvasGetFiles,
    CanvasGetFileInfo,
    CanvasDownloadFile,
    CanvasGetFolders,
    CanvasGetFolderFiles,
    CanvasSearchFiles,
    CanvasGetDiscussions,
    CanvasPostDiscussion,
    CanvasGetAnnouncements,
    CanvasGetCalendarEvents,
    CanvasGetGrades,
    CanvasGetPages,
    CanvasGetPageContent,
    CanvasGetQuizzes,
    CanvasGetTodoItems,
    CanvasGetUpcomingEvents,
    CanvasGetGroups,
    VectorStoreList,
    VectorStoreSearch,
    VectorStoreListFiles,
    VectorStoreGetFile,
)

# Canvas 学生 Agent 配置
canvas_student_agent_config = dict(
    type="general_agent",
    name="canvas_student_agent",
    description="Canvas LMS 学生助手，帮助学生管理课程、作业、讨论等",
    model_id="gpt-4o",  # 默认使用 OpenAI GPT-4o，可替换为其他已注册模型别名
    max_steps=15,
    template_path="src/agent/general_agent/prompts/general_agent.yaml",  # Prompt模板路径
    
    # 初始化所有 Canvas 工具
    tools=[
        CanvasListCourses(),              # 列出课程
        CanvasGetAssignments(),           # 获取作业
        CanvasSubmitAssignment(),         # 提交作业
        CanvasGetModules(),               # 获取模块
        CanvasGetModuleItems(),           # 获取模块项
        CanvasGetFiles(),                 # 获取文件列表
        CanvasGetFileInfo(),              # 获取文件详情
        CanvasDownloadFile(),             # 下载文件
        CanvasGetFolders(),               # 获取文件夹
        CanvasGetFolderFiles(),           # 获取文件夹文件
        CanvasSearchFiles(),              # 搜索文件
        CanvasGetDiscussions(),           # 获取讨论
        CanvasPostDiscussion(),           # 发表讨论
        CanvasGetAnnouncements(),         # 获取公告
        CanvasGetCalendarEvents(),        # 获取日历事件
        CanvasGetGrades(),                # 获取成绩
        CanvasGetPages(),                 # 获取页面
        CanvasGetPageContent(),           # 获取页面内容
        CanvasGetQuizzes(),               # 获取测验
        CanvasGetTodoItems(),             # 获取待办事项
        CanvasGetUpcomingEvents(),        # 获取即将事件
        CanvasGetGroups(),                # 获取小组
        VectorStoreList(),                # 列出知识库
        VectorStoreSearch(),              # 搜索知识库
        VectorStoreListFiles(),           # 列出知识库文件
        VectorStoreGetFile(),             # 读取文件内容
    ],
    
    # Agent 系统提示词可以在这里自定义
    # 或者在 src/agent/general_agent/prompts/general_agent.yaml 中修改
)

# 如果需要导出配置供 main.py 使用
agent_config = canvas_student_agent_config

