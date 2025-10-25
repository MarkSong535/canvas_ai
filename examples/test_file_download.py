"""
Canvas 文件下载测试示例

这个示例展示如何使用 Canvas Agent 下载文件：
1. 列出课程列表
2. 获取课程文件
3. 下载特定文件
"""

import os
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# 导入配置
from configs.canvas_agent_config import canvas_student_agent_config
from src.registry import Registry

# 加载环境变量
load_dotenv()

console = Console()


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           Canvas 文件下载测试                                 ║
║           File Download Test Example                         ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")


async def test_file_download():
    """测试文件下载功能"""
    
    print_banner()
    
    # 检查环境变量
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
    
    if not canvas_url or not canvas_token:
        console.print("\n❌ 错误：未找到 Canvas 配置", style="red bold")
        console.print("请确保 .env 文件包含：", style="yellow")
        console.print("  - CANVAS_URL", style="yellow")
        console.print("  - CANVAS_ACCESS_TOKEN", style="yellow")
        return
    
    console.print(f"\n✓ Canvas URL: {canvas_url}", style="green")
    console.print(f"✓ Token 已配置", style="green")
    
    try:
        # 初始化 Agent
        console.print("\n[cyan]正在初始化 Canvas Agent...[/cyan]")
        registry = Registry()
        agent = registry.get_agent(canvas_student_agent_config)
        
        console.print("✓ Agent 初始化成功", style="green bold")
        
        # ========================================
        # 测试 1: 获取课程列表
        # ========================================
        console.print("\n" + "="*60, style="cyan")
        console.print("测试 1: 获取课程列表", style="cyan bold")
        console.print("="*60, style="cyan")
        
        query1 = "列出我的所有课程"
        console.print(f"\n💬 查询: {query1}", style="yellow")
        
        result1 = await agent.run(query1)
        console.print("\n📋 结果:", style="green bold")
        console.print(result1)
        
        # ========================================
        # 测试 2: 获取文件列表
        # ========================================
        console.print("\n" + "="*60, style="cyan")
        console.print("测试 2: 获取文件列表", style="cyan bold")
        console.print("="*60, style="cyan")
        
        # 让用户选择课程
        console.print("\n请查看上面的课程列表", style="yellow")
        course_id = console.input("\n请输入要查看文件的课程ID (或直接回车跳过): ")
        
        if course_id.strip():
            query2 = f"获取课程 {course_id} 的所有文件"
            console.print(f"\n💬 查询: {query2}", style="yellow")
            
            result2 = await agent.run(query2)
            console.print("\n📁 文件列表:", style="green bold")
            console.print(result2)
            
            # ========================================
            # 测试 3: 下载文件
            # ========================================
            console.print("\n" + "="*60, style="cyan")
            console.print("测试 3: 下载文件", style="cyan bold")
            console.print("="*60, style="cyan")
            
            file_id = console.input("\n请输入要下载的文件ID (或直接回车跳过): ")
            
            if file_id.strip():
                query3 = f"下载文件 {file_id}"
                console.print(f"\n💬 查询: {query3}", style="yellow")
                
                result3 = await agent.run(query3)
                console.print("\n📥 下载结果:", style="green bold")
                console.print(result3)
        else:
            console.print("\n⏩ 跳过文件操作测试", style="yellow")
        
        # ========================================
        # 测试 4: 搜索文件
        # ========================================
        console.print("\n" + "="*60, style="cyan")
        console.print("测试 4: 搜索文件", style="cyan bold")
        console.print("="*60, style="cyan")
        
        search_term = console.input("\n请输入搜索关键词 (或直接回车跳过): ")
        
        if search_term.strip():
            query4 = f"搜索文件名包含 '{search_term}' 的文件"
            console.print(f"\n💬 查询: {query4}", style="yellow")
            
            result4 = await agent.run(query4)
            console.print("\n🔍 搜索结果:", style="green bold")
            console.print(result4)
            
            # 尝试下载搜索到的文件
            download_choice = console.input("\n是否要下载搜索到的某个文件? 输入文件ID (或直接回车跳过): ")
            
            if download_choice.strip():
                query5 = f"下载文件 {download_choice}"
                console.print(f"\n💬 查询: {query5}", style="yellow")
                
                result5 = await agent.run(query5)
                console.print("\n📥 下载结果:", style="green bold")
                console.print(result5)
        else:
            console.print("\n⏩ 跳过搜索测试", style="yellow")
        
        # ========================================
        # 测试完成
        # ========================================
        console.print("\n" + "="*60, style="green")
        console.print("✅ 所有测试完成！", style="green bold")
        console.print("="*60, style="green")
        
    except Exception as e:
        console.print(f"\n❌ 错误: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red")


async def quick_download_test(file_id: str):
    """快速下载测试（直接指定文件ID）"""
    
    print_banner()
    
    console.print(f"\n🎯 快速下载测试 - 文件ID: {file_id}", style="cyan bold")
    
    try:
        # 初始化 Agent
        console.print("\n[cyan]正在初始化 Canvas Agent...[/cyan]")
        registry = Registry()
        agent = registry.get_agent(canvas_student_agent_config)
        
        console.print("✓ Agent 初始化成功", style="green bold")
        
        # 下载文件
        console.print("\n" + "="*60, style="cyan")
        console.print("开始下载文件", style="cyan bold")
        console.print("="*60, style="cyan")
        
        query = f"下载文件 {file_id}"
        console.print(f"\n💬 查询: {query}", style="yellow")
        
        result = await agent.run(query)
        console.print("\n📥 下载结果:", style="green bold")
        console.print(result)
        
        console.print("\n" + "="*60, style="green")
        console.print("✅ 测试完成！", style="green bold")
        console.print("="*60, style="green")
        
    except Exception as e:
        console.print(f"\n❌ 错误: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red")


def main():
    """主函数"""
    
    # 检查命令行参数
    if len(sys.argv) > 1:
        # 快速下载模式：python test_file_download.py <file_id>
        file_id = sys.argv[1]
        asyncio.run(quick_download_test(file_id))
    else:
        # 交互式测试模式
        asyncio.run(test_file_download())


if __name__ == "__main__":
    main()

