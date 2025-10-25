"""
Canvas Student Agent 交互式控制台

这是一个交互式命令行界面，允许学生通过自然语言与Canvas Agent对话
"""

import subprocess
import sys
import importlib


def check_and_install_dependencies():
    """检查并自动安装缺失的依赖库"""
    
    # 完整的依赖包列表
    required_packages = {
        # 核心依赖
        'asyncio': None,  # Python 标准库，无需安装
        'aiohttp': 'aiohttp>=3.9.0',
        'dotenv': 'python-dotenv>=1.0.0',
        'rich': 'rich>=13.0.0',
        'openai': 'openai>=1.0.0',
        'pydantic': 'pydantic>=2.0.0',
        'jinja2': 'jinja2>=3.0.0',
        'yaml': 'pyyaml>=6.0.0',
        
        # 配置和日志
        'mmengine': 'mmengine>=0.10.0',
        'huggingface_hub': 'huggingface-hub>=0.19.0',
        
        # 文档处理
        'markitdown': 'markitdown',
        
        # 其他可能的依赖
        'PIL': 'Pillow',
        'cv2': 'opencv-python',
        'numpy': 'numpy',
        'requests': 'requests',
        'tiktoken': 'tiktoken',
        'anthropic': 'anthropic',
        'bs4': 'beautifulsoup4',
        'markdown': 'markdown',
        'chardet': 'chardet',
    }
    
    missing_packages = []
    installed_count = 0
    
    print("🔍 检查依赖库...\n")
    
    for module_name, package_name in required_packages.items():
        if package_name is None:  # 标准库，跳过
            continue
            
        try:
            importlib.import_module(module_name)
            print(f"  ✓ {module_name}")
            installed_count += 1
        except ImportError:
            print(f"  ✗ {module_name} (需要安装)")
            missing_packages.append(package_name)
    
    print(f"\n已安装: {installed_count}/{len([p for p in required_packages.values() if p is not None])}")
    
    if missing_packages:
        print(f"\n📦 发现 {len(missing_packages)} 个缺失的依赖库")
        
        # 询问用户是否自动安装
        try:
            response = input("\n是否自动安装缺失的依赖库? [Y/n]: ").strip().lower()
            if response and response not in ['y', 'yes', '是']:
                print("\n⚠️  跳过自动安装")
                print("请手动运行: pip install -r requirements.txt")
                return False
        except (KeyboardInterrupt, EOFError):
            print("\n\n⚠️  跳过自动安装")
            return False
        
        print("\n正在安装缺失的依赖库...")
        print("=" * 60)
        
        failed_packages = []
        
        for package in missing_packages:
            try:
                print(f"\n📦 安装 {package}...", end=" ")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", package, "-q", "--upgrade"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    print("✓ 成功")
                else:
                    print(f"✗ 失败")
                    if result.stderr:
                        print(f"   错误: {result.stderr[:200]}")
                    failed_packages.append(package)
                    
            except subprocess.TimeoutExpired:
                print("✗ 超时")
                failed_packages.append(package)
            except Exception as e:
                print(f"✗ 异常: {str(e)}")
                failed_packages.append(package)
        
        print("\n" + "=" * 60)
        
        if failed_packages:
            print(f"\n⚠️  {len(failed_packages)} 个包安装失败:")
            for pkg in failed_packages:
                print(f"   - {pkg}")
            print("\n请手动运行以下命令安装:")
            print(f"   pip install {' '.join(failed_packages)}")
            
            # 询问是否继续
            try:
                response = input("\n是否继续运行程序? [y/N]: ").strip().lower()
                if response not in ['y', 'yes', '是']:
                    return False
            except (KeyboardInterrupt, EOFError):
                return False
        else:
            print("\n✅ 所有依赖库安装完成！")
    else:
        print("\n✅ 所有依赖库已就绪！")
    
    return True


# 在导入其他模块之前，先检查并安装依赖
if __name__ == "__main__":
    if not check_and_install_dependencies():
        print("\n⚠️  依赖安装失败，程序无法继续运行")
        print("请手动运行: pip install -r requirements.txt")
        sys.exit(1)


import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich import print as rprint

# 加载环境变量
load_dotenv()

from src.models import model_manager
from src.registry import AGENT
from src.logger import logger


console = Console()


