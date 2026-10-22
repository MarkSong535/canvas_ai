"""
Canvas LMS API toolset - student-permission version

This file contains all the API tools a student can use on Canvas
Reads CANVAS_ACCESS_TOKEN and CANVAS_URL from os.environ
"""

import os
from collections import OrderedDict
import aiohttp
from typing import Optional, List, Dict, Any
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL
from src import canvas_sandbox
from src.utils.file_text import extract_text

WRITE_BLOCKED = (
    "Blocked: this assistant never sends changes (submissions, discussion posts) to Canvas, so nothing was "
    "sent. Tell the student to do this in Canvas directly."
)
WRITE_POLICY = (
    " Changes never reach the live Canvas: in sandbox mode they are recorded locally, otherwise the request "
    "is blocked and nothing is sent."
)


class CanvasAPIBase(AsyncTool):
    """Base class for Canvas API tools; handles common API request logic"""
    
    def __init__(self):
        super().__init__()
        if not os.environ.get("CANVAS_ACCESS_TOKEN"):
            raise ValueError("CANVAS_ACCESS_TOKEN environment variable not found")

    @property
    def headers(self) -> dict:
        # Read on every request, never stored: in sandbox mode the token is swapped for a simulated one at start
        return {
            "Authorization": f"Bearer {os.environ.get('CANVAS_ACCESS_TOKEN', '')}",
            "Content-Type": "application/json"
        }

    @property
    def canvas_url(self) -> str:
        # Read on every request: in sandbox mode CANVAS_URL is switched to the local server after tools exist
        url = os.environ.get("CANVAS_URL", "https://canvas.instructure.com").rstrip("/")
        if url.startswith("http://") and not url.startswith(("http://127.0.0.1", "http://localhost")):
            url = "https://" + url[len("http://"):]
        if "http" not in url:
            url = "https://" + url
        return url

    @property
    def base_url(self) -> str:
        return f"{self.canvas_url}/api/v1"
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None, 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generic method for sending API requests"""
        url = f"{self.base_url}/{endpoint}"
        # Writes never reach the live Canvas: they are only sent to the running local sandbox (which records
        # them instead); anywhere else they are blocked here, before any request is made.
        if method.upper() != "GET" and canvas_sandbox.active_url() != self.canvas_url:
            return {"error": WRITE_BLOCKED}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 404:
                        return {"error": "Resource not found"}
                    else:
                        error_text = await response.text()
                        return {"error": f"API Request Failed (Status Code {response.status}): {error_text}"}
        except Exception as e:
            return {"error": f"Request Error: {str(e)}"}


@TOOL.register_module(name="canvas_list_courses", force=True)
class CanvasListCourses(CanvasAPIBase):
    """List all of the student's courses"""
    
    name = "canvas_list_courses"
    description = "Get the list of all courses the current student is enrolled in, including each course's name, ID, status, and other details"
    
    parameters = {
        "type": "object",
        "properties": {
            "enrollment_state": {
                "type": "string",
                "description": "Enrollment state: active or completed (default: active)",
                "nullable": True
            },
            "include": {
                "type": "string",
                "description": "Extra information to include; options: total_students, teachers, syllabus_body",
                "nullable": True
            }
        },
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(
        self, 
        enrollment_state: str = "active", 
        include: str = ""
    ) -> ToolResult:
        """Get the course list"""
        try:
            params = {
                "enrollment_state": enrollment_state,
                "per_page": 50
            }
            if include:
                params["include[]"] = include
            
            result = await self._make_request("GET", "courses", params=params)
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            # Format the output
            courses_info = []
            for course in result:
                info = {
                    "id": course.get("id"),
                    "name": course.get("name"),
                    "course_code": course.get("course_code"),
                    "workflow_state": course.get("workflow_state"),
                    "enrollments": course.get("enrollments", [])
                }
                courses_info.append(info)
            
            return ToolResult(
                output=f"Found {len(courses_info)} courses:\n" + 
                       "\n".join([f"- [{c['id']}] {c['name']} ({c['course_code']})" 
                                 for c in courses_info]),
                error=None
            )
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get courses: {str(e)}")


@TOOL.register_module(name="canvas_get_assignments", force=True)
class CanvasGetAssignments(CanvasAPIBase):
    """Get the list of assignments in a course"""
    
    name = "canvas_get_assignments"
    description = "Get all assignments in a specified course, including each assignment's name, due date, points, and other details"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "include_submission": {
                "type": "boolean",
                "description": "Whether to include submission information (default: True)",
                "nullable": True
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(
        self, 
        course_id: str, 
        include_submission: bool = True
    ) -> ToolResult:
        """Get the assignment list"""
        try:
            params = {"per_page": 50}
            if include_submission:
                params["include[]"] = "submission"
            
            result = await self._make_request(
                "GET", 
                f"courses/{course_id}/assignments", 
                params=params
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            # Format the output
            assignments_info = []
            for assignment in result:
                info = {
                    "id": assignment.get("id"),
                    "name": assignment.get("name"),
                    "due_at": assignment.get("due_at", "no due date"),
                    "points_possible": assignment.get("points_possible", 0),
                    "submission_types": assignment.get("submission_types", []),
                    "submission": assignment.get("submission", {})
                }
                assignments_info.append(info)
            
            output = f"Course {course_id} has {len(assignments_info)} assignments:\n"
            for a in assignments_info:
                submission_status = "unsubmitted"
                if a["submission"]:
                    submission_status = a["submission"].get("workflow_state", "unsubmitted")
                output += f"- [{a['id']}] {a['name']} (Due: {a['due_at']}, Points: {a['points_possible']}, Status: {submission_status})\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get assignments: {str(e)}")


@TOOL.register_module(name="canvas_submit_assignment", force=True)
class CanvasSubmitAssignment(CanvasAPIBase):
    """Submit an assignment"""
    
    name = "canvas_submit_assignment"
    description = "Submit an assignment in a course, as text or a URL." + WRITE_POLICY
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "assignment_id": {
                "type": "string",
                "description": "Assignment ID"
            },
            "submission_type": {
                "type": "string",
                "description": "Submission type: online_text_entry, online_url, or online_upload"
            },
            "body": {
                "type": "string",
                "description": "Submission text (used with online_text_entry)",
                "nullable": True
            },
            "url": {
                "type": "string",
                "description": "URL to submit (used with online_url)",
                "nullable": True
            }
        },
        "required": ["course_id", "assignment_id", "submission_type"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(
        self, 
        course_id: str, 
        assignment_id: str,
        submission_type: str,
        body: str = "",
        url: str = ""
    ) -> ToolResult:
        """Submit an assignment"""
        try:
            data = {
                "submission": {
                    "submission_type": submission_type
                }
            }
            
            if submission_type == "online_text_entry" and body:
                data["submission"]["body"] = body
            elif submission_type == "online_url" and url:
                data["submission"]["url"] = url
            
            result = await self._make_request(
                "POST",
                f"courses/{course_id}/assignments/{assignment_id}/submissions",
                data=data
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            return ToolResult(
                output=f"Assignment submitted successfully!\n"
                       f"- Assignment ID: {assignment_id}\n"
                       f"- Submission type: {submission_type}\n"
                       f"- Submitted at: {result.get('submitted_at', 'unknown')}"
                       + (f"\n- SANDBOX: {result.get('note')}" if result.get("sandbox") else ""),
                error=None
            )
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to submit assignment: {str(e)}")


@TOOL.register_module(name="canvas_get_modules", force=True)
class CanvasGetModules(CanvasAPIBase):
    """Get the list of modules in a course"""
    
    name = "canvas_get_modules"
    description = "Get all modules and the content structure of a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """Get the module list"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/modules",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Module structure of course {course_id}:\n"
            for module in result:
                output += f"\n📚 Module [{module.get('id')}]: {module.get('name')}\n"
                output += f"   Status: {module.get('workflow_state')}\n"
                output += f"   Items: {module.get('items_count', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get modules: {str(e)}")


@TOOL.register_module(name="canvas_get_module_items", force=True)
class CanvasGetModuleItems(CanvasAPIBase):
    """Get the content items in a module"""
    
    name = "canvas_get_module_items"
    description = "Get all content items (files, pages, assignments, etc.) in a specified module"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "module_id": {
                "type": "string",
                "description": "Module ID"
            }
        },
        "required": ["course_id", "module_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, module_id: str) -> ToolResult:
        """Get module items"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/modules/{module_id}/items",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Contents of module {module_id}:\n"
            for item in result:
                icon = {
                    "Assignment": "📝",
                    "Page": "📄",
                    "File": "📁",
                    "Discussion": "💬",
                    "Quiz": "✏️",
                    "ExternalUrl": "🔗",
                    "ExternalTool": "🔧"
                }.get(item.get("type"), "•")
                
                output += f"{icon} [{item.get('id')}] {item.get('title')} ({item.get('type')})\n"
                if item.get("type") == "File" and item.get("content_id"):
                    # The file's own id, so its details and download link can be fetched with canvas_get_file_info
                    output += f"   File ID: {item.get('content_id')}\n"
                elif item.get("type") == "Page" and item.get("page_url"):
                    # The page's address, which canvas_get_page_content needs (titles are not addresses)
                    output += f"   Page URL: {item.get('page_url')}\n"

            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get module items: {str(e)}")


@TOOL.register_module(name="canvas_get_files", force=True)
class CanvasGetFiles(CanvasAPIBase):
    """Get the list of files in a course"""
    
    name = "canvas_get_files"
    description = "Get all files and resources in a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "search_term": {
                "type": "string",
                "description": "Search keyword (optional)",
                "nullable": True
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, search_term: str = "") -> ToolResult:
        """Get the file list"""
        try:
            params = {"per_page": 50}
            if search_term:
                params["search_term"] = search_term
            
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/files",
                params=params
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Files in course {course_id}:\n"
            for file in result:
                size_mb = file.get("size", 0) / (1024 * 1024)
                output += f"📁 [{file.get('id')}] {file.get('display_name')} "
                output += f"({size_mb:.2f}MB, {file.get('content-type', 'unknown type')})\n"
                output += f"   URL: {file.get('url')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get files: {str(e)}")


@TOOL.register_module(name="canvas_get_discussions", force=True)
class CanvasGetDiscussions(CanvasAPIBase):
    """Get the list of discussion topics in a course"""
    
    name = "canvas_get_discussions"
    description = "Get all discussion topics in a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """Get the discussion list"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/discussion_topics",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Discussions in course {course_id}:\n"
            for topic in result:
                output += f"💬 [{topic.get('id')}] {topic.get('title')}\n"
                output += f"   Posted at: {topic.get('posted_at', 'unknown')}\n"
                output += f"   Replies: {topic.get('discussion_subentry_count', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get discussions: {str(e)}")


@TOOL.register_module(name="canvas_post_discussion", force=True)
class CanvasPostDiscussion(CanvasAPIBase):
    """Post in a discussion"""
    
    name = "canvas_post_discussion"
    description = "Post a reply or comment in a specified discussion topic." + WRITE_POLICY
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "topic_id": {
                "type": "string",
                "description": "Discussion topic ID"
            },
            "message": {
                "type": "string",
                "description": "Message to post"
            }
        },
        "required": ["course_id", "topic_id", "message"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(
        self, 
        course_id: str, 
        topic_id: str, 
        message: str
    ) -> ToolResult:
        """Post a discussion reply"""
        try:
            data = {"message": message}
            
            result = await self._make_request(
                "POST",
                f"courses/{course_id}/discussion_topics/{topic_id}/entries",
                data=data
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            return ToolResult(
                output=f"Discussion reply posted successfully!\n"
                       f"- Topic ID: {topic_id}\n"
                       f"- Posted at: {result.get('created_at', 'unknown')}"
                       + (f"\n- SANDBOX: {result.get('note')}" if result.get("sandbox") else ""),
                error=None
            )
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to post discussion reply: {str(e)}")


@TOOL.register_module(name="canvas_get_announcements", force=True)
class CanvasGetAnnouncements(CanvasAPIBase):
    """Get course announcements"""
    
    name = "canvas_get_announcements"
    description = "Get the latest announcements for all courses (or only the courses given in context_codes)"
    
    parameters = {
        "type": "object",
        "properties": {
            "context_codes": {
                "type": "string",
                "description": "Comma-separated course context codes, format: course_123,course_456 (optional; leave empty to get all courses)",
                "nullable": True
            }
        },
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, context_codes: str = "") -> ToolResult:
        """Get the announcement list"""
        try:
            params = {"per_page": 20}
            if context_codes:
                params["context_codes[]"] = context_codes.split(",")
            
            result = await self._make_request(
                "GET",
                "announcements",
                params=params
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "📢 Latest announcements:\n"
            for announcement in result:
                output += f"\nTitle: {announcement.get('title')}\n"
                output += f"Posted at: {announcement.get('posted_at', 'unknown')}\n"
                output += f"Content: {announcement.get('message', 'no content')[:200]}...\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get announcements: {str(e)}")


@TOOL.register_module(name="canvas_get_calendar_events", force=True)
class CanvasGetCalendarEvents(CanvasAPIBase):
    """Get calendar events"""
    
    name = "canvas_get_calendar_events"
    description = "Get the student's calendar events, including course activities, assignment due dates, etc."
    
    parameters = {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "Start date, format: YYYY-MM-DD (optional)",
                "nullable": True
            },
            "end_date": {
                "type": "string",
                "description": "End date, format: YYYY-MM-DD (optional)",
                "nullable": True
            }
        },
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(
        self, 
        start_date: str = "", 
        end_date: str = ""
    ) -> ToolResult:
        """Get calendar events"""
        try:
            params = {"per_page": 50}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            
            result = await self._make_request(
                "GET",
                "calendar_events",
                params=params
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "📅 Calendar events:\n"
            for event in result:
                output += f"\n🗓️ {event.get('title')}\n"
                output += f"   Time: {event.get('start_at', 'unknown')}\n"
                output += f"   Type: {event.get('type', 'unknown')}\n"
                if event.get('description'):
                    output += f"   Description: {event.get('description')[:100]}...\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get calendar events: {str(e)}")


@TOOL.register_module(name="canvas_get_grades", force=True)
class CanvasGetGrades(CanvasAPIBase):
    """Get course grades"""
    
    name = "canvas_get_grades"
    description = "Get the student's grade information in a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """Get grades"""
        try:
            # Get the current user ID
            user_result = await self._make_request("GET", "users/self")
            if isinstance(user_result, dict) and "error" in user_result:
                return ToolResult(output=None, error=user_result["error"])
            
            user_id = user_result.get("id")
            
            # Get enrollment info (includes grades)
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/enrollments",
                params={"user_id": user_id}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Grades in course {course_id}:\n"
            for enrollment in result:
                grades = enrollment.get("grades", {})
                output += f"📊 Current grade: {grades.get('current_grade', 'N/A')}\n"
                output += f"   Current score: {grades.get('current_score', 'N/A')}\n"
                output += f"   Final grade: {grades.get('final_grade', 'N/A')}\n"
                output += f"   Final score: {grades.get('final_score', 'N/A')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get grades: {str(e)}")


@TOOL.register_module(name="canvas_get_pages", force=True)
class CanvasGetPages(CanvasAPIBase):
    """Get the list of pages in a course"""
    
    name = "canvas_get_pages"
    description = "Get all pages (wiki pages) in a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """Get the page list"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/pages",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Pages in course {course_id}:\n"
            for page in result:
                output += f"📄 {page.get('title')}\n"
                output += f"   URL: {page.get('url')}\n"
                output += f"   Updated at: {page.get('updated_at', 'unknown')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get pages: {str(e)}")


