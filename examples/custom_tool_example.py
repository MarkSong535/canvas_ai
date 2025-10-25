"""
Agent example with a custom tool.

Demonstrates how to attach a custom tool to an agent.
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

from src.models import model_manager
from src.registry import AGENT
from src.logger import logger
from src.tools.example_calculator import CalculatorTool


async def main():
    """Example entry point."""
    
    # 1. Import the baseline configuration
    from configs.minimal_config import agent_config
    
    # 2. Initialize the model manager
    model_manager.init_models()
    
    # 3. Retrieve the model instance
    model = model_manager.registed_models[agent_config["model_id"]]
    
    # 4. Create the tool instance
    calculator = CalculatorTool()
    
    # 5. Prepare the agent configuration (injecting the tool)
    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=[calculator],  # Add the calculator tool
        max_steps=agent_config["max_steps"],
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )
    
    # 6. Build the agent via the registry
    agent = AGENT.build(agent_build_config)
    
    logger.info("Agent created successfully with the calculator tool attached!")
    logger.info(f"Available tools: {list(agent.tools.keys())}")
    
    # 7. Run the agent
    task = "Calculate 123 + 456"
    logger.info(f"\nStarting task: {task}\n")
    
    result = await agent.run(task)
    
    logger.info("\nTask complete!")
    logger.info(f"Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())

