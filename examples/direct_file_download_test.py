"""
Canvas 文件下载直接测试（不使用Agent）

直接调用 Canvas API 工具来测试文件下载功能，并将文件保存到本地 course 文件夹
"""

import os
import sys
import asyncio
import aiohttp
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, DownloadColumn, TransferSpeedColumn
from rich import print as rprint

# 导入 Canvas 工具
from src.tools.canvas_tools import (
    CanvasListCourses,
    CanvasGetFiles,
    CanvasGetFileInfo,
    CanvasDownloadFile,
    CanvasSearchFiles,
)

# 加载环境变量
load_dotenv()

console = Console()

# 下载文件夹路径
DOWNLOAD_FOLDER = Path(__file__).parent / "course"


def ensure_download_folder():
    """确保下载文件夹存在"""
    DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    return DOWNLOAD_FOLDER


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           Canvas 文件下载直接测试                             ║
║           Direct File Download Test                          ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")
    
    # 显示下载文件夹路径
    download_path = ensure_download_folder()
    console.print(f"📁 下载文件夹: {download_path.absolute()}", style="green")


async def test_list_courses():
    """测试：列出课程"""
    console.print("\n" + "="*60, style="cyan")
    console.print("📚 测试 1: 列出所有课程", style="cyan bold")
    console.print("="*60, style="cyan")
    
    tool = CanvasListCourses()
    result = await tool.forward()
    
    if result.error:
        console.print(f"❌ 错误: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def test_list_files(course_id: str):
    """测试：列出课程文件"""
    console.print("\n" + "="*60, style="cyan")
    console.print(f"📁 测试 2: 列出课程 {course_id} 的文件", style="cyan bold")
    console.print("="*60, style="cyan")
    
    tool = CanvasGetFiles()
    result = await tool.forward(course_id=course_id)
    
    if result.error:
        console.print(f"❌ 错误: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def test_get_file_info(file_id: str):
    """测试：获取文件信息"""
    console.print("\n" + "="*60, style="cyan")
    console.print(f"ℹ️  测试 3: 获取文件 {file_id} 的信息", style="cyan bold")
    console.print("="*60, style="cyan")
    
    tool = CanvasGetFileInfo()
    result = await tool.forward(file_id=file_id)
    
    if result.error:
        console.print(f"❌ 错误: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def download_file_to_disk(file_id: str, course_name: str = None):
    """下载文件并保存到本地磁盘"""
    console.print("\n" + "="*60, style="cyan")
    console.print(f"💾 下载文件到本地: {file_id}", style="cyan bold")
    console.print("="*60, style="cyan")
    
    try:
        # 使用 CanvasGetFileInfo 工具获取文件信息
        info_tool = CanvasGetFileInfo()
        info_result = await info_tool.forward(file_id=file_id)
        
        if info_result.error:
            console.print(f"❌ 错误: {info_result.error}", style="red")
            return None
        
        # 直接通过 API 获取文件完整信息（包含下载URL）
        canvas_url = os.getenv("CANVAS_URL")
        canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
        
        headers = {
            "Authorization": f"Bearer {canvas_token}",
            "Accept": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            # 获取文件信息
            async with session.get(
                f"{canvas_url}/api/v1/files/{file_id}",
                headers=headers
            ) as response:
                if response.status != 200:
                    console.print(f"❌ 获取文件信息失败 (状态码: {response.status})", style="red")
                    return None
                
                file_info = await response.json()
        
        file_url = file_info.get("url")
        file_name = file_info.get("display_name")
        file_size = file_info.get("size", 0)
        
        # 创建下载文件夹
        if course_name:
            # 清理课程名称中的非法字符
            safe_course_name = "".join(c for c in course_name if c.isalnum() or c in (' ', '-', '_')).strip()
            download_path = DOWNLOAD_FOLDER / safe_course_name
        else:
            download_path = DOWNLOAD_FOLDER
        
        download_path.mkdir(parents=True, exist_ok=True)
        
        # 完整的文件保存路径
        file_path = download_path / file_name
        
        console.print(f"📄 文件名: {file_name}", style="yellow")
        console.print(f"📦 大小: {file_size / (1024*1024):.2f} MB", style="yellow")
        console.print(f"💾 保存路径: {file_path.absolute()}", style="yellow")
        
        # 下载文件
        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console
        ) as progress:
            task = progress.add_task(f"[cyan]下载中...", total=file_size)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        with open(file_path, 'wb') as f:
                            downloaded = 0
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.update(task, completed=downloaded)
                        
                        console.print(f"✅ 文件下载成功！", style="green bold")
                        console.print(f"📍 保存位置: {file_path.absolute()}", style="green")
                        return file_path
                    else:
                        console.print(f"❌ 下载失败 (状态码: {response.status})", style="red")
                        return None
    
    except Exception as e:
        console.print(f"❌ 下载异常: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red")
        return None


async def test_download_file(file_id: str, read_content: bool = True):
    """测试：下载文件"""
    console.print("\n" + "="*60, style="cyan")
    console.print(f"📥 测试 4: 下载文件 {file_id}", style="cyan bold")
    console.print(f"   读取内容: {read_content}", style="cyan")
    console.print("="*60, style="cyan")
    
    tool = CanvasDownloadFile()
    result = await tool.forward(file_id=file_id, read_content=read_content)
    
    if result.error:
        console.print(f"❌ 错误: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def test_search_files(search_term: str):
    """测试：搜索文件"""
    console.print("\n" + "="*60, style="cyan")
    console.print(f"🔍 测试: 搜索关键词 '{search_term}'", style="cyan bold")
    console.print("="*60, style="cyan")
    
    tool = CanvasSearchFiles()
    result = await tool.forward(search_term=search_term)
    
    if result.error:
        console.print(f"❌ 错误: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def interactive_test():
    """交互式测试流程"""
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
        # 1. 列出课程
        await test_list_courses()
        
        # 2. 选择课程并列出文件
        course_id = console.input("\n请输入课程ID查看文件 (或回车跳过): ")
        
        if course_id.strip():
            await test_list_files(course_id.strip())
            
            # 3. 选择文件获取信息
            file_id = console.input("\n请输入文件ID获取详细信息 (或回车跳过): ")
            
            if file_id.strip():
                await test_get_file_info(file_id.strip())
                
                # 4. 下载文件
                download = console.input("\n下载选项: \n  1. 仅查看信息\n  2. 下载到本地磁盘\n  3. 在线读取内容\n请选择 (1/2/3): ")
                
                if download == '2':
                    # 下载到本地磁盘
                    course_name = console.input("输入课程名称(可选，用于分类保存，直接回车跳过): ")
                    await download_file_to_disk(file_id.strip(), course_name.strip() or None)
                elif download == '3':
                    # 在线读取内容
                    await test_download_file(file_id.strip(), read_content=True)
        
        # 5. 搜索文件
        console.print("\n" + "="*60, style="magenta")
        search = console.input("\n输入关键词搜索文件 (或回车跳过): ")
        
        if search.strip():
            result = await test_search_files(search.strip())
            
            if result and not result.error:
                file_id = console.input("\n请输入要下载的文件ID (或回车跳过): ")
                
                if file_id.strip():
                    download = console.input("\n下载选项: \n  1. 仅查看信息\n  2. 下载到本地磁盘\n  3. 在线读取内容\n请选择 (1/2/3): ")
                    
                    if download == '2':
                        course_name = console.input("输入课程名称(可选，用于分类保存，直接回车跳过): ")
                        await download_file_to_disk(file_id.strip(), course_name.strip() or None)
                    elif download == '3':
                        await test_download_file(file_id.strip(), read_content=True)
                    else:
                        await test_get_file_info(file_id.strip())
        
        # 测试完成
        console.print("\n" + "="*60, style="green")
        console.print("✅ 所有测试完成！", style="green bold")
        console.print("="*60, style="green")
        
    except Exception as e:
        console.print(f"\n❌ 错误: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red")


async def quick_test(file_id: str, download_to_disk: bool = False, course_name: str = None):
    """快速测试指定文件ID"""
    print_banner()
    
    console.print(f"\n🎯 快速测试 - 文件ID: {file_id}", style="cyan bold")
    
    # 检查环境变量
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
    
    if not canvas_url or not canvas_token:
        console.print("\n❌ 错误：未找到 Canvas 配置", style="red bold")
        return
    
    console.print(f"\n✓ Canvas URL: {canvas_url}", style="green")
    console.print(f"✓ Token 已配置", style="green")
    
    try:
        # 获取文件信息
        await test_get_file_info(file_id)
        
        if download_to_disk:
            # 下载文件到本地磁盘
            console.print("\n💾 下载文件到本地磁盘...", style="yellow")
            await download_file_to_disk(file_id, course_name)
        else:
            # 下载文件（仅获取链接）
            console.print("\n📎 获取下载链接...", style="yellow")
            await test_download_file(file_id, read_content=False)
            
            # 询问是否要下载到本地
            download = console.input("\n是否下载到本地磁盘? (y/n): ")
            if download.lower() == 'y':
                course_name_input = console.input("输入课程名称(可选，用于分类保存，直接回车跳过): ")
                await download_file_to_disk(file_id, course_name_input.strip() or None)
        
        console.print("\n✅ 测试完成！", style="green bold")
        
    except Exception as e:
        console.print(f"\n❌ 错误: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red")


def main():
    """主函数"""
    
    if len(sys.argv) > 1:
        # 快速测试模式
        # 用法1: python direct_file_download_test.py <file_id>
        # 用法2: python direct_file_download_test.py <file_id> --download
        # 用法3: python direct_file_download_test.py <file_id> --download --course "课程名"
        
        file_id = sys.argv[1]
        download_to_disk = '--download' in sys.argv or '-d' in sys.argv
        
        # 获取课程名称（如果提供）
        course_name = None
        if '--course' in sys.argv:
            try:
                course_idx = sys.argv.index('--course')
                if course_idx + 1 < len(sys.argv):
                    course_name = sys.argv[course_idx + 1]
            except:
                pass
        
        asyncio.run(quick_test(file_id, download_to_disk, course_name))
    else:
        # 交互式测试模式
        console.print("\n使用说明:", style="cyan bold")
        console.print("  交互模式: python direct_file_download_test.py", style="yellow")
        console.print("  快速模式: python direct_file_download_test.py <file_id>", style="yellow")
        console.print("  直接下载: python direct_file_download_test.py <file_id> --download", style="yellow")
        console.print("  分类下载: python direct_file_download_test.py <file_id> --download --course '课程名'", style="yellow")
        console.print()
        
        asyncio.run(interactive_test())


if __name__ == "__main__":
    main()