@TOOL.register_module(name="canvas_get_page_content", force=True)
class CanvasGetPageContent(CanvasAPIBase):
    """Get the full content of a page"""
    
    name = "canvas_get_page_content"
    description = "Get the full content of a specified page"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "page_url": {
                "type": "string",
                "description": "Page URL or title"
            }
        },
        "required": ["course_id", "page_url"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, page_url: str) -> ToolResult:
        """Get page content"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/pages/{page_url}"
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📄 Page: {result.get('title')}\n"
            output += f"Updated at: {result.get('updated_at', 'unknown')}\n\n"
            output += f"Content:\n{result.get('body', 'no content')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get page content: {str(e)}")


@TOOL.register_module(name="canvas_get_quizzes", force=True)
class CanvasGetQuizzes(CanvasAPIBase):
    """Get the list of quizzes in a course"""
    
    name = "canvas_get_quizzes"
    description = "Get all quizzes in a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """Get the quiz list"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/quizzes",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"Quizzes in course {course_id}:\n"
            for quiz in result:
                output += f"✏️ [{quiz.get('id')}] {quiz.get('title')}\n"
                output += f"   Type: {quiz.get('quiz_type', 'unknown')}\n"
                output += f"   Points: {quiz.get('points_possible', 0)}\n"
                output += f"   Due: {quiz.get('due_at', 'no due date')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get quizzes: {str(e)}")