def print_banner():
    """打印欢迎横幅"""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🎓 Canvas Student Agent 交互式控制台 🎓          ║
    ║                                                           ║
    ║           您的 Canvas LMS 智能学习助手                   ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def print_help():
    """打印帮助信息"""
    help_text = """
    [bold cyan]📖 可用命令:[/bold cyan]
    
    [yellow]help[/yellow]     - 显示此帮助信息
    [yellow]clear[/yellow]    - 清空屏幕
    [yellow]examples[/yellow] - 显示示例问题
    [yellow]status[/yellow]   - 显示 Canvas 连接状态
    [yellow]exit[/yellow]     - 退出程序
    [yellow]quit[/yellow]     - 退出程序
    
    [bold cyan]💬 如何使用:[/bold cyan]
    
    直接输入您的问题，Agent 会帮您处理！例如：
    • "列出我的所有课程"
    • "查看我的待办事项"
    • "获取数学课的作业"
    • "今天有什么事件？"
    • "查看最新公告"
    """
    console.print(Panel(help_text, title="帮助", border_style="green"))


def print_examples():
    """打印示例问题"""
    examples_text = """
    [bold cyan]📝 示例问题:[/bold cyan]
    
    [bold yellow]📚 课程相关:[/bold yellow]
    • 列出我所有的课程
    • 显示课程XXX的详细信息
    • 获取数学课的模块结构
    
    [bold yellow]📝 作业相关:[/bold yellow]
    • 查看所有待办作业
    • 获取课程123的作业列表
    • 提交作业456的URL: https://example.com
    
    [bold yellow]📅 日程相关:[/bold yellow]
    • 今天有什么安排？
    • 查看本周的日历事件
    • 显示即将到来的事件
    
    [bold yellow]💬 讨论相关:[/bold yellow]
    • 查看课程456的讨论
    • 在讨论123中回复: 我同意这个观点
    
    [bold yellow]📊 成绩相关:[/bold yellow]
    • 查看我在课程789的成绩
    • 显示我的所有成绩
    
    [bold yellow]📢 通知相关:[/bold yellow]
    • 查看最新公告
    • 获取所有课程的公告
    
    [bold yellow]📄 文件和资源:[/bold yellow]
    • 列出课程456的所有文件
    • 搜索课程中的PDF文件
    • 查看课程页面列表
    """
    console.print(Panel(examples_text, title="示例问题", border_style="blue"))


async def check_canvas_connection():
    """检查 Canvas API 连接状态"""
    try:
        import aiohttp
        canvas_url = os.environ.get("CANVAS_URL", "https://canvas.instructure.com")
        access_token = os.environ.get("CANVAS_ACCESS_TOKEN")
        
        if not access_token:
            return False, "未找到 CANVAS_ACCESS_TOKEN 环境变量"
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{canvas_url}/api/v1/users/self",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    user_data = await response.json()
                    return True, f"已连接 - 用户: {user_data.get('name', '未知')}"
                else:
                    return False, f"连接失败 (状态码: {response.status})"
    except Exception as e:
        return False, f"连接错误: {str(e)}"


async def print_status():
    """打印系统状态"""
    console.print("\n[bold cyan]🔍 正在检查系统状态...[/bold cyan]")
    
    # 检查环境变量
    canvas_url = os.environ.get("CANVAS_URL", "未设置")
    canvas_token = "已设置 ✓" if os.environ.get("CANVAS_ACCESS_TOKEN") else "未设置 ✗"

    openai_key = "已设置 ✓" if os.environ.get("OPENAI_API_KEY") else "未设置 ✗"

    available_models = model_manager.list_models()
    if available_models:
        models_text = ", ".join(available_models)
    else:
        models_text = "未初始化"
    
    # 检查 Canvas 连接
    connected, message = await check_canvas_connection()
    canvas_status = f"[green]✓ {message}[/green]" if connected else f"[red]✗ {message}[/red]"
    
    status_text = f"""
    [bold cyan]📊 系统状态:[/bold cyan]
    
    [yellow]Canvas URL:[/yellow] {canvas_url}
    [yellow]Canvas Token:[/yellow] {canvas_token}
    [yellow]OpenAI API Key:[/yellow] {openai_key}
    [yellow]可用模型:[/yellow] {models_text}
    [yellow]Canvas 连接:[/yellow] {canvas_status}
    """
    
    console.print(Panel(status_text, title="系统状态", border_style="cyan"))


