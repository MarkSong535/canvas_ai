"""
Vector Store 搜索测试脚本

测试 OpenAI Vector Store 的搜索功能
"""

import os
import sys
from pathlib import Path
import json

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

# 加载环境变量
load_dotenv()

console = Console()

try:
    from openai import OpenAI
except ImportError:
    console.print("❌ 错误：未安装 openai 库", style="red bold")
    console.print("   安装命令: pip install openai", style="yellow")
    sys.exit(1)


def print_banner():
    """打印欢迎横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           Vector Store 搜索测试                               ║
║           Vector Store Search Test                           ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")


def load_vector_store_mapping():
    """加载 Vector Store 映射文件"""
    mapping_file = Path("file_index/vector_stores_mapping.json")
    
    if not mapping_file.exists():
        return None
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def list_vector_stores(client):
    """列出所有 Vector Stores"""
    try:
        response = client.vector_stores.list(limit=100)
        return list(response.data)
    except Exception as e:
        console.print(f"❌ 获取 Vector Stores 失败: {e}", style="red")
        return []


def search_vector_store(client, vector_store_id, query, max_results=5):
    """搜索 Vector Store"""
    try:
        response = client.vector_stores.search(
            vector_store_id=vector_store_id,
            query=query,
            max_num_results=max_results
        )
        return response
    except Exception as e:
        console.print(f"❌ 搜索失败: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red dim")
        return None


def display_search_results(results, query):
    """显示搜索结果"""
    if not results or not hasattr(results, 'data') or not results.data:
        console.print("\n⚠️  没有找到相关结果", style="yellow")
        return
    
    console.print(f"\n📊 搜索结果（查询: \"{query}\"）", style="green bold")
    console.print(f"找到 {len(results.data)} 个相关结果\n", style="green")
    
    for i, result in enumerate(results.data, 1):
        # 创建结果面板
        panel_content = []
        
        # 相关性分数
        if hasattr(result, 'score'):
            panel_content.append(f"📈 相关性分数: {result.score:.4f}")
        
        # 文件名
        if hasattr(result, 'filename'):
            panel_content.append(f"📄 文件: {result.filename}")
        
        # 元数据
        if hasattr(result, 'attributes') and result.attributes:
            panel_content.append(f"🏷️  属性: {result.attributes}")
        
        # 内容片段
        if hasattr(result, 'content'):
            content = result.content[:500] + "..." if len(result.content) > 500 else result.content
            panel_content.append(f"\n📝 内容片段:\n{content}")
        
        # 显示面板
        panel_text = "\n".join(panel_content)
        console.print(Panel(
            panel_text,
            title=f"[cyan bold]结果 {i}[/cyan bold]",
            border_style="cyan"
        ))
        console.print()


def main():
    """主函数"""
    
    print_banner()
    
    # 检查环境变量
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        console.print("❌ 错误：未找到 OPENAI_API_KEY", style="red bold")
        console.print("请在 .env 文件中配置 OPENAI_API_KEY", style="yellow")
        return
    
    console.print("✓ OpenAI API Key 已配置\n", style="green")
    
    # 创建 OpenAI 客户端
    try:
        client = OpenAI(
            api_key=openai_api_key,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
        console.print("✓ OpenAI 客户端已创建\n", style="green")
    except Exception as e:
        console.print(f"❌ 创建客户端失败: {e}", style="red")
        return
    
    # 加载映射文件
    mapping = load_vector_store_mapping()
    
    # 列出所有 Vector Stores
    console.print("📋 获取 Vector Stores 列表...\n", style="cyan bold")
    vector_stores = list_vector_stores(client)
    
    if not vector_stores:
        console.print("⚠️  未找到任何 Vector Store", style="yellow")
        console.print("请先运行 file_index_downloader.py --upload-only 创建 Vector Stores", style="dim")
        return
    
    # 显示 Vector Stores 表格
    table = Table(title="可用的 Vector Stores", show_header=True)
    table.add_column("#", style="cyan", width=5)
    table.add_column("ID", style="magenta", width=30)
    table.add_column("名称", style="green", width=40)
    table.add_column("文件数", style="yellow", justify="right")
    
    for i, vs in enumerate(vector_stores, 1):
        file_count = vs.file_counts.total if hasattr(vs, 'file_counts') else "N/A"
        table.add_row(
            str(i),
            vs.id,
            vs.name[:40] if vs.name else "未命名",
            str(file_count)
        )
    
    console.print(table)
    console.print()
    
    # 如果有映射文件，显示课程映射
    if mapping:
        console.print("📚 课程映射:", style="cyan bold")
        for course_name, info in mapping.items():
            console.print(f"  • {course_name}: {info.get('vector_store_id', 'N/A')}", style="dim")
        console.print()
    
    # 交互式搜索循环
    while True:
        # 选择 Vector Store
        try:
            choice = console.input("\n请选择 Vector Store 编号 (或按 q 退出): ")
            
            if choice.lower() == 'q':
                console.print("\n👋 再见！", style="cyan")
                break
            
            idx = int(choice) - 1
            if idx < 0 or idx >= len(vector_stores):
                console.print("⚠️  无效的编号", style="yellow")
                continue
            
            selected_vs = vector_stores[idx]
            console.print(f"\n✓ 已选择: {selected_vs.name}", style="green bold")
            console.print(f"  ID: {selected_vs.id}", style="dim")
            
            # 输入搜索查询
            while True:
                query = console.input("\n请输入搜索查询 (或按回车返回选择): ")
                
                if not query.strip():
                    break
                
                # 询问结果数量
                max_results_input = console.input("返回结果数量 (默认 5): ")
                try:
                    max_results = int(max_results_input) if max_results_input.strip() else 5
                except:
                    max_results = 5
                
                console.print(f"\n🔍 搜索中...", style="cyan")
                
                # 执行搜索
                results = search_vector_store(
                    client,
                    selected_vs.id,
                    query,
                    max_results
                )
                
                # 显示结果
                if results:
                    display_search_results(results, query)
                
                # 询问是否继续
                continue_search = console.input("\n继续在此 Vector Store 搜索? (y/n): ")
                if continue_search.lower() != 'y':
                    break
            
        except ValueError:
            console.print("⚠️  请输入有效的数字", style="yellow")
        except KeyboardInterrupt:
            console.print("\n\n👋 再见！", style="cyan")
            break
        except Exception as e:
            console.print(f"\n❌ 错误: {e}", style="red")
            import traceback
            console.print(traceback.format_exc(), style="red dim")


def quick_search(vector_store_id, query, max_results=5):
    """快速搜索（命令行模式）"""
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        console.print("❌ 错误：未找到 OPENAI_API_KEY", style="red bold")
        return
    
    try:
        client = OpenAI(
            api_key=openai_api_key,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
        
        console.print(f"🔍 搜索查询: {query}", style="cyan bold")
        console.print(f"   Vector Store: {vector_store_id}\n", style="dim")
        
        results = search_vector_store(client, vector_store_id, query, max_results)
        
        if results:
            display_search_results(results, query)
        
    except Exception as e:
        console.print(f"❌ 错误: {e}", style="red")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Vector Store 搜索测试工具"
    )
    parser.add_argument(
        "--vector-store-id",
        help="Vector Store ID（快速搜索模式）"
    )
    parser.add_argument(
        "--query",
        help="搜索查询（快速搜索模式）"
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="最大结果数量（默认 5）"
    )
    
    args = parser.parse_args()
    
    if args.vector_store_id and args.query:
        # 快速搜索模式
        quick_search(args.vector_store_id, args.query, args.max_results)
    else:
        # 交互式模式
        main()

