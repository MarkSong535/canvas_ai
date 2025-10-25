"""
模型管理器 - 最小化版本
仅支持 Azure OpenAI 模型
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv(verbose=True)

from src.logger import logger
from src.models.openaillm import AzureOpenAIServerModel
from src.utils import Singleton

PLACEHOLDER = "PLACEHOLDER"


class ModelManager(metaclass=Singleton):
    """模型管理器 - 负责注册和管理可用的模型"""
    
    def __init__(self):
        self.registed_models: Dict[str, Any] = {}
        
    def init_models(self, use_local_proxy: bool = False):
        """初始化所有模型（当前仅支持 Azure OpenAI）"""
        self._register_azureopenai_models(use_local_proxy=use_local_proxy)

    def _check_local_api_key(self, local_api_key_name: str, remote_api_key_name: str) -> str:
        """检查本地和远程 API Key"""
        api_key = os.getenv(local_api_key_name, PLACEHOLDER)
        if api_key == PLACEHOLDER:
            logger.warning(f"Local API key {local_api_key_name} is not set, using remote API key {remote_api_key_name}")
            api_key = os.getenv(remote_api_key_name, PLACEHOLDER)
        return api_key
    
    def _check_local_api_base(self, local_api_base_name: str, remote_api_base_name: str) -> str:
        """检查本地和远程 API Base"""
        api_base = os.getenv(local_api_base_name, PLACEHOLDER)
        if api_base == PLACEHOLDER:
            logger.warning(f"Local API base {local_api_base_name} is not set, using remote API base {remote_api_base_name}")
            api_base = os.getenv(remote_api_base_name, PLACEHOLDER)
        return api_base

    def _register_azureopenai_models(self, use_local_proxy: bool = False):
        """注册 Azure OpenAI 模型"""
        logger.info("注册 Azure OpenAI 模型")
        
        # Azure OpenAI 模型列表
        azure_models = [
            {
                "model_name": "gpt-5",
                "model_id": "gpt-5",
            },
            {
                "model_name": "azure-gpt-5",
                "model_id": "gpt-5",
            },
            {
                "model_name": "azure-gpt-4o",
                "model_id": "gpt-4o",
            },
            {
                "model_name": "azure-gpt-4o-mini",
                "model_id": "gpt-4o-mini",
            },
            {
                "model_name": "azure-gpt-4",
                "model_id": "gpt-4",
            },
            {
                "model_name": "gpt-4o",
                "model_id": "gpt-4o",
            },
            {
                "model_name": "gpt-4",
                "model_id": "gpt-4",
            },
        ]
        
        # 从环境变量获取 Azure OpenAI 配置
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", PLACEHOLDER)
        api_key = os.getenv("AZURE_OPENAI_API_KEY", PLACEHOLDER)
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
        
        if azure_endpoint == PLACEHOLDER or api_key == PLACEHOLDER:
            logger.error("=" * 70)
            logger.error("Azure OpenAI 配置未完成！")
            logger.error("=" * 70)
            logger.error("请在项目根目录创建 .env 文件，并添加以下配置：")
            logger.error("")
            logger.error("AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/")
            logger.error("AZURE_OPENAI_API_KEY=your-api-key-here")
            logger.error("AZURE_OPENAI_API_VERSION=2024-08-01-preview")
            logger.error("")
            logger.error("CANVAS_URL=https://your-school.instructure.com")
            logger.error("CANVAS_ACCESS_TOKEN=your-canvas-token-here")
            logger.error("=" * 70)
            raise ValueError("Azure OpenAI 配置缺失，请检查 .env 文件")
        
        # 注册每个模型
        for model_config in azure_models:
            model_name = model_config["model_name"]
            model_id = model_config["model_id"]
            
            try:
                # 创建 Azure OpenAI 模型实例
                # 注意: use_local_proxy 参数在最小化框架中被忽略
                model = AzureOpenAIServerModel(
                    model_id=model_id,
                    azure_endpoint=azure_endpoint,
                    api_key=api_key,
                    api_version=api_version,
                )
                
                self.registed_models[model_name] = model
                logger.info(f"成功注册模型: {model_name} (ID: {model_id})")
                
            except Exception as e:
                logger.error(f"注册模型 {model_name} 失败: {e}")
                
    def get_model(self, model_name: str):
        """获取已注册的模型实例"""
        if model_name not in self.registed_models:
            raise ValueError(f"模型 {model_name} 未注册。可用模型: {list(self.registed_models.keys())}")
        return self.registed_models[model_name]
    
    def list_models(self):
        """列出所有已注册的模型"""
        return list(self.registed_models.keys())


# 全局模型管理器实例
model_manager = ModelManager()
