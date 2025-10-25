"""
模型模块 - 最小化版本
仅包含核心模型类和 Azure OpenAI 支持
"""

from .base import (
                 ChatMessage,
                 ChatMessageStreamDelta,
                 ChatMessageToolCall,
                 MessageRole,
                 Model,
                 parse_json_if_needed,
                 agglomerate_stream_deltas,
                 CODEAGENT_RESPONSE_FORMAT,
                 )
from .openaillm import OpenAIServerModel, AzureOpenAIServerModel
from .models import ModelManager
from .message_manager import MessageManager

model_manager = ModelManager()

__all__ = [
    "Model",
    "ChatMessage",
    "ChatMessageStreamDelta",
    "ChatMessageToolCall",
    "MessageRole",
    "OpenAIServerModel",
    "AzureOpenAIServerModel",
    "parse_json_if_needed",
    "agglomerate_stream_deltas",
    "model_manager",
    "ModelManager",
    "MessageManager",
]