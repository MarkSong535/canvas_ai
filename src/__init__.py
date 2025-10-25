"""
DeepResearchAgent - 最小化框架模板
此文件仅导入核心模块，不包含高级工具
"""

from .tools import (
    Tool,
    ToolResult,
    AsyncTool,
    FinalAnswerTool,
    make_tool_instance,
)

__all__ = [
    "Tool",
    "ToolResult", 
    "AsyncTool",
    "FinalAnswerTool",
    "make_tool_instance",
]
