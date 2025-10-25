"""
Canvas full file index downloader.

Automatically download every file for each course, organize them by course and module,
and optionally upload supported files to an OpenAI Vector Store.
"""

import os
import sys
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime
import json
import time
from typing import List, Optional, Set

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeElapsedColumn
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

try:
    from openai import OpenAI
    import openai
    OPENAI_VERSION = openai.__version__
except ImportError:
    OpenAI = None
    OPENAI_VERSION = None

# Load environment variables
load_dotenv()

console = Console()

# Root directory for downloaded artifacts
DOWNLOAD_ROOT = Path("file_index")

# Aggregated download statistics


def _initial_stats():
    return {
        "courses": 0,
        "modules": 0,
        "files_total": 0,
        "files_downloaded": 0,
        "files_skipped": 0,
        "files_failed": 0,
        "total_size": 0,
        "vector_stores_created": 0,
        "files_uploaded_to_vector_store": 0,
        "files_upload_failed": 0,
        "errors": []
    }


stats = _initial_stats()

# Automation controls (used when driven programmatically)
AUTO_MODE = False
AUTO_SELECTED_COURSE_IDS: Optional[Set[int]] = None
AUTO_CONFIRM = True


def configure_automation(course_ids: Optional[List[int]] = None, auto_confirm: bool = True) -> None:
    """Enable automation mode so the downloader can run without prompts."""

    global AUTO_MODE, AUTO_SELECTED_COURSE_IDS, AUTO_CONFIRM

    AUTO_MODE = True
    AUTO_SELECTED_COURSE_IDS = set(int(cid) for cid in course_ids) if course_ids else None
    AUTO_CONFIRM = auto_confirm


def clear_automation() -> None:
    """Disable automation mode and restore defaults."""

    global AUTO_MODE, AUTO_SELECTED_COURSE_IDS, AUTO_CONFIRM

    AUTO_MODE = False
    AUTO_SELECTED_COURSE_IDS = None
    AUTO_CONFIRM = True


def reset_stats() -> None:
    """Reset run statistics between automated invocations."""

    global stats
    stats = _initial_stats()