@TOOL.register_module(name="canvas_get_todo_items", force=True)
class CanvasGetTodoItems(CanvasAPIBase):
    """Get to-do items"""
    
    name = "canvas_get_todo_items"
    description = "Get the student's to-do list, including upcoming assignments and tasks"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """Get to-do items"""
        try:
            result = await self._make_request("GET", "users/self/todo")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "📝 To-do items:\n"
            for item in result:
                assignment = item.get("assignment", {})
                output += f"\n• {assignment.get('name', 'unknown task')}\n"
                output += f"  Course: {item.get('context_name', 'unknown')}\n"
                output += f"  Due: {assignment.get('due_at', 'no due date')}\n"
                output += f"  Points: {assignment.get('points_possible', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get to-do items: {str(e)}")


@TOOL.register_module(name="canvas_get_upcoming_events", force=True)
class CanvasGetUpcomingEvents(CanvasAPIBase):
    """Get upcoming events"""
    
    name = "canvas_get_upcoming_events"
    description = "Get all of the student's upcoming events and activities"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """Get upcoming events"""
        try:
            result = await self._make_request("GET", "users/self/upcoming_events")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "🗓️ Upcoming events:\n"
            for event in result:
                output += f"\n• {event.get('title', 'unknown event')}\n"
                output += f"  Time: {event.get('start_at', 'unknown')}\n"
                output += f"  Type: {event.get('type', 'unknown')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get upcoming events: {str(e)}")


