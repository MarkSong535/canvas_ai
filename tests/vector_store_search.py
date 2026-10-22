"""
Vector Store search test script (manual, interactive; not collected by pytest)

Tests the search functionality of OpenAI Vector Stores. Calls the OpenAI API, so it needs OPENAI_API_KEY.
Run from anywhere: python tests/manual/vector_store_search.py [--help]
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

ROOT = Path(__file__).resolve().parents[1]

# Load environment variables from the project's .env
load_dotenv(ROOT / ".env")

console = Console()

try:
    from openai import OpenAI
except ImportError:
    console.print("❌ Error: openai library is not installed", style="red bold")
    console.print("   Install with: pip install openai", style="yellow")
    sys.exit(1)


def print_banner():
    """Print the welcome banner"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           Vector Store Search Test                           ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")


def load_vector_store_mapping():
    """Load the Vector Store mapping file"""
    mapping_file = ROOT / "file_index" / "vector_stores_mapping.json"
    
    if not mapping_file.exists():
        return None
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def list_vector_stores(client):
    """List all Vector Stores"""
    try:
        response = client.vector_stores.list(limit=100)
        return list(response.data)
    except Exception as e:
        console.print(f"❌ Failed to fetch Vector Stores: {e}", style="red")
        return []


def search_vector_store(client, vector_store_id, query, max_results=5):
    """Search a Vector Store"""
    try:
        response = client.vector_stores.search(
            vector_store_id=vector_store_id,
            query=query,
            max_num_results=max_results
        )
        return response
    except Exception as e:
        console.print(f"❌ Search failed: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red dim")
        return None


def display_search_results(results, query):
    """Display search results"""
    if not results or not hasattr(results, 'data') or not results.data:
        console.print("\n⚠️  No relevant results found", style="yellow")
        return
    
    console.print(f"\n📊 Search results (query: \"{query}\")", style="green bold")
    console.print(f"Found {len(results.data)} relevant results\n", style="green")
    
    for i, result in enumerate(results.data, 1):
        # Build the result panel
        panel_content = []
        
        # Relevance score
        if hasattr(result, 'score'):
            panel_content.append(f"📈 Relevance score: {result.score:.4f}")
        
        # File name
        if hasattr(result, 'filename'):
            panel_content.append(f"📄 File: {result.filename}")
        
        # Metadata
        if hasattr(result, 'attributes') and result.attributes:
            panel_content.append(f"🏷️  Attributes: {result.attributes}")
        
        # Content snippet
        if hasattr(result, 'content'):
            content = result.content[:500] + "..." if len(result.content) > 500 else result.content
            panel_content.append(f"\n📝 Content snippet:\n{content}")
        
        # Display the panel
        panel_text = "\n".join(panel_content)
        console.print(Panel(
            panel_text,
            title=f"[cyan bold]Result {i}[/cyan bold]",
            border_style="cyan"
        ))
        console.print()


def main():
    """Main function"""
    
    print_banner()
    
    # Check environment variables
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_api_key:
        console.print("❌ Error: OPENAI_API_KEY not found", style="red bold")
        console.print("Please set OPENAI_API_KEY in your .env file", style="yellow")
        return
    
    console.print("✓ OpenAI API Key is configured\n", style="green")
    
    # Create the OpenAI client
    try:
        client = OpenAI(
            api_key=openai_api_key,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
        console.print("✓ OpenAI client created\n", style="green")
    except Exception as e:
        console.print(f"❌ Failed to create client: {e}", style="red")
        return
    
    # Load the mapping file
    mapping = load_vector_store_mapping()
    
    # List all Vector Stores
    console.print("📋 Fetching Vector Stores list...\n", style="cyan bold")
    vector_stores = list_vector_stores(client)
    
    if not vector_stores:
        console.print("⚠️  No Vector Stores found", style="yellow")
        console.print("Run file_index_downloader.py --upload-only first to create Vector Stores", style="dim")
        return
    
    # Display the Vector Stores table
    table = Table(title="Available Vector Stores", show_header=True)
    table.add_column("#", style="cyan", width=5)
    table.add_column("ID", style="magenta", width=30)
    table.add_column("Name", style="green", width=40)
    table.add_column("Files", style="yellow", justify="right")
    
    for i, vs in enumerate(vector_stores, 1):
        file_count = vs.file_counts.total if hasattr(vs, 'file_counts') else "N/A"
        table.add_row(
            str(i),
            vs.id,
            vs.name[:40] if vs.name else "Unnamed",
            str(file_count)
        )
    
    console.print(table)
    console.print()
    
    # If a mapping file exists, show the course mapping
    if mapping:
        console.print("📚 Course mapping:", style="cyan bold")
        for course_name, info in mapping.items():
            console.print(f"  • {course_name}: {info.get('vector_store_id', 'N/A')}", style="dim")
        console.print()
    
    # Interactive search loop
    while True:
        # Select a Vector Store
        try:
            choice = console.input("\nSelect a Vector Store number (or press q to quit): ")
            
            if choice.lower() == 'q':
                console.print("\n👋 Goodbye!", style="cyan")
                break
            
            idx = int(choice) - 1
            if idx < 0 or idx >= len(vector_stores):
                console.print("⚠️  Invalid number", style="yellow")
                continue
            
            selected_vs = vector_stores[idx]
            console.print(f"\n✓ Selected: {selected_vs.name}", style="green bold")
            console.print(f"  ID: {selected_vs.id}", style="dim")
            
            # Enter a search query
            while True:
                query = console.input("\nEnter a search query (or press Enter to go back): ")
                
                if not query.strip():
                    break
                
                # Ask for the number of results
                max_results_input = console.input("Number of results (default 5): ")
                try:
                    max_results = int(max_results_input) if max_results_input.strip() else 5
                except:
                    max_results = 5
                
                console.print(f"\n🔍 Searching...", style="cyan")
                
                # Run the search
                results = search_vector_store(
                    client,
                    selected_vs.id,
                    query,
                    max_results
                )
                
                # Display results
                if results:
                    display_search_results(results, query)
                
                # Ask whether to continue
                continue_search = console.input("\nContinue searching this Vector Store? (y/n): ")
                if continue_search.lower() != 'y':
                    break
            
        except ValueError:
            console.print("⚠️  Please enter a valid number", style="yellow")
        except KeyboardInterrupt:
            console.print("\n\n👋 Goodbye!", style="cyan")
            break
        except Exception as e:
            console.print(f"\n❌ Error: {e}", style="red")
            import traceback
            console.print(traceback.format_exc(), style="red dim")


def quick_search(vector_store_id, query, max_results=5):
    """Quick search (command-line mode)"""
    
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        console.print("❌ Error: OPENAI_API_KEY not found", style="red bold")
        return
    
    try:
        client = OpenAI(
            api_key=openai_api_key,
            default_headers={"OpenAI-Beta": "assistants=v2"}
        )
        
        console.print(f"🔍 Search query: {query}", style="cyan bold")
        console.print(f"   Vector Store: {vector_store_id}\n", style="dim")
        
        results = search_vector_store(client, vector_store_id, query, max_results)
        
        if results:
            display_search_results(results, query)
        
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Vector Store search test tool"
    )
    parser.add_argument(
        "--vector-store-id",
        help="Vector Store ID (quick search mode)"
    )
    parser.add_argument(
        "--query",
        help="Search query (quick search mode)"
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum number of results (default 5)"
    )
    
    args = parser.parse_args()
    
    if args.vector_store_id and args.query:
        # Quick search mode
        quick_search(args.vector_store_id, args.query, args.max_results)
    else:
        # Interactive mode
        main()

