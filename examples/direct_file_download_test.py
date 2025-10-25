"""
Direct Canvas file download tests (agent-free).

Invokes the Canvas API tools directly to validate file downloads and save artifacts to the local course folder.
"""

import os
import sys
import asyncio
import aiohttp
from pathlib import Path

# Add the repository root to the module search path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, DownloadColumn, TransferSpeedColumn
from rich import print as rprint

# Import Canvas tools
from src.tools.canvas_tools import (
    CanvasListCourses,
    CanvasGetFiles,
    CanvasGetFileInfo,
    CanvasDownloadFile,
    CanvasSearchFiles,
)

# Load environment variables
load_dotenv()

console = Console()

# Target directory for downloaded files
DOWNLOAD_FOLDER = Path(__file__).parent / "course"


def ensure_download_folder():
    """Ensure the download folder exists."""
    DOWNLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    return DOWNLOAD_FOLDER


def print_banner():
    """Render the console banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║           Canvas Direct File Download Test                   ║
╚══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan bold")
    
    # Show the download folder path
    download_path = ensure_download_folder()
    console.print(f"📁 Download folder: {download_path.absolute()}", style="green")


async def test_list_courses():
    """Test helper: list Canvas courses."""
    console.print("\n" + "=" * 60, style="cyan")
    console.print("📚 Test 1: List all courses", style="cyan bold")
    console.print("=" * 60, style="cyan")
    
    tool = CanvasListCourses()
    result = await tool.forward()
    
    if result.error:
        console.print(f"❌ Error: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def test_list_files(course_id: str):
    """Test helper: list files for a course."""
    console.print("\n" + "=" * 60, style="cyan")
    console.print(f"📁 Test 2: List files for course {course_id}", style="cyan bold")
    console.print("=" * 60, style="cyan")
    
    tool = CanvasGetFiles()
    result = await tool.forward(course_id=course_id)
    
    if result.error:
        console.print(f"❌ Error: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def test_get_file_info(file_id: str):
    """Test helper: fetch file metadata."""
    console.print("\n" + "=" * 60, style="cyan")
    console.print(f"ℹ️  Test 3: Fetch metadata for file {file_id}", style="cyan bold")
    console.print("=" * 60, style="cyan")
    
    tool = CanvasGetFileInfo()
    result = await tool.forward(file_id=file_id)
    
    if result.error:
        console.print(f"❌ Error: {result.error}", style="red")
        return None
    
    console.print(result.output, style="green")
    return result


async def download_file_to_disk(file_id: str, course_name: str = None):
    """Download a file and save it to the local filesystem."""
    console.print("\n" + "=" * 60, style="cyan")
    console.print(f"💾 Download file to local disk: {file_id}", style="cyan bold")
    console.print("=" * 60, style="cyan")

    try:
        # Retrieve file information via the Canvas tool.
        info_tool = CanvasGetFileInfo()
        info_result = await info_tool.forward(file_id=file_id)

        if info_result.error:
            console.print(f"❌ Error: {info_result.error}", style="red")
            return None

        # Query the Canvas API directly to get the download URL.
        canvas_url = os.getenv("CANVAS_URL")
        canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")

        headers = {
            "Authorization": f"Bearer {canvas_token}",
            "Accept": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{canvas_url}/api/v1/files/{file_id}",
                headers=headers,
            ) as response:
                if response.status != 200:
                    console.print(
                        f"❌ Failed to retrieve file info (status: {response.status})",
                        style="red",
                    )
                    return None

                file_info = await response.json()

        file_url = file_info.get("url")
        file_name = file_info.get("display_name")
        file_size = file_info.get("size", 0)

        # Create the target download directory.
        if course_name:
            safe_course_name = "".join(
                c for c in course_name if c.isalnum() or c in (" ", "-", "_")
            ).strip()
            download_path = DOWNLOAD_FOLDER / safe_course_name
        else:
            download_path = DOWNLOAD_FOLDER

        download_path.mkdir(parents=True, exist_ok=True)

        # Compose the final file path.
        file_path = download_path / file_name

        console.print(f"📄 File name: {file_name}", style="yellow")
        console.print(f"📦 Size: {file_size / (1024 * 1024):.2f} MB", style="yellow")
        console.print(f"💾 Saving to: {file_path.absolute()}", style="yellow")

        # Stream the file to disk with a progress bar.
        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Downloading...", total=file_size)

            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        with open(file_path, "wb") as f:
                            downloaded = 0
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress.update(task, completed=downloaded)

                        console.print("✅ File downloaded successfully!", style="green bold")
                        console.print(f"📍 Saved at: {file_path.absolute()}", style="green")
                        return file_path
                    else:
                        console.print(
                            f"❌ Download failed (status: {response.status})",
                            style="red",
                        )
                        return None

    except Exception as e:
        console.print(f"❌ Download error: {e}", style="red")
        import traceback

        console.print(traceback.format_exc(), style="red")
        return None


async def test_download_file(file_id: str, read_content: bool = True):
    """Test helper: download file content or shareable link."""
    console.print("\n" + "=" * 60, style="cyan")
    console.print(f"📥 Test 4: Download file {file_id}", style="cyan bold")
    console.print(f"   Read content: {read_content}", style="cyan")
    console.print("=" * 60, style="cyan")

    tool = CanvasDownloadFile()
    result = await tool.forward(file_id=file_id, read_content=read_content)

    if result.error:
        console.print(f"❌ Error: {result.error}", style="red")
        return None

    console.print(result.output, style="green")
    return result


async def test_search_files(search_term: str):
    """Test helper: search files by keyword."""
    console.print("\n" + "=" * 60, style="cyan")
    console.print(f"🔍 Test: Search keyword '{search_term}'", style="cyan bold")
    console.print("=" * 60, style="cyan")

    tool = CanvasSearchFiles()
    result = await tool.forward(search_term=search_term)

    if result.error:
        console.print(f"❌ Error: {result.error}", style="red")
        return None

    console.print(result.output, style="green")
    return result


async def interactive_test():
    """Interactive test workflow."""
    print_banner()

    # Validate environment variables.
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
        # 1. List courses.
        await test_list_courses()

        # 2. Select a course and list its files.
        course_id = console.input("\nEnter course ID to view files (leave blank to skip): ")

        if course_id.strip():
            await test_list_files(course_id.strip())

            # 3. Select a file for more details.
            file_id = console.input(
                "\nEnter file ID for detailed info (leave blank to skip): "
            )

            if file_id.strip():
                await test_get_file_info(file_id.strip())

                # 4. Decide how to handle the file.
                download = console.input(
                    "\nDownload options: \n"
                    "  1. View metadata only\n"
                    "  2. Download to local disk\n"
                    "  3. Read content online\n"
                    "Choose (1/2/3): "
                )

                if download == "2":
                    course_name = console.input(
                        "Enter course name (optional, used for folder name; leave blank to skip): "
                    )
                    await download_file_to_disk(
                        file_id.strip(), course_name.strip() or None
                    )
                elif download == "3":
                    await test_download_file(file_id.strip(), read_content=True)

        # 5. Search files.
        console.print("\n" + "=" * 60, style="magenta")
        search = console.input(
            "\nEnter a keyword to search files (leave blank to skip): "
        )

        if search.strip():
            result = await test_search_files(search.strip())

            if result and not result.error:
                file_id = console.input(
                    "\nEnter the file ID to download (leave blank to skip): "
                )

                if file_id.strip():
                    download = console.input(
                        "\nDownload options: \n"
                        "  1. View metadata only\n"
                        "  2. Download to local disk\n"
                        "  3. Read content online\n"
                        "Choose (1/2/3): "
                    )

                    if download == "2":
                        course_name = console.input(
                            "Enter course name (optional, used for folder name; leave blank to skip): "
                        )
                        await download_file_to_disk(
                            file_id.strip(), course_name.strip() or None
                        )
                    elif download == "3":
                        await test_download_file(file_id.strip(), read_content=True)
                    else:
                        await test_get_file_info(file_id.strip())

        # Completion message.
        console.print("\n" + "=" * 60, style="green")
        console.print("✅ All tests complete!", style="green bold")
        console.print("=" * 60, style="green")

    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red bold")
        import traceback

        console.print(traceback.format_exc(), style="red")


async def quick_test(file_id: str, download_to_disk: bool = False, course_name: str = None):
    """Quick test for a specific file ID."""
    print_banner()

    console.print(f"\n🎯 Quick test - File ID: {file_id}", style="cyan bold")

    # Validate environment variables.
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")

    if not canvas_url or not canvas_token:
        console.print("\n❌ Error: Canvas configuration not found", style="red bold")
        return

    console.print(f"\n✓ Canvas URL: {canvas_url}", style="green")
    console.print("✓ Access token configured", style="green")

    try:
        # Fetch metadata for the file.
        await test_get_file_info(file_id)

        if download_to_disk:
            console.print("\n💾 Downloading file to local disk...", style="yellow")
            await download_file_to_disk(file_id, course_name)
        else:
            console.print("\n📎 Fetching download link...", style="yellow")
            await test_download_file(file_id, read_content=False)

            download = console.input(
                "\nDownload to local disk? (y/n): "
            )
            if download.lower() == "y":
                course_name_input = console.input(
                    "Enter course name (optional, used for folder name; leave blank to skip): "
                )
                await download_file_to_disk(file_id, course_name_input.strip() or None)

        console.print("\n✅ Test complete!", style="green bold")

    except Exception as e:
        console.print(f"\n❌ Error: {e}", style="red bold")
        import traceback

        console.print(traceback.format_exc(), style="red")


def main():
    """Script entry point."""

    if len(sys.argv) > 1:
        # Quick-test mode.
        # Usage 1: python direct_file_download_test.py <file_id>
        # Usage 2: python direct_file_download_test.py <file_id> --download
        # Usage 3: python direct_file_download_test.py <file_id> --download --course "Course Name"

        file_id = sys.argv[1]
        download_to_disk = "--download" in sys.argv or "-d" in sys.argv

        # Capture the course name if provided.
        course_name = None
        if "--course" in sys.argv:
            try:
                course_idx = sys.argv.index("--course")
                if course_idx + 1 < len(sys.argv):
                    course_name = sys.argv[course_idx + 1]
            except Exception:
                pass

        asyncio.run(quick_test(file_id, download_to_disk, course_name))
    else:
        # Interactive test mode.
        console.print("\nUsage:", style="cyan bold")
        console.print("  Interactive mode: python direct_file_download_test.py", style="yellow")
        console.print(
            "  Quick mode: python direct_file_download_test.py <file_id>",
            style="yellow",
        )
        console.print(
            "  Direct download: python direct_file_download_test.py <file_id> --download",
            style="yellow",
        )
        console.print(
            "  Categorized download: python direct_file_download_test.py <file_id> --download --course 'Course Name'",
            style="yellow",
        )
        console.print()

        asyncio.run(interactive_test())


if __name__ == "__main__":
    main()

