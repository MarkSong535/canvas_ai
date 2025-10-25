"""
Canvas Student Agent example.

Demonstrates how to use the Canvas API toolset to help students manage coursework.
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from src.models import model_manager
from src.registry import AGENT
from src.logger import logger, LogLevel


async def main():
    """Example entry point."""
    
    # 0. Validate required environment variables
    if not os.environ.get("CANVAS_ACCESS_TOKEN"):
        logger.error("Missing CANVAS_ACCESS_TOKEN environment variable")
        logger.error("Set CANVAS_ACCESS_TOKEN and CANVAS_URL in your .env file")
        return
    
    # 1. Initialize logger
    log_dir = Path("workdir/canvas_student")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.init_logger(str(log_dir / "log.txt"))
    
    # 2. Import the agent configuration
    from configs.canvas_agent_config import agent_config
    
    # 3. Initialize the model manager
    model_manager.init_models()
    
    # 4. Retrieve the model instance
    model = model_manager.registed_models[agent_config["model_id"]]
    
    # 5. Prepare the agent build configuration
    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=agent_config["tools"],
        max_steps=agent_config["max_steps"],
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )
    
    # 6. Build the agent via the registry
    agent = AGENT.build(agent_build_config)
    
    logger.info("Canvas Student Agent created successfully!")
    logger.info(f"Loaded {len(agent_config['tools'])} Canvas API tools")
    
    # 7. Example task list
    example_tasks = [
        "List all of my courses",
        "Show my to-do items",
        "Get upcoming events",
        "Show the latest announcements",
        # Add more tasks if you like...
    ]
    
    # Prompt for the task to run
    print("\n" + "=" * 60)
    print("Canvas Student Agent Example")
    print("=" * 60)
    print("\nAvailable sample tasks:")
    for i, task in enumerate(example_tasks, 1):
        print(f"{i}. {task}")
    
    print("\nEnter a task number or provide a custom prompt:")
    user_input = input("> ").strip()
    
    # Pick the task to execute
    if user_input.isdigit() and 1 <= int(user_input) <= len(example_tasks):
        task = example_tasks[int(user_input) - 1]
    else:
        task = user_input
    
    print(f"\nRunning task: {task}")
    print("-" * 60)
    
    # 8. Run the agent
    try:
        result = await agent.run(task)
        
        print("\n" + "=" * 60)
        print("Task completed!")
        print("=" * 60)
        print(f"\nResult:\n{result}\n")
        
    except Exception as e:
        logger.error(f"Error while running the task: {str(e)}")
        print(f"\nError: {str(e)}\n")


if __name__ == "__main__":
    asyncio.run(main())


