"""
带工具的Agent使用示例

这个示例展示如何给Agent添加自定义工具
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
    """主函数"""
    
    # 1. 从配置文件导入配置
    from configs.minimal_config import agent_config
    
    # 2. 初始化模型管理器
    model_manager.init_models()
    
    # 3. 获取模型
    model = model_manager.registed_models[agent_config["model_id"]]
    
    # 4. 创建工具实例
    calculator = CalculatorTool()
    
    # 5. 准备Agent配置（添加工具）
    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=[calculator],  # 添加计算器工具
        max_steps=agent_config["max_steps"],
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )
    
    # 6. 使用Registry创建Agent
    agent = AGENT.build(agent_build_config)
    
    logger.info("Agent创建成功（带计算器工具）！")
    logger.info(f"可用工具: {list(agent.tools.keys())}")
    
    # 7. 运行Agent
    task = "计算 123 + 456 的结果"
    logger.info(f"\n开始执行任务: {task}\n")
    
    result = await agent.run(task)
    
    logger.info(f"\n任务完成！")
    logger.info(f"结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())

