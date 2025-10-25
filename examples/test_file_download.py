"""
Canvas file download test example.

This script demonstrates how to use the Canvas Agent to download files:
1. List courses
2. Retrieve course files
3. Download a specific file
"""

import os
import sys
import asyncio
from pathlib import Path

# Add the project root to the module search path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# Import configuration
from configs.canvas_agent_config import canvas_student_agent_config
from src.registry import Registry

# Load environment variables
load_dotenv()

console = Console()


def print_banner():
    """Render the splash banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           Canvas File Download Test                          ║
║           File Download Test Example                         ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")


async def test_file_download():
    """Run the interactive file download workflow."""
    
    print_banner()
    
    # Validate required environment variables.
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
    
    if not canvas_url or not canvas_token:
        console.print("\n❌ Error: Canvas configuration not found", style="red bold")
        console.print("Please ensure the .env file includes:", style="yellow")
        console.print("  - CANVAS_URL", style="yellow")
        console.print("  - CANVAS_ACCESS_TOKEN", style="yellow")
        return
    
    console.print(f"\n✓ Canvas URL: {canvas_url}", style="green")
    console.print("✓ Access token configured", style="green")
    
    try:
        # Initialize the agent.
        console.print("\n[cyan]Initializing Canvas Agent...[/cyan]")
        registry = Registry()
        agent = registry.get_agent(canvas_student_agent_config)
        
        console.print("✓ Agent initialized", style="green bold")
        
        # ========================================
        # Test 1: List courses
        # ========================================
        console.print("\n" + "="*60, style="cyan")
        console.print("Test 1: List courses", style="cyan bold")
        console.print("="*60, style="cyan")
        
        query1 = "List all of my courses"
        console.print(f"\n💬 Query: {query1}", style="yellow")
        
        result1 = await agent.run(query1)
        console.print("\n📋 Result:", style="green bold")
        console.print(result1)
        
        # ========================================
        # Test 2: List files
        # ========================================
        console.print("\n" + "="*60, style="cyan")
        console.print("Test 2: List files", style="cyan bold")
        console.print("="*60, style="cyan")
        
        # Allow the user to choose a course.
        console.print("\nPlease review the course list above.", style="yellow")
        course_id = console.input("\nEnter a course ID to list files (leave blank to skip): ")
        
        if course_id.strip():
            query2 = f"List all files for course {course_id}"
            console.print(f"\n💬 Query: {query2}", style="yellow")
            
            result2 = await agent.run(query2)
            console.print("\n📁 File list:", style="green bold")
            console.print(result2)
            
            # ========================================
            # Test 3: Download a file
            # ========================================
            console.print("\n" + "="*60, style="cyan")
            console.print("Test 3: Download a file", style="cyan bold")
            console.print("="*60, style="cyan")
            
            file_id = console.input("\nEnter the file ID to download (leave blank to skip): ")
            
            if file_id.strip():
                query3 = f"Download file {file_id}"
                console.print(f"\n💬 Query: {query3}", style="yellow")
                
                result3 = await agent.run(query3)
                console.print("\n📥 Download result:", style="green bold")
                console.print(result3)
        else:
            console.print("\n⏩ File operations skipped", style="yellow")
        
        # ========================================
        # Test 4: Search files
        # ========================================
        console.print("\n" + "="*60, style="cyan")
        console.print("Test 4: Search files", style="cyan bold")
        console.print("="*60, style="cyan")
        
        search_term = console.input("\nEnter a search keyword (leave blank to skip): ")
        
        if search_term.strip():
            query4 = f"Search for files whose names include '{search_term}'"
            console.print(f"\n💬 Query: {query4}", style="yellow")
            
            result4 = await agent.run(query4)
            console.print("\n🔍 Search results:", style="green bold")
            console.print(result4)
            
            # Optionally download one of the matches.
            download_choice = console.input(
                "\nDownload one of the search results? Enter the file ID (leave blank to skip): "
            )
            
            if download_choice.strip():
                query5 = f"Download file {download_choice}"
                console.print(f"\n💬 Query: {query5}", style="yellow")
                
                result5 = await agent.run(query5)
                console.print("\n📥 Download result:", style="green bold")
                console.print(result5)
        else:
            console.print("\n⏩ Search test skipped", style="yellow")
        
        # ========================================
        # Complete
        # ========================================
        console.print("\n" + "="*60, style="green")
        console.print("✅ All tests complete!", style="green bold")
        console.print("="*60, style="green")
        
    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red")


async def quick_download_test(file_id: str):
    """Quick download test with a specified file ID."""
    
    print_banner()
    
    console.print(f"\n🎯 Quick download test - File ID: {file_id}", style="cyan bold")
    
    try:
        # Initialize the agent.
        console.print("\n[cyan]Initializing Canvas Agent...[/cyan]")
        registry = Registry()
        agent = registry.get_agent(canvas_student_agent_config)
        
        console.print("✓ Agent initialized", style="green bold")
        
        # Download the file.
        console.print("\n" + "="*60, style="cyan")
        console.print("Begin file download", style="cyan bold")
        console.print("="*60, style="cyan")
        
        query = f"Download file {file_id}"
        console.print(f"\n💬 Query: {query}", style="yellow")
        
        result = await agent.run(query)
        console.print("\n📥 Download result:", style="green bold")
        console.print(result)
        
        console.print("\n" + "="*60, style="green")
        console.print("✅ Test complete!", style="green bold")
        console.print("="*60, style="green")
        
    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red")


def main():
    """Entry point."""
    
    # Check command-line arguments.
    if len(sys.argv) > 1:
        # Quick download mode: python test_file_download.py <file_id>
        file_id = sys.argv[1]
        asyncio.run(quick_download_test(file_id))
    else:
        # Interactive test mode.
        asyncio.run(test_file_download())


if __name__ == "__main__":
    main()

