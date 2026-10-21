"""
模型管理器 - 最小化版本
仅支持 OpenAI 官方模型
"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv(verbose=True)

from src.logger import logger
from src.models.openaillm import OpenAIServerModel
from src.utils import Singleton

PLACEHOLDER = "PLACEHOLDER"

# 单价上限（美元 / 1M tokens），输入和输出价格都不得超过该值
MAX_PRICE_PER_1M_TOKENS = 5.0

# OpenAI 标准档价格（美元 / 1M tokens，短上下文），来源 developers.openai.com/api/docs/pricing，2026-10 核对
OPENAI_MODELS = [
    {"model_id": "gpt-6-luna", "aliases": ["gpt-6-luna", "openai-gpt-6-luna"],
     "input_price": 0.10, "output_price": 0.50, "kwargs": {"reasoning_effort": "none"}},
    {"model_id": "gpt-5.6-luna", "aliases": ["gpt-5.6-luna", "openai-gpt-5.6-luna"],
     "input_price": 0.20, "output_price": 1.20},
    {"model_id": "gpt-5.4-mini", "aliases": ["gpt-5.4-mini", "openai-gpt-5.4-mini"],
     "input_price": 0.75, "output_price": 4.50},
    {"model_id": "gpt-5.4-nano", "aliases": ["gpt-5.4-nano", "openai-gpt-5.4-nano"],
     "input_price": 0.20, "output_price": 1.25},
    {"model_id": "gpt-5-mini", "aliases": ["gpt-5-mini", "openai-gpt-5-mini"],
     "input_price": 0.25, "output_price": 2.00},
    {"model_id": "gpt-5-nano", "aliases": ["gpt-5-nano", "openai-gpt-5-nano"],
     "input_price": 0.05, "output_price": 0.40},
    {"model_id": "gpt-4.1-mini", "aliases": ["gpt-4.1-mini", "openai-gpt-4.1-mini"],
     "input_price": 0.40, "output_price": 1.60},
    {"model_id": "gpt-4.1-nano", "aliases": ["gpt-4.1-nano", "openai-gpt-4.1-nano"],
     "input_price": 0.10, "output_price": 0.40},
    {"model_id": "gpt-4o-mini", "aliases": ["gpt-4o-mini", "openai-gpt-4o-mini"],
     "input_price": 0.15, "output_price": 0.60},
    {"model_id": "o4-mini", "aliases": ["o4-mini", "openai-o4-mini"],
     "input_price": 1.10, "output_price": 4.40},
]


class ModelManager(metaclass=Singleton):
    """模型管理器 - 负责注册和管理可用的模型"""
    
    def __init__(self):
        self.registed_models: Dict[str, Any] = {}
        
    def init_models(self, use_local_proxy: bool = False) -> int:
        """初始化所有模型（当前仅支持 OpenAI 官方接口）"""

        # 重新初始化时先清空，保证配置变更即时生效
        self.registed_models.clear()

        registered_count = self._register_openai_models(use_local_proxy=use_local_proxy)

        if registered_count == 0:
            logger.error("=" * 70)
            logger.error("未检测到可用的大模型配置！")
            logger.error("=" * 70)
            logger.error("请在 .env 中至少配置以下任一项：")
            logger.error("- OPENAI_API_KEY (+ 可选 OPENAI_BASE_URL / OPENAI_ORGANIZATION / OPENAI_PROJECT)")
            logger.error("=" * 70)
            raise ValueError("模型配置缺失，请检查 .env 文件")

        return registered_count

    def _register_openai_models(self, use_local_proxy: bool = False) -> int:
        """注册 OpenAI 官方模型"""
        logger.info("注册 OpenAI 模型")

        if use_local_proxy:
            api_key = self._check_local_api_key("LOCAL_OPENAI_API_KEY", "OPENAI_API_KEY")
            api_base = self._check_local_api_base("LOCAL_OPENAI_API_BASE", "OPENAI_API_BASE")
        else:
            api_key = os.getenv("OPENAI_API_KEY", PLACEHOLDER)
            api_base = os.getenv("OPENAI_API_BASE", PLACEHOLDER)

        # 兼容其他常见的基础地址环境变量命名
        if api_base == PLACEHOLDER:
            api_base = os.getenv("OPENAI_BASE_URL", PLACEHOLDER)
        if api_base == PLACEHOLDER:
            api_base = os.getenv("OPENAI_API_URL", PLACEHOLDER)

        if api_key == PLACEHOLDER:
            logger.warning("未检测到 OPENAI_API_KEY，跳过 OpenAI 模型注册")
            return 0

        organization = os.getenv("OPENAI_ORGANIZATION") or os.getenv("OPENAI_ORG")
        project = os.getenv("OPENAI_PROJECT")

        client_kwargs: Dict[str, Any] = {}
        max_retries = os.getenv("OPENAI_MAX_RETRIES")
        if max_retries:
            try:
                client_kwargs["max_retries"] = int(max_retries)
            except ValueError:
                logger.warning("OPENAI_MAX_RETRIES 不是有效的整数，已忽略该配置")

        timeout = os.getenv("OPENAI_TIMEOUT")
        if timeout:
            try:
                client_kwargs["timeout"] = float(timeout)
            except ValueError:
                logger.warning("OPENAI_TIMEOUT 不是有效的数字，已忽略该配置")

        if api_base == PLACEHOLDER:
            api_base = None

        registered = 0

        for model_config in OPENAI_MODELS:
            model_id = model_config["model_id"]
            aliases = model_config.get("aliases", []) or [model_id]

            # 价格上限保护：输入或输出单价超过上限的模型一律不注册
            if max(model_config["input_price"], model_config["output_price"]) > MAX_PRICE_PER_1M_TOKENS:
                logger.warning(f"模型 {model_id} 单价超过 ${MAX_PRICE_PER_1M_TOKENS}/1M tokens，跳过注册")
                continue

            try:
                model = OpenAIServerModel(
                    model_id=model_id,
                    api_base=api_base,
                    api_key=api_key,
                    organization=organization,
                    project=project,
                    client_kwargs=client_kwargs or None,
                    **model_config.get("kwargs", {}),
                )
            except Exception as exc:  # noqa: BLE001 - 捕获并记录初始化异常
                logger.error(f"注册 OpenAI 模型 {model_id} 失败: {exc}")
                continue

            for alias in aliases:
                if alias in self.registed_models:
                    logger.debug(f"模型别名 {alias} 已存在，跳过覆盖")
                    continue

                self.registed_models[alias] = model
                registered += 1
                logger.info(f"成功注册 OpenAI 模型: {alias} (ID: {model_id})")

        if registered == 0:
            logger.warning("没有成功注册任何 OpenAI 模型，请检查模型别名或配置")

        return registered

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
