"""
Canvas Student Agent 示例

这个示例展示如何使用 Canvas API 工具集来帮助学生管理学习任务
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
    
    # 0. 检查必要的环境变量
    if not os.environ.get("CANVAS_ACCESS_TOKEN"):
        logger.error("错误: 未找到 CANVAS_ACCESS_TOKEN 环境变量")
        logger.error("请在 .env 文件中设置 CANVAS_ACCESS_TOKEN 和 CANVAS_URL")
        return
    
    # 1. 初始化 logger
    log_dir = Path("workdir/canvas_student")
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.init_logger(str(log_dir / "log.txt"))
    
    # 2. 从配置文件导入配置
    from configs.canvas_agent_config import agent_config
    
    # 3. 初始化模型管理器
    model_manager.init_models()
    
    # 4. 获取模型
    model = model_manager.registed_models[agent_config["model_id"]]
    
    # 5. 准备 Agent 配置
    agent_build_config = dict(
        type=agent_config["type"],
        config=agent_config,
        model=model,
        tools=agent_config["tools"],
        max_steps=agent_config["max_steps"],
        name=agent_config.get("name"),
        description=agent_config.get("description"),
    )
    
    # 6. 使用 Registry 创建 Agent
    agent = AGENT.build(agent_build_config)
    
    logger.info("Canvas Student Agent 创建成功！")
    logger.info(f"已加载 {len(agent_config['tools'])} 个 Canvas API 工具")
    
    # 7. 示例任务列表
    example_tasks = [
        "列出我所有的课程",
        "查看我的待办事项",
        "获取即将到来的事件",
        "查看最新的公告",
        # 你可以添加更多任务...
    ]
    
    # 选择要执行的任务
    print("\n" + "="*60)
    print("Canvas Student Agent 示例")
    print("="*60)
    print("\n可用的示例任务:")
    for i, task in enumerate(example_tasks, 1):
        print(f"{i}. {task}")
    
    print("\n请输入任务编号，或直接输入自定义任务:")
    user_input = input("> ").strip()
    
    # 确定要执行的任务
    if user_input.isdigit() and 1 <= int(user_input) <= len(example_tasks):
        task = example_tasks[int(user_input) - 1]
    else:
        task = user_input
    
    print(f"\n执行任务: {task}")
    print("-" * 60)
    
    # 8. 运行 Agent
    try:
        result = await agent.run(task)
        
        print("\n" + "="*60)
        print("任务完成！")
        print("="*60)
        print(f"\n结果:\n{result}\n")
        
    except Exception as e:
        logger.error(f"执行任务时出错: {str(e)}")
        print(f"\n错误: {str(e)}\n")


if __name__ == "__main__":
    asyncio.run(main())