# Vector Store configuration
SUPPORTED_EXTENSIONS = {'.pdf', '.txt', '.md', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.json', '.csv'}
MAX_FILE_SIZE = 512 * 1024 * 1024  # 512 MB (OpenAI limit)


def sanitize_filename(name: str) -> str:
    """Clean file or folder names by removing illegal characters."""
    # Characters that are not allowed on Windows
    illegal_chars = '<>:"/\\|?*'
    for char in illegal_chars:
        name = name.replace(char, '_')
    # Remove leading/trailing spaces and dots
    name = name.strip('. ')
    # Enforce a safe length
    if len(name) > 200:
        name = name[:200]
    return name or "unnamed"


async def fetch_all_pages(session, url, headers, params=None):
    """Retrieve all pages of a paginated Canvas API endpoint."""
    all_data = []
    current_url = url
    
    while current_url:
        try:
            async with session.get(current_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        all_data.extend(data)
                    else:
                        all_data.append(data)
                    
                    # Inspect pagination headers for the next page
                    link_header = response.headers.get('Link', '')
                    current_url = None
                    if link_header:
                        for link in link_header.split(','):
                            if 'rel="next"' in link:
                                current_url = link[link.find('<')+1:link.find('>')]
                                break
                    params = None  # Subsequent requests should not include original params
                else:
                    console.print(
                        f"⚠️  Request failed ({response.status}): {current_url}",
                        style="yellow",
                    )
                    break
                    
        except Exception as e:
            console.print(f"❌ Request error: {e}", style="red")
            break
    
    return all_data


async def download_file(session, file_info, file_path):
    """Download a single file payload."""
    file_url = file_info.get('url')
    file_name = file_info.get('display_name', 'unnamed')
    file_size = file_info.get('size', 0)
    
    if not file_url:
        return False, "Missing download URL"
    
    # Skip downloads when the file already exists and matches the expected size
    if file_path.exists() and file_path.stat().st_size == file_size:
        stats["files_skipped"] += 1
        return True, "Already exists"
    
    try:
        async with session.get(file_url) as response:
            if response.status == 200:
                # Ensure parent directories exist
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Stream file contents to disk
                with open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                
                stats["files_downloaded"] += 1
                stats["total_size"] += file_size
                return True, "Success"
            else:
                return False, f"HTTP {response.status}"
                
    except Exception as e:
        return False, str(e)


async def get_courses(session, canvas_url, headers):
    """Retrieve all active courses."""
    console.print("\n📚 Fetching course list...", style="cyan bold")
    
    courses = await fetch_all_pages(
        session,
        f"{canvas_url}/api/v1/courses",
        headers,
        params={"enrollment_state": "active", "per_page": 100}
    )
    
    console.print(f"✓ Located {len(courses)} courses\n", style="green")
    return courses


def select_courses(courses):
    """Prompt the user to select courses to download."""
    if not courses:
        return []

    if AUTO_MODE:
        if AUTO_SELECTED_COURSE_IDS is None:
            return courses

        selected = [course for course in courses if course.get('id') in AUTO_SELECTED_COURSE_IDS]
        return selected

    console.print("Enter course indices using one of the formats below:", style="cyan")
    console.print("  • Type `all` or press Enter to download every course", style="dim")
    console.print("  • Type a single index to select one course (for example: 3)", style="dim")
    console.print("  • Type multiple indices separated by commas (for example: 1,3,5)\n", style="dim")

    while True:
        choice = console.input("Select courses to download (default all): ").strip().lower()

        if choice in ("", "all"):
            return courses

        try:
            selected_indices = set()
            for part in choice.split(','):
                part = part.strip()
                if not part:
                    continue
                index = int(part)
                if 1 <= index <= len(courses):
                    selected_indices.add(index - 1)
                else:
                    raise ValueError

            if not selected_indices:
                raise ValueError

            selected = [courses[i] for i in sorted(selected_indices)]
            console.print(f"✓ Selected {len(selected)} course(s)\n", style="green")
            return selected

        except ValueError:
            console.print("⚠️  Invalid input, enter course numbers or `all`", style="yellow")


async def get_course_modules(session, canvas_url, headers, course_id):
    """Fetch every module for a given course."""
    modules = await fetch_all_pages(
        session,
        f"{canvas_url}/api/v1/courses/{course_id}/modules",
        headers,
        params={"include[]": "items", "per_page": 100}
    )
    return modules


async def get_module_items(session, canvas_url, headers, course_id, module_id):
    """Retrieve all items inside a module."""
    items = await fetch_all_pages(
        session,
        f"{canvas_url}/api/v1/courses/{course_id}/modules/{module_id}/items",
        headers,
        params={"per_page": 100}
    )
    return items


async def get_course_files(session, canvas_url, headers, course_id):
    """Collect every file exposed in the course Files area."""
    try:
        files = await fetch_all_pages(
            session,
            f"{canvas_url}/api/v1/courses/{course_id}/files",
            headers,
            params={"per_page": 100}
        )
        return files
    except:
        # As a fallback, iterate through folders manually.
        try:
            folders = await fetch_all_pages(
                session,
                f"{canvas_url}/api/v1/courses/{course_id}/folders",
                headers,
                params={"per_page": 100}
            )
            
            all_files = []
            for folder in folders:
                folder_files = await fetch_all_pages(
                    session,
                    f"{canvas_url}/api/v1/folders/{folder['id']}/files",
                    headers,
                    params={"per_page": 100}
                )
                all_files.extend(folder_files)
            
            return all_files
        except:
            return []


async def get_file_info(session, canvas_url, headers, file_id):
    """Retrieve detailed metadata for a file."""
    try:
        async with session.get(
            f"{canvas_url}/api/v1/files/{file_id}",
            headers=headers
        ) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return None


def can_upload_to_vector_store(file_path: Path) -> bool:
    """Return True when the file meets the Vector Store upload requirements."""
    # Validate extension support
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False
    
    # Enforce the maximum file size
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
    except:
        return False
    
    return True


def upload_to_vector_store(client, vector_store_id, file_path, course_name):
    """Upload a file to the specified Vector Store."""
    try:
        with open(file_path, 'rb') as f:
            file_response = client.files.create(
                file=f,
                purpose='assistants'
            )
        
    # Attach the uploaded file to the Vector Store (non-beta API)
        client.vector_stores.files.create(
            vector_store_id=vector_store_id,
            file_id=file_response.id
        )
        
        stats["files_uploaded_to_vector_store"] += 1
        return True, file_response.id
        
    except Exception as e:
        stats["files_upload_failed"] += 1
        stats["errors"].append({
            "course": course_name,
            "file": file_path.name,
            "error": f"Vector Store upload failed: {str(e)}"
        })
        return False, str(e)


def create_vector_store_for_course(client, course_name, course_code):
    """Create a dedicated Vector Store for the course."""
    try:
        vector_store_name = f"{course_code}_{course_name}" if course_code else course_name

        # Use the production Vector Store API (not the beta endpoints)
        vector_store = client.vector_stores.create(
            name=vector_store_name[:100]  # Enforce OpenAI naming limits
        )
        
        stats["vector_stores_created"] += 1
        return vector_store.id
        
    except AttributeError as e:
        console.print(f"❌ Vector Stores API unavailable: {e}", style="red")
        console.print("   Please update the OpenAI library: pip install --upgrade openai", style="yellow")
        return None
    except Exception as e:
        console.print(f"❌ Failed to create Vector Store: {e}", style="red")
        import traceback
        console.print(traceback.format_exc(), style="red dim")
        return None


async def process_course(session, canvas_url, headers, course, progress, task_id):
    """Download files for a single course and update aggregate statistics."""
    course_id = course['id']
    course_name = sanitize_filename(course.get('name', f'Course_{course_id}'))
    course_code = course.get('course_code', '')
    
    # Create a folder dedicated to this course
    course_path = DOWNLOAD_ROOT / f"{course_code}_{course_name}" if course_code else DOWNLOAD_ROOT / course_name
    course_path.mkdir(parents=True, exist_ok=True)
    
    progress.update(task_id, description=f"[cyan]Processing course: {course_name}")
    
    course_stats = {
        "modules": 0,
        "files_from_modules": 0,
        "files_from_files": 0,
        "files_downloaded": 0,
        "files_failed": 0
    }
    
    # ================================================
    # 1. Process files referenced in Modules
    # ================================================
    modules = await get_course_modules(session, canvas_url, headers, course_id)
    
    for module in modules:
        module_name = sanitize_filename(module.get('name', f'Module_{module["id"]}'))
        module_path = course_path / "Modules" / module_name
        
        course_stats["modules"] += 1
        
    # Gather module items when they were not pre-included
        items = module.get('items', [])
        if not items:
            items = await get_module_items(session, canvas_url, headers, course_id, module['id'])
        
    # Download module file entries
        for item in items:
            if item.get('type') == 'File':
                file_id = item.get('content_id')
                if file_id:
                    file_info = await get_file_info(session, canvas_url, headers, file_id)
                    if file_info:
                        file_name = sanitize_filename(file_info.get('display_name', 'unnamed'))
                        file_path = module_path / file_name
                        
                        success, msg = await download_file(session, file_info, file_path)
                        
                        if success:
                            course_stats["files_from_modules"] += 1
                            course_stats["files_downloaded"] += 1
                        else:
                            course_stats["files_failed"] += 1
                            stats["errors"].append({
                                "course": course_name,
                                "module": module_name,
                                "file": file_name,
                                "error": msg
                            })
    
    # ================================================
    # 2. Download files from the Files area
    # ================================================
    files = await get_course_files(session, canvas_url, headers, course_id)
    
    for file_info in files:
        file_name = sanitize_filename(file_info.get('display_name', 'unnamed'))
    # Files area assets live under a dedicated folder
        file_path = course_path / "Files" / file_name
        
        success, msg = await download_file(session, file_info, file_path)
        
        if success:
            course_stats["files_from_files"] += 1
            course_stats["files_downloaded"] += 1
        else:
            course_stats["files_failed"] += 1
            stats["errors"].append({
                "course": course_name,
                "file": file_name,
                "error": msg
            })
    
    stats["courses"] += 1
    stats["modules"] += course_stats["modules"]
    stats["files_total"] += course_stats["files_from_modules"] + course_stats["files_from_files"]
    stats["files_failed"] += course_stats["files_failed"]
    
    return course_stats


async def main(skip_download=False):
    """Drive the download workflow and optional Vector Store upload.

    Args:
        skip_download: When True, skip downloading and upload existing files only.
    """

    # Display banner
    console.print("\n" + "="*70, style="cyan bold")
    if skip_download:
        console.print("☁️  Canvas file upload to Vector Store", style="cyan bold")
    else:
        console.print("📦 Canvas full file index downloader + Vector Store upload", style="cyan bold")
    console.print("="*70 + "\n", style="cyan bold")
    
    # Validate required environment variables
    canvas_url = os.getenv("CANVAS_URL")
    canvas_token = os.getenv("CANVAS_ACCESS_TOKEN")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not canvas_url or not canvas_token:
        console.print("❌ Error: Canvas configuration missing", style="red bold")
        console.print("Ensure the .env file includes:", style="yellow")
        console.print("  - CANVAS_URL", style="yellow")
        console.print("  - CANVAS_ACCESS_TOKEN", style="yellow")
        return
    
    console.print(f"✓ Canvas URL: {canvas_url}", style="green")
    console.print("✓ Canvas token configured", style="green")
    console.print(f"✓ Download directory: {DOWNLOAD_ROOT.absolute()}", style="green")
    
    # Inspect OpenAI configuration
    upload_to_openai = False
    openai_client = None
    
    if openai_api_key:
        if OpenAI is None:
            console.print("⚠️  The openai package is not installed; skipping Vector Store upload", style="yellow")
            console.print("   Install with: pip install 'openai>=1.20.0'", style="dim")
        else:
            try:
                # Display the installed version
                if OPENAI_VERSION:
                    console.print(f"✓ OpenAI package version: {OPENAI_VERSION}", style="green")
                
                # Create the OpenAI client (requires assistants=v2 header)
                openai_client = OpenAI(
                    api_key=openai_api_key,
                    default_headers={"OpenAI-Beta": "assistants=v2"}
                )
                
                console.print("✓ OpenAI API configured", style="green")
                
                # Verify Vector Stores API access with a lightweight call
                try:
                    # Validate that the production vector_stores API is reachable
                    test_list = openai_client.vector_stores.list(limit=1)
                    console.print("✓ Vector Stores API reachable", style="green")
                    upload_to_openai = True
                except AttributeError as ae:
                    console.print("❌ Vector Stores API unavailable (client attribute missing)", style="red")
                    console.print(f"   Error: {ae}", style="yellow")
                    console.print("   Confirm that openai>=1.20.0 is installed", style="yellow")
                    openai_client = None
                except Exception as ve:
                    # API is present but the call failed (permissions or transient error)
                    console.print(f"⚠️  Vector Stores API test failed: {ve}", style="yellow")
                    console.print("   Continuing anyway; upload may still succeed", style="dim")
                    upload_to_openai = True
                    
            except Exception as e:
                console.print(f"⚠️  OpenAI initialization failed: {e}", style="yellow")
                import traceback
                console.print(traceback.format_exc()[:500], style="red dim")
    else:
        console.print("⚠️  OPENAI_API_KEY missing; skipping Vector Store upload", style="yellow")
        console.print("   Please set: OPENAI_API_KEY", style="dim")
    
    console.print()
    
    # Ensure the download directory exists
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    
    # When running upload-only mode, validate directory contents
    if skip_download:
        if not DOWNLOAD_ROOT.exists() or not any(DOWNLOAD_ROOT.iterdir()):
            console.print("❌ Error: the file_index directory is missing or empty", style="red bold")
            console.print(f"Run the download mode first or populate: {DOWNLOAD_ROOT.absolute()}", style="yellow")
            return
        
        console.print(f"✓ Located download folder: {DOWNLOAD_ROOT.absolute()}", style="green")
    
    start_time = datetime.now()
    
    # ================================================
    # Optional download phase
    # ================================================
    if not skip_download:
        headers = {
            "Authorization": f"Bearer {canvas_token}",
            "Accept": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            # Fetch every course
            courses = await get_courses(session, canvas_url, headers)
            
            if not courses:
                console.print("⚠️  No courses found", style="yellow")
                return
            
            # Display a course index for selection
            console.print("📋 Course list:", style="cyan bold")
            for i, course in enumerate(courses, 1):
                console.print(f"  {i}. {course.get('name', 'N/A')} (ID: {course['id']})", style="dim")
            console.print()

            courses = select_courses(courses)
            if not courses:
                console.print("⚠️  No courses selected for download", style="yellow")
                return
            
            # Confirm before proceeding
            console.print(f"Downloading all files for {len(courses)} course(s)", style="yellow bold")
            if AUTO_MODE:
                response = 'y' if AUTO_CONFIRM else 'n'
            else:
                response = console.input("Continue? (y/n): ")

            if response.lower() != 'y':
                console.print("Operation cancelled", style="yellow")
                return
            
            console.print()
            
            # Start the download workflow
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                main_task = progress.add_task(
                    "[cyan]Overall progress",
                    total=len(courses)
                )
                
                for course in courses:
                    course_stats = await process_course(
                        session, canvas_url, headers, course, progress, main_task
                    )
                    
                    progress.update(main_task, advance=1)
    else:
        console.print("⏩ Skipping downloads, processing existing files\n", style="yellow")
    
    # ================================================
    # Upload to OpenAI Vector Store
    # ================================================
    if upload_to_openai and openai_client:
        console.print("\n" + "="*70, style="magenta bold")
        console.print("☁️  Uploading files to the OpenAI Vector Store", style="magenta bold")
        console.print("="*70 + "\n", style="magenta bold")
        
        # Aggregate downloaded files per course
        course_files = {}
        
        for course_folder in DOWNLOAD_ROOT.iterdir():
            if course_folder.is_dir() and not course_folder.name.startswith('.'):
                course_name = course_folder.name
                files_to_upload = []
                
                # Collect files that meet upload requirements
                for file_path in course_folder.rglob('*'):
                    if file_path.is_file() and can_upload_to_vector_store(file_path):
                        files_to_upload.append(file_path)
                
                if files_to_upload:
                    course_files[course_name] = files_to_upload
        
        if course_files:
            console.print(
                f"Identified {len(course_files)} course folder(s) with "
                f"{sum(len(files) for files in course_files.values())} uploadable file(s)\n",
                style="green",
            )
            
            with Progress(
                SpinnerColumn(),
                *Progress.get_default_columns(),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                upload_task = progress.add_task(
                    "[magenta]Uploading to Vector Store",
                    total=len(course_files)
                )
                
                # Persist Vector Store metadata for later
                vector_stores_info = {}
                
                for course_name, files in course_files.items():
                    progress.update(upload_task, description=f"[magenta]Processing: {course_name[:40]}")
                    
                    # Create one Vector Store per course
                    vector_store_id = create_vector_store_for_course(openai_client, course_name, "")
                    
                    if vector_store_id:
                        vector_stores_info[course_name] = {
                            "vector_store_id": vector_store_id,
                            "files": []
                        }
                        
                        # Upload each supported file
                        for file_path in files:
                            success, file_id = upload_to_vector_store(
                                openai_client,
                                vector_store_id,
                                file_path,
                                course_name
                            )
                            
                            if success:
                                vector_stores_info[course_name]["files"].append({
                                    "path": str(file_path.relative_to(DOWNLOAD_ROOT)),
                                    "file_id": file_id
                                })
                            
                            # Respect rate limits by spacing requests slightly
                            await asyncio.sleep(0.1)
                    
                    progress.update(upload_task, advance=1)
                
                # Write Vector Store mapping to disk
                vector_store_mapping_path = DOWNLOAD_ROOT / "vector_stores_mapping.json"
                with open(vector_store_mapping_path, 'w', encoding='utf-8') as f:
                    json.dump(vector_stores_info, f, indent=2, ensure_ascii=False)
                
                console.print(f"\n✓ Saved Vector Store mapping to: {vector_store_mapping_path}", style="green")
        else:
            console.print("⚠️  No files qualified for Vector Store upload", style="yellow")
    
    # Wrap up summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    console.print("\n" + "="*70, style="green bold")
    console.print("✅ Download phase complete!", style="green bold")
    console.print("="*70 + "\n", style="green bold")
    
    # Build summary table
    table = Table(title="Download and Upload Summary", show_header=True)
    table.add_column("Metric", style="cyan", width=30)
    table.add_column("Value", style="green", justify="right", width=15)

    table.add_row("━━━━ Download stats ━━━━", "", style="bold cyan")
    table.add_row("Courses processed", str(stats["courses"]))
    table.add_row("Modules processed", str(stats["modules"]))
    table.add_row("Files discovered", str(stats["files_total"]))
    table.add_row("Files downloaded", str(stats["files_downloaded"]))
    table.add_row("Files skipped (existing)", str(stats["files_skipped"]))
    table.add_row("Download failures", str(stats["files_failed"]))
    table.add_row("Total size", f"{stats['total_size'] / (1024*1024):.2f} MB")

    if upload_to_openai:
        table.add_row("━━━━ Vector Store ━━━━", "", style="bold magenta")
        table.add_row("Vector Stores created", str(stats["vector_stores_created"]))
        table.add_row("Files uploaded", str(stats["files_uploaded_to_vector_store"]))
        table.add_row("Upload failures", str(stats["files_upload_failed"]))

    table.add_row("━━━━━━━━━━━━", "", style="bold")
    table.add_row("Total duration", f"{duration:.1f} s")
    
    console.print(table)
    console.print()
    
    # Persist download report
    report = {
        "timestamp": datetime.now().isoformat(),
        "canvas_url": canvas_url,
        "statistics": stats,
        "duration_seconds": duration
    }
    
    report_path = DOWNLOAD_ROOT / "download_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    console.print(f"📄 Saved report: {report_path}", style="dim")
    
    # Display a condensed error table when applicable
    if stats["errors"]:
        console.print(f"\n⚠️  {len(stats['errors'])} file(s) failed during download:", style="yellow bold")
        error_table = Table(show_header=True)
        error_table.add_column("Course", style="cyan")
        error_table.add_column("File", style="white")
        error_table.add_column("Error", style="red")
        
        for error in stats["errors"][:20]:  # Limit display to first 20 entries
            error_table.add_row(
                error.get("course", "N/A"),
                error.get("file", "N/A"),
                error.get("error", "N/A")[:50]
            )
        
        console.print(error_table)
        
        if len(stats["errors"]) > 20:
            console.print(f"\n... {len(stats['errors']) - 20} additional errors omitted", style="dim")

    console.print(f"\n📁 Files stored at: {DOWNLOAD_ROOT.absolute()}", style="green bold")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Canvas file downloader and Vector Store uploader"
    )
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Upload previously downloaded files to the Vector Store without downloading"
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Alias for --upload-only"
    )
    
    args = parser.parse_args()
    skip_download = args.upload_only or args.skip_download
    
    try:
        asyncio.run(main(skip_download=skip_download))
    except KeyboardInterrupt:
        console.print("\n\n⚠️  Operation interrupted by user", style="yellow")
        if stats['files_downloaded'] > 0:
            console.print(f"Downloaded: {stats['files_downloaded']} file(s)", style="dim")
        if stats['files_uploaded_to_vector_store'] > 0:
            console.print(f"Uploaded: {stats['files_uploaded_to_vector_store']} file(s)", style="dim")
    except Exception as e:
        console.print(f"\n❌ Unexpected error: {e}", style="red bold")
        import traceback
        console.print(traceback.format_exc(), style="red dim")

