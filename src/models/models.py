import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv(verbose=True)

from src.logger import logger
from src.models.openaillm import OpenAIServerModel
from src.utils import Singleton

PLACEHOLDER = "PLACEHOLDER"

# Price cap (USD per 1M tokens): neither the input nor the output price may exceed it
MAX_PRICE_PER_1M_TOKENS = 5.0

# OpenAI standard-tier prices
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
    """Model manager: registers and looks up the available models."""
    
    def __init__(self):
        self.registed_models: Dict[str, Any] = {}
        
    def init_models(self, use_local_proxy: bool = False) -> int:
        """Register all models (currently only the official OpenAI API)."""

        # Clear first when re-initializing, so configuration changes take effect immediately
        self.registed_models.clear()

        registered_count = self._register_openai_models(use_local_proxy=use_local_proxy)

        if registered_count == 0:
            logger.error("=" * 70)
            logger.error("No usable LLM configuration found!")
            logger.error("=" * 70)
            logger.error("Configure at least one of the following in .env:")
            logger.error("- OPENAI_API_KEY (+ optional OPENAI_BASE_URL / OPENAI_ORGANIZATION / OPENAI_PROJECT)")
            logger.error("=" * 70)
            raise ValueError("Model configuration missing; check your .env file")

        return registered_count

    def _register_openai_models(self, use_local_proxy: bool = False) -> int:
        """Register the official OpenAI models."""
        logger.info("Registering OpenAI models")

        if use_local_proxy:
            api_key = self._check_local_api_key("LOCAL_OPENAI_API_KEY", "OPENAI_API_KEY")
            api_base = self._check_local_api_base("LOCAL_OPENAI_API_BASE", "OPENAI_API_BASE")
        else:
            api_key = os.getenv("OPENAI_API_KEY", PLACEHOLDER)
            api_base = os.getenv("OPENAI_API_BASE", PLACEHOLDER)

        # Also accept other common names for the base-URL environment variable
        if api_base == PLACEHOLDER:
            api_base = os.getenv("OPENAI_BASE_URL", PLACEHOLDER)
        if api_base == PLACEHOLDER:
            api_base = os.getenv("OPENAI_API_URL", PLACEHOLDER)

        if api_key == PLACEHOLDER:
            logger.warning("OPENAI_API_KEY not found; skipping OpenAI model registration")
            return 0

        organization = os.getenv("OPENAI_ORGANIZATION") or os.getenv("OPENAI_ORG")
        project = os.getenv("OPENAI_PROJECT")

        client_kwargs: Dict[str, Any] = {}
        max_retries = os.getenv("OPENAI_MAX_RETRIES")
        if max_retries:
            try:
                client_kwargs["max_retries"] = int(max_retries)
            except ValueError:
                logger.warning("OPENAI_MAX_RETRIES is not a valid integer; ignoring it")

        timeout = os.getenv("OPENAI_TIMEOUT")
        if timeout:
            try:
                client_kwargs["timeout"] = float(timeout)
            except ValueError:
                logger.warning("OPENAI_TIMEOUT is not a valid number; ignoring it")

        if api_base == PLACEHOLDER:
            api_base = None

        registered = 0

        for model_config in OPENAI_MODELS:
            model_id = model_config["model_id"]
            aliases = model_config.get("aliases", []) or [model_id]

            # Price-cap guard: a model whose input or output price exceeds the cap is never registered
            if max(model_config["input_price"], model_config["output_price"]) > MAX_PRICE_PER_1M_TOKENS:
                logger.warning(f"Model {model_id} costs more than ${MAX_PRICE_PER_1M_TOKENS}/1M tokens; not registering it")
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
            except Exception as exc:  # noqa: BLE001 - catch and log initialization errors
                logger.error(f"Failed to register OpenAI model {model_id}: {exc}")
                continue

            for alias in aliases:
                if alias in self.registed_models:
                    logger.debug(f"Model alias {alias} already exists; not overwriting it")
                    continue

                self.registed_models[alias] = model
                registered += 1
                logger.info(f"Registered OpenAI model: {alias} (ID: {model_id})")

        if registered == 0:
            logger.warning("No OpenAI models were registered; check the model aliases or configuration")

        return registered

    def _check_local_api_key(self, local_api_key_name: str, remote_api_key_name: str) -> str:
        """Use the local API key if set, else the remote one."""
        api_key = os.getenv(local_api_key_name, PLACEHOLDER)
        if api_key == PLACEHOLDER:
            logger.warning(f"Local API key {local_api_key_name} is not set, using remote API key {remote_api_key_name}")
            api_key = os.getenv(remote_api_key_name, PLACEHOLDER)
        return api_key
    
    def _check_local_api_base(self, local_api_base_name: str, remote_api_base_name: str) -> str:
        """Use the local API base URL if set, else the remote one."""
        api_base = os.getenv(local_api_base_name, PLACEHOLDER)
        if api_base == PLACEHOLDER:
            logger.warning(f"Local API base {local_api_base_name} is not set, using remote API base {remote_api_base_name}")
            api_base = os.getenv(remote_api_base_name, PLACEHOLDER)
        return api_base

    def get_model(self, model_name: str):
        """Return a registered model instance."""
        if model_name not in self.registed_models:
            raise ValueError(f"Model {model_name} is not registered. Available models: {list(self.registed_models.keys())}")
        return self.registed_models[model_name]
    
    def list_models(self):
        """List all registered models."""
        return list(self.registed_models.keys())


# Global model manager instance
model_manager = ModelManager()