@TOOL.register_module(name="canvas_get_groups", force=True)
class CanvasGetGroups(CanvasAPIBase):
    """Get the student's groups"""
    
    name = "canvas_get_groups"
    description = "Get all groups the student belongs to"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """Get the group list"""
        try:
            result = await self._make_request("GET", "users/self/groups")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "👥 My groups:\n"
            for group in result:
                output += f"\n• [{group.get('id')}] {group.get('name')}\n"
                output += f"  Members: {group.get('members_count', 0)}\n"
                output += f"  Course: {group.get('course_id', 'unknown')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get groups: {str(e)}")


@TOOL.register_module(name="canvas_get_file_info", force=True)
class CanvasGetFileInfo(CanvasAPIBase):
    """Get detailed file information"""
    
    name = "canvas_get_file_info"
    description = "Get detailed information about a specified file, including download link, size, type, etc."
    
    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "File ID"
            }
        },
        "required": ["file_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, file_id: str) -> ToolResult:
        """Get file information"""
        try:
            result = await self._make_request("GET", f"files/{file_id}")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📁 File information:\n"
            output += f"Name: {result.get('display_name')}\n"
            output += f"ID: {result.get('id')}\n"
            output += f"Size: {result.get('size', 0) / (1024*1024):.2f} MB\n"
            output += f"Type: {result.get('content-type', 'unknown')}\n"
            output += f"Modified at: {result.get('modified_at', 'unknown')}\n"
            output += f"Download link: {result.get('url')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get file information: {str(e)}")


