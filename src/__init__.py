"""
DeepResearchAgent – minimal framework template.
This module exposes only the core tool interfaces.
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
