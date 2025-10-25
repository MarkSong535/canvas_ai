"""
Canvas Student Agent interactive console.

Offers a command-line chat experience so students can talk to the Canvas Agent in natural language.
"""

import subprocess
import sys
import importlib


def check_and_install_dependencies():
    """Check for required packages and install any missing dependencies."""
    
    # Complete dependency list
    required_packages = {
        # Core dependencies
        'asyncio': None,  # Part of the Python standard library
        'aiohttp': 'aiohttp>=3.9.0',
        'dotenv': 'python-dotenv>=1.0.0',
        'rich': 'rich>=13.0.0',
        'openai': 'openai>=1.0.0',
        'pydantic': 'pydantic>=2.0.0',
        'jinja2': 'jinja2>=3.0.0',
        'yaml': 'pyyaml>=6.0.0',
        
        # Configuration and logging
        'mmengine': 'mmengine>=0.10.0',
        'huggingface_hub': 'huggingface-hub>=0.19.0',
        
        # Document processing
        'markitdown': 'markitdown',
        
        # Additional optional dependencies
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
    
    print("🔍 Checking dependencies...\n")
    
    for module_name, package_name in required_packages.items():
        if package_name is None:  # Skip modules that are part of the standard library
            continue
            
        try:
            importlib.import_module(module_name)
            print(f"  ✓ {module_name}")
            installed_count += 1
        except ImportError:
            print(f"  ✗ {module_name} (needs installation)")
            missing_packages.append(package_name)

    print(f"\nInstalled: {installed_count}/{len([p for p in required_packages.values() if p is not None])}")
    
    if missing_packages:
        print(f"\n📦 Found {len(missing_packages)} missing dependencies")
        
        # Ask the user before attempting automatic installation
        try:
            response = input("\nInstall the missing dependencies automatically? [Y/n]: ").strip().lower()
            if response and response not in ['y', 'yes']:
                print("\n⚠️  Skipping automatic installation")
                print("Run `pip install -r requirements.txt` manually if needed.")
                return False
        except (KeyboardInterrupt, EOFError):
            print("\n\n⚠️  Skipping automatic installation")
            return False
        
        print("\nInstalling missing dependencies...")
        print("=" * 60)
        
        failed_packages = []
        
        for package in missing_packages:
            try:
                print(f"\n📦 Installing {package}...", end=" ")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", package, "-q", "--upgrade"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                
                if result.returncode == 0:
                    print("✓ Success")
                else:
                    print("✗ Failed")
                    if result.stderr:
                        print(f"   Error: {result.stderr[:200]}")
                    failed_packages.append(package)
                    
            except subprocess.TimeoutExpired:
                print("✗ Timed out")
                failed_packages.append(package)
            except Exception as e:
                print(f"✗ Error: {str(e)}")
                failed_packages.append(package)
        
        print("\n" + "=" * 60)
        
        if failed_packages:
            print(f"\n⚠️  {len(failed_packages)} packages failed to install:")
            for pkg in failed_packages:
                print(f"   - {pkg}")
            print("\nRun the following command manually:")
            print(f"   pip install {' '.join(failed_packages)}")
            
            # Confirm whether execution should continue
            try:
                response = input("\nContinue running the program anyway? [y/N]: ").strip().lower()
                if response not in ['y', 'yes']:
                    return False
            except (KeyboardInterrupt, EOFError):
                return False
        else:
            print("\n✅ All dependencies installed successfully!")
    else:
        print("\n✅ All dependencies are already satisfied!")
    
    return True


# Check and install dependencies before importing other project modules
if __name__ == "__main__":
    if not check_and_install_dependencies():
        print("\n⚠️  Dependency installation failed; the program cannot continue")
        print("Please run `pip install -r requirements.txt` manually.")
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

# Load environment variables
load_dotenv()

from src.models import model_manager
from src.registry import AGENT
from src.logger import logger


console = Console()


def print_banner():
    """Render the welcome banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🎓 Canvas Student Agent Interactive Console 🎓    ║
    ║                                                           ║
    ║           Your Canvas LMS study companion                ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold cyan")


def print_help():
    """Display help text."""
    help_text = """
    [bold cyan]📖 Available commands:[/bold cyan]

    [yellow]help[/yellow]     - Show this guide
    [yellow]clear[/yellow]    - Clear the terminal window
    [yellow]examples[/yellow] - Show sample prompts
    [yellow]status[/yellow]   - Check Canvas connectivity
    [yellow]exit[/yellow]     - Quit the program
    [yellow]quit[/yellow]     - Quit the program

    [bold cyan]💬 How to use:[/bold cyan]

    Type a question or instruction and the agent will handle it. For example:
    - "List all of my courses"
    - "Show my to-do items"
    - "Get the assignments for Calculus"
    - "What events are happening today?"
    - "Show the latest announcements"
    """
    console.print(Panel(help_text, title="Help", border_style="green"))


def print_examples():
    """Display sample prompts."""
    examples_text = """
    [bold cyan]📝 Sample prompts:[/bold cyan]

    [bold yellow]📚 Courses:[/bold yellow]
    - List every course I am enrolled in
    - Show the details for course 123
    - Outline the module structure for Calculus

    [bold yellow]📝 Assignments:[/bold yellow]
    - Show all assignments on my to-do list
    - Get the assignments for course 123
    - Submit assignment 456 with URL: https://example.com

    [bold yellow]📅 Schedule:[/bold yellow]
    - What is on my calendar today?
    - Show this week’s calendar events
    - List upcoming events

    [bold yellow]💬 Discussions:[/bold yellow]
    - Show the discussions for course 456
    - Reply to discussion 123: I agree with this point

    [bold yellow]📊 Grades:[/bold yellow]
    - Show my grades in course 789
    - Display all of my grades

    [bold yellow]📢 Announcements:[/bold yellow]
    - Show the latest announcements
    - Get announcements across all courses

    [bold yellow]📄 Files and resources:[/bold yellow]
    - List every file in course 456
    - Search the course for PDF files
    - Show the course page list
    """
    console.print(Panel(examples_text, title="Sample Prompts", border_style="blue"))


async def check_canvas_connection():
    """Check whether the Canvas API can be reached."""
    try:
        import aiohttp
        canvas_url = os.environ.get("CANVAS_URL", "https://canvas.instructure.com")
        access_token = os.environ.get("CANVAS_ACCESS_TOKEN")
        
        if not access_token:
            return False, "Missing CANVAS_ACCESS_TOKEN environment variable"
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{canvas_url}/api/v1/users/self",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    user_data = await response.json()
                    return True, f"Connected as {user_data.get('name', 'Unknown')}"
                else:
                    return False, f"Connection failed (status code {response.status})"
    except Exception as e:
        return False, f"Connection error: {str(e)}"


async def print_status():
    """Print the current system status."""
    console.print("\n[bold cyan]🔍 Checking system status...[/bold cyan]")
    
    # Inspect environment variables
    canvas_url = os.environ.get("CANVAS_URL", "Not configured")
    canvas_token = "Configured ✓" if os.environ.get("CANVAS_ACCESS_TOKEN") else "Missing ✗"

    openai_key = "Configured ✓" if os.environ.get("OPENAI_API_KEY") else "Missing ✗"

    available_models = model_manager.list_models()
    if available_models:
        models_text = ", ".join(available_models)
    else:
        models_text = "Not initialized"
    
    # Check Canvas connectivity
    connected, message = await check_canvas_connection()
    canvas_status = f"[green]✓ {message}[/green]" if connected else f"[red]✗ {message}[/red]"

    status_text = f"""
    [bold cyan]📊 System status:[/bold cyan]

    [yellow]Canvas URL:[/yellow] {canvas_url}
    [yellow]Canvas Token:[/yellow] {canvas_token}
    [yellow]OpenAI API Key:[/yellow] {openai_key}
    [yellow]Registered Models:[/yellow] {models_text}
    [yellow]Canvas Connectivity:[/yellow] {canvas_status}
    """

    console.print(Panel(status_text, title="System Status", border_style="cyan"))


async def initialize_agent():
    """Initialize the Canvas Student Agent."""
    try:
        console.print("\n[bold cyan]🚀 Initializing the Canvas Student Agent...[/bold cyan]")
        
    # Verify essential environment variables
        if not os.environ.get("CANVAS_ACCESS_TOKEN"):
            console.print("[bold red]Error: CANVAS_ACCESS_TOKEN is not configured[/bold red]")
            console.print("[yellow]Set CANVAS_ACCESS_TOKEN and CANVAS_URL in your .env file.[/yellow]")
            console.print("\n[cyan]How to generate a Canvas access token:[/cyan]")
            console.print("1. Sign in to your Canvas account")
            console.print("2. Open the 'Account' menu on the left")
            console.print("3. Choose 'Settings'")
            console.print("4. Scroll to 'Approved Integrations'")
            console.print("5. Click '+ New Access Token'")
            console.print("6. Describe the purpose and generate the token")
            console.print("7. Copy the token and add it to your .env file\n")
            return None
        
    # Initialize the logger in quiet mode
        log_dir = Path("workdir/canvas_chat")
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.init_logger(str(log_dir / "log.txt"))
        
    # Import the agent configuration
        from configs.canvas_agent_config import agent_config
        
    # Initialize the model manager
        model_manager.init_models()

        available_models = model_manager.list_models()
        console.print(
            f"[green]Registered {len(available_models)} models: {', '.join(available_models) or 'None'}[/green]"
        )

    # Retrieve the configured model
        try:
            model = model_manager.registed_models[agent_config["model_id"]]
        except KeyError:
            available = model_manager.list_models()
            console.print(
                f"[bold red]Error: model '{agent_config['model_id']}' is not registered[/bold red]"
            )
            console.print(
                f"[yellow]Available models: {', '.join(available) if available else 'None'}[/yellow]"
            )
            console.print(
                "[cyan]Update `model_id` in configs/canvas_agent_config.py or verify your environment variables.[/cyan]"
            )
            return None
        
    # Prepare the agent configuration
        agent_build_config = dict(
            type=agent_config["type"],
            config=agent_config,
            model=model,
            tools=agent_config["tools"],
            max_steps=agent_config["max_steps"],
            name=agent_config.get("name"),
            description=agent_config.get("description"),
        )
        
    # Build the agent via the registry
        agent = AGENT.build(agent_build_config)
        
        console.print(f"[bold green]✓ Agent initialized successfully![/bold green]")
        console.print(f"[green]Loaded {len(agent_config['tools'])} Canvas API tools[/green]\n")
        
        return agent
        
    except Exception as e:
        console.print(f"[bold red]✗ Failed to initialize the agent: {str(e)}[/bold red]")
        return None


async def process_query(agent, query: str):
    """Handle a single user query."""
    try:
        console.print("\n[bold cyan]🤔 The agent is thinking...[/bold cyan]")
        
    # Execute the agent
        result = await agent.run(query)
        
    # Display the result
        console.print("\n" + "=" * 70)
        console.print("[bold green]💡 Answer:[/bold green]\n")
        console.print(Panel(str(result), border_style="green"))
        console.print("=" * 70 + "\n")
        
    except Exception as e:
        console.print(f"\n[bold red]✗ Error while processing the query: {str(e)}[/bold red]\n")


async def main():
    """Entry point for the interactive console."""
    
    # Print the welcome banner
    print_banner()
    
    console.print("\n[cyan]Starting up...[/cyan]")
    
    # Initialize the agent
    agent = await initialize_agent()
    
    if agent is None:
        console.print("[bold red]Unable to start the agent; exiting.[/bold red]")
        return
    
    # Show help message
    print_help()
    
    console.print("\n[bold green]✨ Ready! Start chatting whenever you are.[/bold green]")
    console.print("[dim]Tip: type 'help' for guidance or 'exit' to quit.[/dim]\n")
    
    # Main interaction loop
    conversation_count = 0
    
    while True:
        try:
            # Read user input
            user_input = Prompt.ask(
                "\n[bold cyan]You[/bold cyan]",
                default=""
            ).strip()
            
            # Skip empty submissions
            if not user_input:
                continue
            
            # Handle commands
            command = user_input.lower()
            
            if command in ["exit", "quit", "q"]:
                console.print("\n[bold cyan]👋 Goodbye! Happy studying![/bold cyan]\n")
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
            
            # Handle standard queries
            conversation_count += 1
            await process_query(agent, user_input)
            
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Detected Ctrl+C[/yellow]")
            confirm = Prompt.ask(
                "[cyan]Do you want to exit?[/cyan]",
                choices=["y", "n"],
                default="n"
            )
            if confirm.lower() == "y":
                console.print("\n[bold cyan]👋 Goodbye! Happy studying![/bold cyan]\n")
                break
            else:
                continue
        
        except Exception as e:
            console.print(f"\n[bold red]An error occurred: {str(e)}[/bold red]\n")
            continue
    
    # Display session statistics
    if conversation_count > 0:
        console.print(f"\n[dim]This session included {conversation_count} exchanges.[/dim]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        console.print(f"\n[bold red]Application exited with an error: {str(e)}[/bold red]\n")
        sys.exit(1)