@TOOL.register_module(name="canvas_read_file", force=True)
class CanvasReadFile(CanvasAPIBase):
    """Read the text content of a course file"""

    name = "canvas_read_file"
    description = (
        "Read the text content of a course file (PDF, Word, PowerPoint, Excel, text, code or notebook) so you "
        "can work with what it says, e.g. a worksheet's questions, an assignment sheet or lecture notes. Long "
        "files come in parts: call again with `start` to continue. Images and scanned PDFs have no readable text."
    )

    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "File ID (from file lists, file search, or module items)"
            },
            "start": {
                "type": "integer",
                "description": "Character offset to continue reading from (default 0)",
                "nullable": True
            }
        },
        "required": ["file_id"],
        "additionalProperties": False
    }

    output_type = "any"

    CHUNK_CHARS = 12000
    MAX_BYTES = 60 * 1024 * 1024
    _text_cache: "OrderedDict[str, tuple[str, str, str]]" = OrderedDict()  # file id -> (name, text, note)

    async def forward(self, file_id: str, start: int = 0) -> ToolResult:
        """Read a file's text"""
        try:
            meta = await self._make_request("GET", f"files/{file_id}")
            if isinstance(meta, dict) and "error" in meta:
                return ToolResult(output=None, error=meta["error"])
            name = meta.get("display_name") or meta.get("filename") or f"file {file_id}"

            cached = self._text_cache.get(str(file_id))
            if cached is None:
                data, problem = await self._file_bytes(str(file_id), meta)
                if problem:
                    return ToolResult(output=f"📄 {name}: {problem}", error=None)
                text, note = extract_text(data, name, meta.get("content-type"))
                cached = (name, text, note)
                self._text_cache[str(file_id)] = cached
                while len(self._text_cache) > 16:
                    self._text_cache.popitem(last=False)
            name, text, note = cached
            if not text.strip():
                return ToolResult(output=f"📄 {name}: {note or 'No readable text found.'}", error=None)

            start = max(0, int(start or 0))
            chunk = text[start:start + self.CHUNK_CHARS]
            output = f"📄 {name} ({len(text)} characters of text"
            output += f", showing from character {start})\n" if start else ")\n"
            if note:
                output += f"Note: {note}\n"
            output += chunk
            if start + self.CHUNK_CHARS < len(text):
                output += (f"\n\n[More text follows: call canvas_read_file with file_id={file_id} and "
                           f"start={start + self.CHUNK_CHARS} to continue.]")
            return ToolResult(output=output, error=None)

        except Exception as e:
            return ToolResult(output=None, error=f"Failed to read file: {str(e)}")

    async def _file_bytes(self, file_id: str, meta: dict) -> tuple[bytes | None, str | None]:
        if (meta.get("size") or 0) > self.MAX_BYTES:
            return None, f"The file is too large to read here ({meta['size'] / (1024 * 1024):.0f} MB)."
        if canvas_sandbox.active_url() is not None:
            # Sandbox mode: read the downloaded copy; nothing is fetched from Canvas
            path = canvas_sandbox.local_file_path(file_id)
            if path is None:
                return None, "This file isn't in the sandbox (Canvas didn't allow it to be downloaded)."
            return path.read_bytes(), None
        url = meta.get("url")
        if not url or meta.get("locked_for_user"):
            return None, "This file is locked or has no download link in Canvas."
        async with aiohttp.ClientSession() as session:
            # No auth header: Canvas download URLs are pre-signed and redirect to file storage
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status != 200:
                    return None, f"Downloading the file failed (HTTP {response.status})."
                return await response.read(), None

@TOOL.register_module(name="canvas_get_folders", force=True)
class CanvasGetFolders(CanvasAPIBase):
    """Get the list of folders in a course"""
    
    name = "canvas_get_folders"
    description = "Get the folder structure of a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """Get the folder list"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/folders",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📂 Folders in course {course_id}:\n"
            for folder in result:
                output += f"• [{folder.get('id')}] {folder.get('full_name')}\n"
                output += f"  Files: {folder.get('files_count', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get folders: {str(e)}")