async def initialize_agent():
    """初始化 Canvas Student Agent"""
    try:
        console.print("\n[bold cyan]🚀 正在初始化 Canvas Student Agent...[/bold cyan]")
        
        # 检查必要的环境变量
        if not os.environ.get("CANVAS_ACCESS_TOKEN"):
            console.print("[bold red]错误: 未找到 CANVAS_ACCESS_TOKEN 环境变量[/bold red]")
            console.print("[yellow]请在 .env 文件中设置 CANVAS_ACCESS_TOKEN 和 CANVAS_URL[/yellow]")
            console.print("\n[cyan]如何获取 Canvas Access Token:[/cyan]")
            console.print("1. 登录到你的 Canvas 账户")
            console.print("2. 点击左侧菜单的 '账户' (Account)")
            console.print("3. 点击 '设置' (Settings)")
            console.print("4. 滚动到 '已批准的集成' (Approved Integrations)")
            console.print("5. 点击 '+ 新建访问令牌' (+ New Access Token)")
            console.print("6. 输入用途说明并生成令牌")
            console.print("7. 复制令牌并粘贴到 .env 文件中\n")
            return None
        
        # 初始化 logger (静默模式)
        log_dir = Path("workdir/canvas_chat")
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.init_logger(str(log_dir / "log.txt"))
        
        # 导入配置
        from configs.canvas_agent_config import agent_config
        
        # 初始化模型管理器
        model_manager.init_models()

        available_models = model_manager.list_models()
        console.print(
            f"[green]已注册 {len(available_models)} 个大模型: {', '.join(available_models) or '无'}[/green]"
        )

        # 获取模型
        try:
            model = model_manager.registed_models[agent_config["model_id"]]
        except KeyError:
            available = model_manager.list_models()
            console.print(
                f"[bold red]错误: 模型 {agent_config['model_id']} 未注册[/bold red]"
            )
            console.print(
                f"[yellow]当前可用模型: {', '.join(available) if available else '无'}[/yellow]"
            )
            console.print(
                "[cyan]请在 configs/canvas_agent_config.py 中更新 model_id 或检查环境变量配置[/cyan]"
            )
            return None
        
        # 准备 Agent 配置
        agent_build_config = dict(
            type=agent_config["type"],
            config=agent_config,
            model=model,
            tools=agent_config["tools"],
            max_steps=agent_config["max_steps"],
            name=agent_config.get("name"),
            description=agent_config.get("description"),
        )
        
        # 使用 Registry 创建 Agent
        agent = AGENT.build(agent_build_config)
        
        console.print(f"[bold green]✓ Agent 初始化成功！[/bold green]")
        console.print(f"[green]已加载 {len(agent_config['tools'])} 个 Canvas API 工具[/green]\n")
        
        return agent
        
    except Exception as e:
        console.print(f"[bold red]✗ Agent 初始化失败: {str(e)}[/bold red]")
        return None


async def process_query(agent, query: str):
    """处理用户查询"""
    try:
        console.print(f"\n[bold cyan]🤔 Agent 正在思考...[/bold cyan]")
        
        # 运行 Agent
        result = await agent.run(query)
        
        # 显示结果
        console.print("\n" + "="*70)
        console.print("[bold green]💡 回答:[/bold green]\n")
        console.print(Panel(str(result), border_style="green"))
        console.print("="*70 + "\n")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ 处理查询时出错: {str(e)}[/bold red]\n")


async def main():
    """主函数 - 交互式控制台"""
    
    # 打印欢迎信息
    print_banner()
    
    console.print("\n[cyan]正在启动...[/cyan]")
    
    # 初始化 Agent
    agent = await initialize_agent()
    
    if agent is None:
        console.print("[bold red]无法启动 Agent，程序退出[/bold red]")
        return
    
    # 显示帮助信息
    print_help()
    
    console.print("\n[bold green]✨ 准备就绪！开始对话吧！[/bold green]")
    console.print("[dim]提示: 输入 'help' 查看帮助，'exit' 退出程序[/dim]\n")
    
    # 主循环
    conversation_count = 0
    
    while True:
        try:
            # 获取用户输入
            user_input = Prompt.ask(
                "\n[bold cyan]You[/bold cyan]",
                default=""
            ).strip()
            
            # 处理空输入
            if not user_input:
                continue
            
            # 处理命令
            command = user_input.lower()
            
            if command in ["exit", "quit", "q"]:
                console.print("\n[bold cyan]👋 再见！祝学习愉快！[/bold cyan]\n")
                break
            
            elif command == "help":
                print_help()
                continue
            
            elif command == "examples":
                print_examples()
                continue
            
            elif command == "status":
                await print_status()
                continue
            
            elif command == "clear":
                os.system('cls' if os.name == 'nt' else 'clear')
                print_banner()
                continue
            
            # 处理正常查询
            conversation_count += 1
            await process_query(agent, user_input)
            
        except KeyboardInterrupt:
            console.print("\n\n[yellow]检测到 Ctrl+C[/yellow]")
            confirm = Prompt.ask(
                "[cyan]确定要退出吗?[/cyan]",
                choices=["y", "n"],
                default="n"
            )
            if confirm.lower() == "y":
                console.print("\n[bold cyan]👋 再见！祝学习愉快！[/bold cyan]\n")
                break
            else:
                continue
        
        except Exception as e:
            console.print(f"\n[bold red]发生错误: {str(e)}[/bold red]\n")
            continue
    
    # 显示统计信息
    if conversation_count > 0:
        console.print(f"\n[dim]本次会话共进行了 {conversation_count} 次对话[/dim]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        console.print(f"\n[bold red]程序异常退出: {str(e)}[/bold red]\n")
        sys.exit(1)

