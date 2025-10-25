"""
Test Vector Store tool integration with the agent.

This script shows how an agent can perform searches through the Canvas Vector Store.
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# Load environment variables
load_dotenv()

console = Console()


def print_banner():
    """Render the welcome banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║     Test Vector Store Tools Integration                     ║
║     Test Vector Store Tools Integration                     ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")


async def test_vector_store_list():
    """List available Vector Stores."""
    from src.tools.canvas_tools import VectorStoreList
    
    console.print("\n" + "="*60, style="cyan")
    console.print("📋 Test 1: List Vector Stores", style="cyan bold")
    console.print("="*60, style="cyan")
    
    tool = VectorStoreList()
    result = await tool.forward()
    
    if result.error:
        console.print(f"❌ Error: {result.error}", style="red")
    else:
        console.print(result.output, style="green")
    
    return result


async def test_vector_store_search(vector_store_id: str = None):
    """Search within a Vector Store."""
    from src.tools.canvas_tools import VectorStoreSearch
    
    console.print("\n" + "="*60, style="cyan")
    console.print("🔍 Test 2: Search a Vector Store", style="cyan bold")
    console.print("="*60, style="cyan")
    
    # If no vector_store_id is provided, fetch the list first.
    if not vector_store_id:
        console.print("\n⚠️  Vector Store ID not provided, retrieving list", style="yellow")
        list_result = await test_vector_store_list()
        
        if list_result.error or not list_result.output:
            console.print("❌ Unable to retrieve the Vector Store list", style="red")
            return
        
        # Prompt the user for the Vector Store ID.
        vector_store_id = console.input("\nEnter a Vector Store ID: ")
    
    # Example queries.
    test_queries = [
        "What are the main topics covered in this course?",
        "Requirements for the first assignment",
        "Agent-Based Modeling"
    ]
    
    console.print(f"\n✓ 使用 Vector Store: {vector_store_id}", style="green")
    console.print("\n📝 Sample queries:", style="cyan bold")
    for i, query in enumerate(test_queries, 1):
        console.print(f"  {i}. {query}", style="dim")
    
    # Let the user choose a query.
    choice = console.input("\nSelect a query (1-3) or enter a custom query: ")
    
    if choice.isdigit() and 1 <= int(choice) <= len(test_queries):
        query = test_queries[int(choice) - 1]
    else:
        query = choice
    
    console.print(f"\n🔍 Search query: \"{query}\"", style="cyan")
    
    # Execute the search.
    tool = VectorStoreSearch()
    result = await tool.forward(
        vector_store_id=vector_store_id,
        query=query,
        max_results=3
    )
    
    if result.error:
        console.print(f"\n❌ Error: {result.error}", style="red")
    else:
        console.print(f"\n{result.output}", style="green")
    
    return result


async def test_with_agent():
    """Exercise the Vector Store tools through the agent."""
    console.print("\n" + "="*60, style="magenta")
    console.print("🤖 Test 3: Use tools through the agent", style="magenta bold")
    console.print("="*60, style="magenta")
    
    try:
        from configs.canvas_agent_config import canvas_student_agent_config
        from src.agent.general_agent.general_agent import GeneralAgent
        
        # Initialize the agent.
        console.print("\n🚀 Initializing Canvas Student Agent...", style="cyan")
        agent = GeneralAgent(**canvas_student_agent_config)
        console.print("✓ Agent initialized", style="green")
        
        # Example prompts.
        test_queries = [
            "List all available knowledge bases",
            "Search the knowledge base for Agent-Based Modeling",
            "What are the primary learning materials for this course?"
        ]
        
        console.print("\n📝 Available sample prompts:", style="cyan bold")
        for i, query in enumerate(test_queries, 1):
            console.print(f"  {i}. {query}", style="dim")
        
        # Let the user choose or enter a prompt.
        choice = console.input(
            "\nSelect a prompt (1-3) or enter a custom prompt (press q to exit): "
        )
        
        if choice.lower() == 'q':
            return
        
        if choice.isdigit() and 1 <= int(choice) <= len(test_queries):
            query = test_queries[int(choice) - 1]
        else:
            query = choice
        
        console.print(f"\n💬 User: {query}", style="blue bold")
        console.print("\n🤖 Agent processing...\n", style="cyan")
        
        # Execute the request.
        response = await agent.process_message(query)
        
        # Display the result.
        console.print(Panel(
            response,
            title="[green bold]Agent Response[/green bold]",
            border_style="green"
        ))
        
    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red dim")


async def main():
    """Entry point."""
    print_banner()
    
    # Check environment variables.
    openai_key = os.getenv("OPENAI_API_KEY")
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
    
    console.print("\n📋 Environment check:", style="cyan bold")
    console.print(f"  {'✓' if openai_key else '✗'} OPENAI_API_KEY", 
                  style="green" if openai_key else "red")
    console.print(f"  {'✓' if canvas_url else '✗'} CANVAS_URL", 
                  style="green" if canvas_url else "red")
    console.print(f"  {'✓' if canvas_token else '✗'} CANVAS_ACCESS_TOKEN", 
                  style="green" if canvas_token else "red")
    
    if not all([openai_key, canvas_url, canvas_token]):
        console.print("\n❌ Missing required environment variables", style="red bold")
        console.print("Please update the .env file with:", style="yellow")
        if not openai_key:
            console.print("  - OPENAI_API_KEY", style="yellow")
        if not canvas_url:
            console.print("  - CANVAS_URL", style="yellow")
        if not canvas_token:
            console.print("  - CANVAS_ACCESS_TOKEN", style="yellow")
        return
    
    console.print()
    
    # Main menu loop.
    while True:
        console.print("\n" + "="*60, style="cyan")
        console.print("📋 Test menu", style="cyan bold")
        console.print("="*60, style="cyan")
        console.print("  1. List all Vector Stores")
        console.print("  2. Search a Vector Store (call tool directly)")
        console.print("  3. Use the agent with tools (end-to-end)")
        console.print("  q. Quit")
        
        choice = console.input("\nChoose an option (1-3/q): ")
        
        if choice.lower() == 'q':
            console.print("\n👋 Goodbye!", style="cyan")
            break
        elif choice == '1':
            await test_vector_store_list()
        elif choice == '2':
            await test_vector_store_search()
        elif choice == '3':
            await test_with_agent()
        else:
            console.print("⚠️  Invalid choice", style="yellow")
        
        input("\nPress Enter to continue...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n\n👋 Goodbye!", style="cyan")
    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red dim")