@TOOL.register_module(name="canvas_get_folder_files", force=True)
class CanvasGetFolderFiles(CanvasAPIBase):
    """Get the files in a folder"""
    
    name = "canvas_get_folder_files"
    description = "Get all files in a specified folder"
    
    parameters = {
        "type": "object",
        "properties": {
            "folder_id": {
                "type": "string",
                "description": "Folder ID"
            }
        },
        "required": ["folder_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, folder_id: str) -> ToolResult:
        """Get the files in a folder"""
        try:
            result = await self._make_request(
                "GET",
                f"folders/{folder_id}/files",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📂 Files in folder {folder_id}:\n"
            for file in result:
                size_mb = file.get('size', 0) / (1024 * 1024)
                output += f"📄 [{file.get('id')}] {file.get('display_name')}\n"
                output += f"   Size: {size_mb:.2f} MB\n"
                output += f"   Type: {file.get('content-type', 'unknown')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get folder files: {str(e)}")


@TOOL.register_module(name="canvas_search_files", force=True)
class CanvasSearchFiles(CanvasAPIBase):
    """Search for files in a course"""
    
    name = "canvas_search_files"
    description = "Search for files in a specified course"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "Course ID"
            },
            "search_term": {
                "type": "string",
                "description": "Search keyword"
            }
        },
        "required": ["course_id", "search_term"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, search_term: str) -> ToolResult:
        """Search files"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/files",
                params={"search_term": search_term, "per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"🔍 Results for '{search_term}':\n"
            if len(result) == 0:
                output += "No matching files found"
            else:
                for file in result:
                    output += f"\n📄 {file.get('display_name')}\n"
                    output += f"   File ID: {file.get('id')}\n"
                    output += f"   Size: {file.get('size', 0) / 1024:.2f} KB\n"
                    output += f"   Download: {file.get('url')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to search files: {str(e)}")


@TOOL.register_module(name="vector_store_list", force=True)
class VectorStoreList(AsyncTool):
    """List all available vector stores"""
    
    name = "vector_store_list"
    description = "List all available course knowledge bases (vector stores), showing each one's ID, name, and file count"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """Get the vector store list"""
        try:
            # Import OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI library is not installed; run: pip install openai"
                )
            
            # Get the API key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="OPENAI_API_KEY is not configured; add it to the .env file"
                )
            
            # Create the client
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # Get the vector stores
            response = client.vector_stores.list(limit=100)
            vector_stores = list(response.data)
            
            if not vector_stores:
                return ToolResult(
                    output="📋 No knowledge bases are available\nRun file_index_downloader.py first to create one",
                    error=None
                )
            
            # Format the output
            output = f"📚 Found {len(vector_stores)} course knowledge bases:\n\n"
            
            for i, vs in enumerate(vector_stores, 1):
                file_count = vs.file_counts.total if hasattr(vs, 'file_counts') else 0
                output += f"{i}. [{vs.id}] {vs.name}\n"
                output += f"   📁 Files: {file_count}\n"
                if hasattr(vs, 'created_at'):
                    output += f"   📅 Created at: {vs.created_at}\n"
                output += "\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"Failed to get knowledge bases: {str(e)}")


@TOOL.register_module(name="vector_store_search", force=True)
class VectorStoreSearch(AsyncTool):
    """Search a vector store for relevant content"""
    
    name = "vector_store_search"
    description = "Search a specified course knowledge base for relevant content; use it to answer questions about course materials, lecture notes, assignments, etc."
    
    parameters = {
        "type": "object",
        "properties": {
            "vector_store_id": {
                "type": "string",
                "description": "Vector store ID (from the vector_store_list tool)"
            },
            "query": {
                "type": "string",
                "description": "Search query, e.g. 'What is this course mainly about?' or 'Requirements for Assignment 1'"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 5)",
                "nullable": True
            }
        },
        "required": ["vector_store_id", "query"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, vector_store_id: str, query: str, max_results: int = 5) -> ToolResult:
        """Search the vector store"""
        try:
            # Import OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI library is not installed; run: pip install openai"
                )
            
            # Get the API key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="OPENAI_API_KEY is not configured; add it to the .env file"
                )
            
            # Create the client
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # Run the search
            response = client.vector_stores.search(
                vector_store_id=vector_store_id,
                query=query,
                max_num_results=max_results
            )
            
            # Check the results
            if not response or not hasattr(response, 'data') or not response.data:
                return ToolResult(
                    output=f"🔍 Search query: \"{query}\"\n❌ No relevant content found",
                    error=None
                )
            
            # Format the output
            output = f"🔍 Search query: \"{query}\"\n"
            output += f"📊 Found {len(response.data)} relevant results:\n\n"
            
            for i, result in enumerate(response.data, 1):
                output += f"{'='*60}\n"
                output += f"Result {i}:\n"
                
                # Relevance score
                if hasattr(result, 'score'):
                    output += f"📈 Relevance: {result.score:.2%}\n"
                
                # File name
                if hasattr(result, 'filename'):
                    output += f"📄 Source: {result.filename}\n"
                
                # Metadata
                if hasattr(result, 'attributes') and result.attributes:
                    output += f"🏷️  Attributes: {result.attributes}\n"
                
                # Content
                if hasattr(result, 'content'):
                    content = result.content
                    # Limit the length
                    if len(content) > 800:
                        content = content[:800] + "...\n(content truncated)"
                    output += f"\n📝 Content:\n{content}\n"
                
                output += "\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ToolResult(
                output=None,
                error=f"Search failed: {str(e)}\nDetails: {error_detail[:500]}"
            )


@TOOL.register_module(name="vector_store_list_files", force=True)
class VectorStoreListFiles(AsyncTool):
    """List all files in a vector store"""
    
    name = "vector_store_list_files"
    description = "List all files in a specified knowledge base, showing each file's ID, name, status, and other details; can optionally read file contents"
    
    parameters = {
        "type": "object",
        "properties": {
            "vector_store_id": {
                "type": "string",
                "description": "Vector store ID (from the vector_store_list tool)"
            },
            "read_content": {
                "type": "boolean",
                "description": "Whether to read file contents (default: False, which only lists file information)",
                "nullable": True
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of files to return (default: 100; 0 or a negative number returns all files)",
                "nullable": True
            }
        },
        "required": ["vector_store_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, vector_store_id: str, read_content: bool = False, limit: int = 100) -> ToolResult:
        """List vector store files"""
        try:
            # Import OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI library is not installed; run: pip install openai"
                )
            
            # Get the API key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="OPENAI_API_KEY is not configured; add it to the .env file"
                )
            
            # Create the client
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # Get the vector store file list
            files = []
            
            # If limit <= 0, get all files (paginated)
            if limit <= 0:
                after = None
                while True:
                    if after:
                        response = client.vector_stores.files.list(
                            vector_store_id=vector_store_id,
                            limit=100,  # At most 100 per page
                            after=after
                        )
                    else:
                        response = client.vector_stores.files.list(
                            vector_store_id=vector_store_id,
                            limit=100
                        )
                    
                    batch_files = list(response.data)
                    if not batch_files:
                        break
                    
                    files.extend(batch_files)
                    
                    # Check whether there is more data
                    if hasattr(response, 'has_more') and response.has_more:
                        # Use the last file's ID as the after parameter
                        after = batch_files[-1].id
                    else:
                        break
            else:
                # Fetch a limited number of files
                response = client.vector_stores.files.list(
                    vector_store_id=vector_store_id,
                    limit=limit
                )
                files = list(response.data)
            
            if not files:
                return ToolResult(
                    output=f"📋 Vector Store [{vector_store_id}] has no files",
                    error=None
                )
            
            # Format the output
            output = f"📚 Vector Store [{vector_store_id}] files:\n"
            output += f"Found {len(files)} files\n\n"
            
            for i, file in enumerate(files, 1):
                output += f"{'='*60}\n"
                output += f"File {i}:\n"
                output += f"🆔 File ID: {file.id}\n"
                
                if hasattr(file, 'status'):
                    status_emoji = "✅" if file.status == "completed" else "⏳"
                    output += f"{status_emoji} Status: {file.status}\n"
                
                if hasattr(file, 'created_at'):
                    from datetime import datetime
                    created = datetime.fromtimestamp(file.created_at)
                    output += f"📅 Created at: {created.strftime('%Y-%m-%d %H:%M:%S')}\n"
                
                # Always get basic file info (name, size, etc.)
                try:
                    # Get detailed file info
                    file_info = client.files.retrieve(file.id)
                    
                    if hasattr(file_info, 'filename'):
                        output += f"📄 File name: {file_info.filename}\n"
                    
                    if hasattr(file_info, 'bytes'):
                        size_kb = file_info.bytes / 1024
                        if size_kb >= 1024:
                            output += f"📦 Size: {size_kb / 1024:.2f} MB\n"
                        else:
                            output += f"📦 Size: {size_kb:.2f} KB\n"
                    
                    if hasattr(file_info, 'purpose'):
                        output += f"🎯 Purpose: {file_info.purpose}\n"
                    
                    # Read the content if requested
                    if read_content and file.status == "completed":
                        # Try to read the file content
                        try:
                            content_response = client.files.content(file.id)
                            content = content_response.read()
                            
                            # Try to decode as text
                            try:
                                text_content = content.decode('utf-8')
                                # Limit the length
                                if len(text_content) > 1000:
                                    text_content = text_content[:1000] + "\n...(content truncated)"
                                output += f"\n📝 Content preview:\n{text_content}\n"
                            except:
                                output += f"\n⚠️  Cannot display file content (not a text file, or an encoding issue)\n"
                                output += f"   File size: {len(content)} bytes\n"
                        except Exception as e:
                            output += f"\n⚠️  Failed to read content: {str(e)}\n"
                
                except Exception as e:
                    output += f"\n⚠️  Failed to get file information: {str(e)}\n"
                
                output += "\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ToolResult(
                output=None,
                error=f"Failed to get files: {str(e)}\nDetails: {error_detail[:500]}"
            )


@TOOL.register_module(name="vector_store_get_file", force=True)
class VectorStoreGetFile(AsyncTool):
    """Get a file by file_id and read its content"""
    
    name = "vector_store_get_file"
    description = "Get a file's details by file_id and read its content; shows the full content of text files"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "OpenAI file ID (from the vector_store_list_files tool)"
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum number of characters to display (default: 5000)",
                "nullable": True
            }
        },
        "required": ["file_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, file_id: str, max_length: int = 5000) -> ToolResult:
        """Get file content"""
        try:
            # Import OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI library is not installed; run: pip install openai"
                )
            
            # Get the API key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="OPENAI_API_KEY is not configured; add it to the .env file"
                )
            
            # Create the client
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # Get the file info
            file_info = client.files.retrieve(file_id)
            
            output = f"📄 File details:\n"
            output += f"{'='*60}\n"
            output += f"🆔 File ID: {file_info.id}\n"
            
            if hasattr(file_info, 'filename'):
                output += f"📝 File name: {file_info.filename}\n"
            
            if hasattr(file_info, 'purpose'):
                output += f"🎯 Purpose: {file_info.purpose}\n"
            
            if hasattr(file_info, 'bytes'):
                size_kb = file_info.bytes / 1024
                size_mb = size_kb / 1024
                if size_mb >= 1:
                    output += f"📦 Size: {size_mb:.2f} MB\n"
                else:
                    output += f"📦 Size: {size_kb:.2f} KB\n"
            
            if hasattr(file_info, 'created_at'):
                from datetime import datetime
                created = datetime.fromtimestamp(file_info.created_at)
                output += f"📅 Created at: {created.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if hasattr(file_info, 'status'):
                status_emoji = "✅" if file_info.status == "processed" else "⏳"
                output += f"{status_emoji} Status: {file_info.status}\n"
            
            output += f"\n{'='*60}\n"
            
            # Try to read the file content
            try:
                content_response = client.files.content(file_id)
                content = content_response.read()
                
                # Try to decode as text
                try:
                    text_content = content.decode('utf-8')
                    
                    output += f"\n📖 File content:\n"
                    output += f"{'='*60}\n"
                    
                    if len(text_content) > max_length:
                        output += text_content[:max_length]
                        output += f"\n\n{'='*60}\n"
                        output += f"⚠️  Content truncated (showing {max_length}/{len(text_content)} characters)\n"
                        output += f"Full content is {len(text_content)} characters\n"
                    else:
                        output += text_content
                        output += f"\n{'='*60}\n"
                        output += f"✅ Showing the full content ({len(text_content)} characters)\n"
                
                except UnicodeDecodeError:
                    output += f"\n⚠️  File is binary and cannot be displayed as text\n"
                    output += f"File size: {len(content)} bytes\n"
                    
                    # Try to determine the file type
                    if content.startswith(b'%PDF'):
                        output += f"File type: PDF document\n"
                    elif content.startswith(b'\x50\x4b'):
                        output += f"File type: ZIP/Office document\n"
                    else:
                        output += f"File type: unknown binary file\n"
            
            except Exception as e:
                output += f"\n⚠️  Failed to read file content: {str(e)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ToolResult(
                output=None,
                error=f"Failed to get file: {str(e)}\nDetails: {error_detail[:500]}"
            )


# Export all tools
__all__ = [
    "CanvasListCourses",
    "CanvasGetAssignments",
    "CanvasSubmitAssignment",
    "CanvasGetModules",
    "CanvasGetModuleItems",
    "CanvasGetFiles",
    "CanvasGetFileInfo",
    "CanvasReadFile",
    "CanvasDownloadFile",
    "CanvasGetFolders",
    "CanvasGetFolderFiles",
    "CanvasSearchFiles",
    "CanvasGetDiscussions",
    "CanvasPostDiscussion",
    "CanvasGetAnnouncements",
    "CanvasGetCalendarEvents",
    "CanvasGetGrades",
    "CanvasGetPages",
    "CanvasGetPageContent",
    "CanvasGetQuizzes",
    "CanvasGetTodoItems",
    "CanvasGetUpcomingEvents",
    "CanvasGetGroups",
    "VectorStoreList",
    "VectorStoreSearch",
    "VectorStoreListFiles",
    "VectorStoreGetFile",
]


