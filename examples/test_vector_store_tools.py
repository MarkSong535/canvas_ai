1"""
测试 Vector Store 工具集成到 Agent

这个脚本演示如何通过 Agent 使用 Vector Store 搜索功能
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# 加载环境变量
load_dotenv()

console = Console()


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║     测试 Vector Store 工具集成                                ║
║     Test Vector Store Tools Integration                     ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")


async def test_vector_store_list():
    """测试列出 Vector Stores"""
    from src.tools.canvas_tools import VectorStoreList
    
    console.print("\n" + "="*60, style="cyan")
    console.print("📋 测试 1: 列出 Vector Stores", style="cyan bold")
    console.print("="*60, style="cyan")
    
    tool = VectorStoreList()
    result = await tool.forward()
    
    if result.error:
        console.print(f"❌ 错误: {result.error}", style="red")
    else:
        console.print(result.output, style="green")
    
    return result


async def test_vector_store_search(vector_store_id: str = None):
    """测试搜索 Vector Store"""
    from src.tools.canvas_tools import VectorStoreSearch
    
    console.print("\n" + "="*60, style="cyan")
    console.print("🔍 测试 2: 搜索 Vector Store", style="cyan bold")
    console.print("="*60, style="cyan")
    
    # 如果没有提供 vector_store_id，先获取列表
    if not vector_store_id:
        console.print("\n⚠️  未提供 Vector Store ID，将从列表中选择", style="yellow")
        list_result = await test_vector_store_list()
        
        if list_result.error or not list_result.output:
            console.print("❌ 无法获取 Vector Store 列表", style="red")
            return
        
        # 让用户输入 vector_store_id
        vector_store_id = console.input("\n请输入 Vector Store ID: ")
    
    # 测试查询
    test_queries = [
        "这门课的主要内容是什么？",
        "第一次作业的要求",
        "Agent-Based Modeling"
    ]
    
    console.print(f"\n✓ 使用 Vector Store: {vector_store_id}", style="green")
    console.print("\n📝 测试查询:", style="cyan bold")
    for i, query in enumerate(test_queries, 1):
        console.print(f"  {i}. {query}", style="dim")
    
    # 让用户选择查询
    choice = console.input("\n选择查询 (1-3) 或输入自定义查询: ")
    
    if choice.isdigit() and 1 <= int(choice) <= len(test_queries):
        query = test_queries[int(choice) - 1]
    else:
        query = choice
    
    console.print(f"\n🔍 搜索查询: \"{query}\"", style="cyan")
    
    # 执行搜索
    tool = VectorStoreSearch()
    result = await tool.forward(
        vector_store_id=vector_store_id,
        query=query,
        max_results=3
    )
    
    if result.error:
        console.print(f"\n❌ 错误: {result.error}", style="red")
    else:
        console.print(f"\n{result.output}", style="green")
    
    return result


async def test_with_agent():
    """测试通过 Agent 使用 Vector Store 工具"""
    console.print("\n" + "="*60, style="magenta")
    console.print("🤖 测试 3: 通过 Agent 使用工具", style="magenta bold")
    console.print("="*60, style="magenta")
    
    try:
        from configs.canvas_agent_config import canvas_student_agent_config
        from src.agent.general_agent.general_agent import GeneralAgent
        
        # 初始化 Agent
        console.print("\n🚀 正在初始化 Canvas Student Agent...", style="cyan")
        agent = GeneralAgent(**canvas_student_agent_config)
        console.print("✓ Agent 初始化成功", style="green")
        
        # 测试查询
        test_queries = [
            "列出所有可用的知识库",
            "在知识库中搜索关于 Agent-Based Modeling 的内容",
            "这门课有哪些主要的学习材料？"
        ]
        
        console.print("\n📝 可用的测试查询:", style="cyan bold")
        for i, query in enumerate(test_queries, 1):
            console.print(f"  {i}. {query}", style="dim")
        
        # 让用户选择或输入查询
        choice = console.input("\n选择查询 (1-3) 或输入自定义查询 (按 q 退出): ")
        
        if choice.lower() == 'q':
            return
        
        if choice.isdigit() and 1 <= int(choice) <= len(test_queries):
            query = test_queries[int(choice) - 1]
        else:
            query = choice
        
        console.print(f"\n💬 用户: {query}", style="blue bold")
        console.print("\n🤖 Agent 正在处理...\n", style="cyan")
        
        # 执行查询
        response = await agent.process_message(query)
        
        # 显示结果
        console.print(Panel(
            response,
            title="[green bold]Agent 响应[/green bold]",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(f"\n❌ 错误: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red dim")


async def main():
    """主函数"""
    print_banner()
    
    # 检查环境变量
    openai_key = os.getenv("OPENAI_API_KEY")
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
    
    console.print("\n📋 环境检查:", style="cyan bold")
    console.print(f"  {'✓' if openai_key else '✗'} OPENAI_API_KEY", 
                  style="green" if openai_key else "red")
    console.print(f"  {'✓' if canvas_url else '✗'} CANVAS_URL", 
                  style="green" if canvas_url else "red")
    console.print(f"  {'✓' if canvas_token else '✗'} CANVAS_ACCESS_TOKEN", 
                  style="green" if canvas_token else "red")
    
    if not all([openai_key, canvas_url, canvas_token]):
        console.print("\n❌ 缺少必要的环境变量", style="red bold")
        console.print("请在 .env 文件中配置以下变量:", style="yellow")
        if not openai_key:
            console.print("  - OPENAI_API_KEY", style="yellow")
        if not canvas_url:
            console.print("  - CANVAS_URL", style="yellow")
        if not canvas_token:
            console.print("  - CANVAS_ACCESS_TOKEN", style="yellow")
        return
    
    console.print()
    
    # 主菜单
    while True:
        console.print("\n" + "="*60, style="cyan")
        console.print("📋 测试菜单", style="cyan bold")
        console.print("="*60, style="cyan")
        console.print("  1. 列出所有 Vector Stores")
        console.print("  2. 搜索 Vector Store（直接调用工具）")
        console.print("  3. 通过 Agent 使用工具（完整流程）")
        console.print("  q. 退出")
        
        choice = console.input("\n请选择 (1-3/q): ")
        
        if choice.lower() == 'q':
            console.print("\n👋 再见！", style="cyan")
            break
        elif choice == '1':
            await test_vector_store_list()
        elif choice == '2':
            await test_vector_store_search()
        elif choice == '3':
            await test_with_agent()
        else:
            console.print("⚠️  无效的选择", style="yellow")
        
        input("\n按回车继续...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n👋 再见！", style="cyan")
    except Exception as e:
        console.print(f"\n❌ 发生错误: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red dim")

