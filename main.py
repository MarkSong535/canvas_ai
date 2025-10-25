"""
最小化框架示例 - 运行GeneralAgent

这个示例展示如何使用核心框架运行一个简单的Agent
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from src.models import model_manager
from src.registry import AGENT
from src.logger import logger, LogLevel


async def main():
    """主函数"""
    
    # 0. 初始化 logger
    log_dir = Path("workdir/minimal")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.init_logger(str(log_dir / "log.txt"))
    
    # 1. 从配置文件导入配置
    from configs.minimal_config import agent_config
    
    # 2. 初始化模型管理器
    model_manager.init_models()
    
    # 3. 获取模型
    model = model_manager.registed_models[agent_config["model_id"]]
    
    # 4. 准备Agent配置
    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=[],  # 初始没有工具
        max_steps=agent_config["max_steps"],
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )
    
    # 5. 使用Registry创建Agent
    agent = AGENT.build(agent_build_config)
    
    logger.info("Agent创建成功！")
    # logger.visualize_agent_tree(agent)  # 如需可视化Agent树,请确保logger支持此功能
    
    # 6. 运行Agent
    task = "计算 123 + 456 的结果"
    logger.info(f"开始执行任务: {task}")
    
    result = await agent.run(task)
    
    logger.info(f"任务完成！")
    logger.info(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())

