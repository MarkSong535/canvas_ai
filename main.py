"""
Minimal framework example – run a GeneralAgent.

Demonstrates how to launch a simple agent using the core framework components.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env if present

from src.models import model_manager
from src.registry import AGENT
from src.logger import logger, LogLevel


async def main():
    """Entry point for the minimal demo."""
    
    # 0. Initialize the logger
    log_dir = Path("workdir/minimal")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.init_logger(str(log_dir / "log.txt"))
    
    # 1. Import the agent configuration
    from configs.minimal_config import agent_config
    
    # 2. Initialize the model manager
    model_manager.init_models()
    
    # 3. Retrieve the backing model
    model = model_manager.registed_models[agent_config["model_id"]]
    
    # 4. Prepare the agent build configuration
    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=[],  # No tools enabled for this minimal example
        max_steps=agent_config["max_steps"],
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )
    
    # 5. Build the agent via the registry
    agent = AGENT.build(agent_build_config)
    
    logger.info("Agent created successfully!")
    # logger.visualize_agent_tree(agent)  # Enable if logger supports agent tree visualization
    
    # 6. Execute the agent
    task = "Calculate 123 + 456"
    logger.info(f"Starting task: {task}")
    
    result = await agent.run(task)
    
    logger.info("Task completed!")
    logger.info(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())

