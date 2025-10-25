"""
Canvas LMS API 工具集 - 学生权限版本

这个文件包含了学生在Canvas上可以使用的所有API工具
使用 os.environ 获取 CANVAS_ACCESS_TOKEN 和 CANVAS_URL
"""

import os
import aiohttp
from typing import Optional, List, Dict, Any
from src.tools import AsyncTool, ToolResult
from src.registry import TOOL


class CanvasAPIBase(AsyncTool):
    """Canvas API 基类，处理通用的API调用逻辑"""
    
    def __init__(self):
        super().__init__()
        self.canvas_url = os.environ.get("CANVAS_URL", "https://canvas.instructure.com")
        self.access_token = os.environ.get("CANVAS_ACCESS_TOKEN")
        
        if not self.access_token:
            raise ValueError("未找到 CANVAS_ACCESS_TOKEN 环境变量")
        
        self.base_url = f"{self.canvas_url}/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None, 
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """发送API请求的通用方法"""
        url = f"{self.base_url}/{endpoint}"
        
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
                        return {"error": "资源未找到"}
                    else:
                        error_text = await response.text()
                        return {"error": f"API请求失败 (状态码: {response.status}): {error_text}"}
        except Exception as e:
            return {"error": f"请求异常: {str(e)}"}


@TOOL.register_module(name="canvas_list_courses", force=True)
class CanvasListCourses(CanvasAPIBase):
    """列出学生的所有课程"""
    
    name = "canvas_list_courses"
    description = "获取当前学生注册的所有课程列表，包括课程名称、ID、状态等信息"
    
    parameters = {
        "type": "object",
        "properties": {
            "enrollment_state": {
                "type": "string",
                "description": "课程注册状态: active(活跃), completed(已完成), 默认为active",
                "nullable": True
            },
            "include": {
                "type": "string",
                "description": "包含额外信息，可选: total_students, teachers, syllabus_body",
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
        """获取课程列表"""
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
            
            # 格式化输出
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
                output=f"找到 {len(courses_info)} 门课程:\n" + 
                       "\n".join([f"- [{c['id']}] {c['name']} ({c['course_code']})" 
                                 for c in courses_info]),
                error=None
            )
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取课程列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_assignments", force=True)
class CanvasGetAssignments(CanvasAPIBase):
    """获取课程的作业列表"""
    
    name = "canvas_get_assignments"
    description = "获取指定课程的所有作业，包括作业名称、截止日期、分数等信息"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "include_submission": {
                "type": "boolean",
                "description": "是否包含提交信息，默认为True",
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
        """获取作业列表"""
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
            
            # 格式化输出
            assignments_info = []
            for assignment in result:
                info = {
                    "id": assignment.get("id"),
                    "name": assignment.get("name"),
                    "due_at": assignment.get("due_at", "无截止日期"),
                    "points_possible": assignment.get("points_possible", 0),
                    "submission_types": assignment.get("submission_types", []),
                    "submission": assignment.get("submission", {})
                }
                assignments_info.append(info)
            
            output = f"课程 {course_id} 共有 {len(assignments_info)} 个作业:\n"
            for a in assignments_info:
                submission_status = "未提交"
                if a["submission"]:
                    submission_status = a["submission"].get("workflow_state", "未提交")
                output += f"- [{a['id']}] {a['name']} (截止: {a['due_at']}, 分值: {a['points_possible']}, 状态: {submission_status})\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取作业列表失败: {str(e)}")


@TOOL.register_module(name="canvas_submit_assignment", force=True)
class CanvasSubmitAssignment(CanvasAPIBase):
    """提交作业"""
    
    name = "canvas_submit_assignment"
    description = "提交指定课程的作业，支持文本、URL等提交类型"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "assignment_id": {
                "type": "string",
                "description": "作业ID"
            },
            "submission_type": {
                "type": "string",
                "description": "提交类型: online_text_entry, online_url, online_upload"
            },
            "body": {
                "type": "string",
                "description": "提交内容（文本提交时使用）",
                "nullable": True
            },
            "url": {
                "type": "string",
                "description": "提交的URL（URL提交时使用）",
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
        """提交作业"""
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
                output=f"作业提交成功！\n"
                       f"- 作业ID: {assignment_id}\n"
                       f"- 提交类型: {submission_type}\n"
                       f"- 提交时间: {result.get('submitted_at', '未知')}",
                error=None
            )
            
        except Exception as e:
            return ToolResult(output=None, error=f"提交作业失败: {str(e)}")


@TOOL.register_module(name="canvas_get_modules", force=True)
class CanvasGetModules(CanvasAPIBase):
    """获取课程模块列表"""
    
    name = "canvas_get_modules"
    description = "获取指定课程的所有模块和学习内容结构"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """获取模块列表"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/modules",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"课程 {course_id} 的模块结构:\n"
            for module in result:
                output += f"\n📚 模块 [{module.get('id')}]: {module.get('name')}\n"
                output += f"   状态: {module.get('workflow_state')}\n"
                output += f"   项目数: {module.get('items_count', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取模块列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_module_items", force=True)
class CanvasGetModuleItems(CanvasAPIBase):
    """获取模块中的具体内容项"""
    
    name = "canvas_get_module_items"
    description = "获取指定模块中的所有学习内容项（文件、页面、作业等）"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "module_id": {
                "type": "string",
                "description": "模块ID"
            }
        },
        "required": ["course_id", "module_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, module_id: str) -> ToolResult:
        """获取模块项"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/modules/{module_id}/items",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"模块 {module_id} 的内容:\n"
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
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取模块项失败: {str(e)}")


@TOOL.register_module(name="canvas_get_files", force=True)
class CanvasGetFiles(CanvasAPIBase):
    """获取课程文件列表"""
    
    name = "canvas_get_files"
    description = "获取指定课程的所有文件和资源"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "search_term": {
                "type": "string",
                "description": "搜索关键词（可选）",
                "nullable": True
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, search_term: str = "") -> ToolResult:
        """获取文件列表"""
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
            
            output = f"课程 {course_id} 的文件:\n"
            for file in result:
                size_mb = file.get("size", 0) / (1024 * 1024)
                output += f"📁 [{file.get('id')}] {file.get('display_name')} "
                output += f"({size_mb:.2f}MB, {file.get('content-type', '未知类型')})\n"
                output += f"   URL: {file.get('url')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取文件列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_discussions", force=True)
class CanvasGetDiscussions(CanvasAPIBase):
    """获取课程讨论主题列表"""
    
    name = "canvas_get_discussions"
    description = "获取指定课程的所有讨论话题"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """获取讨论列表"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/discussion_topics",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"课程 {course_id} 的讨论:\n"
            for topic in result:
                output += f"💬 [{topic.get('id')}] {topic.get('title')}\n"
                output += f"   发布时间: {topic.get('posted_at', '未知')}\n"
                output += f"   回复数: {topic.get('discussion_subentry_count', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取讨论列表失败: {str(e)}")


@TOOL.register_module(name="canvas_post_discussion", force=True)
class CanvasPostDiscussion(CanvasAPIBase):
    """在讨论中发帖"""
    
    name = "canvas_post_discussion"
    description = "在指定的讨论主题中发表回复或评论"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "topic_id": {
                "type": "string",
                "description": "讨论主题ID"
            },
            "message": {
                "type": "string",
                "description": "发帖内容"
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
        """发表讨论回复"""
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
                output=f"讨论回复发表成功！\n"
                       f"- 主题ID: {topic_id}\n"
                       f"- 发表时间: {result.get('created_at', '未知')}",
                error=None
            )
            
        except Exception as e:
            return ToolResult(output=None, error=f"发表讨论失败: {str(e)}")


@TOOL.register_module(name="canvas_get_announcements", force=True)
class CanvasGetAnnouncements(CanvasAPIBase):
    """获取课程公告"""
    
    name = "canvas_get_announcements"
    description = "获取所有课程的最新公告"
    
    parameters = {
        "type": "object",
        "properties": {
            "context_codes": {
                "type": "string",
                "description": "课程ID列表，格式: course_123,course_456（可选，留空则获取所有课程）",
                "nullable": True
            }
        },
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, context_codes: str = "") -> ToolResult:
        """获取公告列表"""
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
            
            output = "📢 最新公告:\n"
            for announcement in result:
                output += f"\n标题: {announcement.get('title')}\n"
                output += f"发布时间: {announcement.get('posted_at', '未知')}\n"
                output += f"内容: {announcement.get('message', '无内容')[:200]}...\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取公告失败: {str(e)}")


@TOOL.register_module(name="canvas_get_calendar_events", force=True)
class CanvasGetCalendarEvents(CanvasAPIBase):
    """获取日历事件"""
    
    name = "canvas_get_calendar_events"
    description = "获取学生的日历事件，包括课程活动、作业截止日期等"
    
    parameters = {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "description": "开始日期，格式: YYYY-MM-DD（可选）",
                "nullable": True
            },
            "end_date": {
                "type": "string",
                "description": "结束日期，格式: YYYY-MM-DD（可选）",
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
        """获取日历事件"""
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
            
            output = "📅 日历事件:\n"
            for event in result:
                output += f"\n🗓️ {event.get('title')}\n"
                output += f"   时间: {event.get('start_at', '未知')}\n"
                output += f"   类型: {event.get('type', '未知')}\n"
                if event.get('description'):
                    output += f"   描述: {event.get('description')[:100]}...\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取日历事件失败: {str(e)}")


@TOOL.register_module(name="canvas_get_grades", force=True)
class CanvasGetGrades(CanvasAPIBase):
    """获取课程成绩"""
    
    name = "canvas_get_grades"
    description = "获取学生在指定课程中的成绩信息"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """获取成绩"""
        try:
            # 获取当前用户ID
            user_result = await self._make_request("GET", "users/self")
            if isinstance(user_result, dict) and "error" in user_result:
                return ToolResult(output=None, error=user_result["error"])
            
            user_id = user_result.get("id")
            
            # 获取注册信息（包含成绩）
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/enrollments",
                params={"user_id": user_id}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"课程 {course_id} 的成绩:\n"
            for enrollment in result:
                grades = enrollment.get("grades", {})
                output += f"📊 当前成绩: {grades.get('current_grade', '暂无')}\n"
                output += f"   当前分数: {grades.get('current_score', '暂无')}\n"
                output += f"   最终成绩: {grades.get('final_grade', '暂无')}\n"
                output += f"   最终分数: {grades.get('final_score', '暂无')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取成绩失败: {str(e)}")


@TOOL.register_module(name="canvas_get_pages", force=True)
class CanvasGetPages(CanvasAPIBase):
    """获取课程页面列表"""
    
    name = "canvas_get_pages"
    description = "获取指定课程的所有页面（Wiki页面）"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """获取页面列表"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/pages",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"课程 {course_id} 的页面:\n"
            for page in result:
                output += f"📄 {page.get('title')}\n"
                output += f"   URL: {page.get('url')}\n"
                output += f"   更新时间: {page.get('updated_at', '未知')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取页面列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_page_content", force=True)
class CanvasGetPageContent(CanvasAPIBase):
    """获取页面详细内容"""
    
    name = "canvas_get_page_content"
    description = "获取指定页面的完整内容"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "page_url": {
                "type": "string",
                "description": "页面URL或标题"
            }
        },
        "required": ["course_id", "page_url"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, page_url: str) -> ToolResult:
        """获取页面内容"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/pages/{page_url}"
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📄 页面: {result.get('title')}\n"
            output += f"更新时间: {result.get('updated_at', '未知')}\n\n"
            output += f"内容:\n{result.get('body', '无内容')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取页面内容失败: {str(e)}")


@TOOL.register_module(name="canvas_get_quizzes", force=True)
class CanvasGetQuizzes(CanvasAPIBase):
    """获取课程测验列表"""
    
    name = "canvas_get_quizzes"
    description = "获取指定课程的所有测验"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """获取测验列表"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/quizzes",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"课程 {course_id} 的测验:\n"
            for quiz in result:
                output += f"✏️ [{quiz.get('id')}] {quiz.get('title')}\n"
                output += f"   类型: {quiz.get('quiz_type', '未知')}\n"
                output += f"   分数: {quiz.get('points_possible', 0)}\n"
                output += f"   截止时间: {quiz.get('due_at', '无截止时间')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取测验列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_todo_items", force=True)
class CanvasGetTodoItems(CanvasAPIBase):
    """获取待办事项"""
    
    name = "canvas_get_todo_items"
    description = "获取学生的待办事项列表，包括即将到期的作业和任务"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """获取待办事项"""
        try:
            result = await self._make_request("GET", "users/self/todo")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "📝 待办事项:\n"
            for item in result:
                assignment = item.get("assignment", {})
                output += f"\n• {assignment.get('name', '未知任务')}\n"
                output += f"  课程: {item.get('context_name', '未知')}\n"
                output += f"  截止: {assignment.get('due_at', '无截止时间')}\n"
                output += f"  分数: {assignment.get('points_possible', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取待办事项失败: {str(e)}")


@TOOL.register_module(name="canvas_get_upcoming_events", force=True)
class CanvasGetUpcomingEvents(CanvasAPIBase):
    """获取即将到来的事件"""
    
    name = "canvas_get_upcoming_events"
    description = "获取学生即将到来的所有事件和活动"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """获取即将事件"""
        try:
            result = await self._make_request("GET", "users/self/upcoming_events")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "🗓️ 即将到来的事件:\n"
            for event in result:
                output += f"\n• {event.get('title', '未知事件')}\n"
                output += f"  时间: {event.get('start_at', '未知')}\n"
                output += f"  类型: {event.get('type', '未知')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取即将事件失败: {str(e)}")


@TOOL.register_module(name="canvas_get_groups", force=True)
class CanvasGetGroups(CanvasAPIBase):
    """获取学生小组"""
    
    name = "canvas_get_groups"
    description = "获取学生参与的所有小组"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """获取小组列表"""
        try:
            result = await self._make_request("GET", "users/self/groups")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = "👥 我的小组:\n"
            for group in result:
                output += f"\n• [{group.get('id')}] {group.get('name')}\n"
                output += f"  成员数: {group.get('members_count', 0)}\n"
                output += f"  课程: {group.get('course_id', '未知')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取小组列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_file_info", force=True)
class CanvasGetFileInfo(CanvasAPIBase):
    """获取文件详细信息"""
    
    name = "canvas_get_file_info"
    description = "获取指定文件的详细信息，包括下载链接、大小、类型等"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "文件ID"
            }
        },
        "required": ["file_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, file_id: str) -> ToolResult:
        """获取文件信息"""
        try:
            result = await self._make_request("GET", f"files/{file_id}")
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📁 文件信息:\n"
            output += f"名称: {result.get('display_name')}\n"
            output += f"ID: {result.get('id')}\n"
            output += f"大小: {result.get('size', 0) / (1024*1024):.2f} MB\n"
            output += f"类型: {result.get('content-type', '未知')}\n"
            output += f"修改时间: {result.get('modified_at', '未知')}\n"
            output += f"下载链接: {result.get('url')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取文件信息失败: {str(e)}")


@TOOL.register_module(name="canvas_download_file", force=True)
class CanvasDownloadFile(CanvasAPIBase):
    """下载并读取文件内容"""
    
    name = "canvas_download_file"
    description = "下载指定文件并读取其内容（支持文本文件、PDF、图片等）"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "文件ID"
            },
            "read_content": {
                "type": "boolean",
                "description": "是否读取文件内容，默认True",
                "nullable": True
            }
        },
        "required": ["file_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, file_id: str, read_content: bool = True) -> ToolResult:
        """下载并读取文件"""
        try:
            # 先获取文件的 public_url（学生权限需要通过这个API）
            public_url_result = await self._make_request("GET", f"files/{file_id}/public_url")
            
            if isinstance(public_url_result, dict) and "error" in public_url_result:
                # 如果获取public_url失败，尝试获取文件基本信息
                file_info = await self._make_request("GET", f"files/{file_id}")
                if isinstance(file_info, dict) and "error" in file_info:
                    return ToolResult(output=None, error=file_info["error"])
                
                # 返回文件信息但无法下载
                return ToolResult(
                    output=f"📁 文件: {file_info.get('display_name')}\n"
                           f"权限限制: 无法下载此文件（可能需要在Canvas网页上直接访问）\n"
                           f"文件ID: {file_id}",
                    error=None
                )
            
            # 获取public_url和文件信息
            file_url = public_url_result.get("public_url")
            
            # 再获取文件详细信息
            file_info = await self._make_request("GET", f"files/{file_id}")
            if isinstance(file_info, dict) and "error" in file_info:
                return ToolResult(output=None, error=file_info["error"])
            
            file_name = file_info.get("display_name")
            content_type = file_info.get("content-type", "")
            
            if not read_content:
                return ToolResult(
                    output=f"文件下载链接: {file_url}",
                    error=None
                )
            
            # 下载文件内容（不需要认证头，因为public_url已包含认证）
            async with aiohttp.ClientSession() as session:
                async with session.get(file_url) as response:
                    if response.status == 200:
                        # 根据文件类型处理
                        if "text" in content_type or file_name.endswith(('.txt', '.md', '.py', '.java', '.cpp', '.c')):
                            # 文本文件
                            content = await response.text()
                            output = f"📄 文件: {file_name}\n"
                            output += f"类型: 文本文件\n"
                            output += f"内容:\n{'-'*60}\n{content}\n{'-'*60}"
                            
                        elif "pdf" in content_type or file_name.endswith('.pdf'):
                            # PDF 文件
                            output = f"📕 PDF 文件: {file_name}\n"
                            output += f"大小: {file_info.get('size', 0) / (1024*1024):.2f} MB\n"
                            output += f"下载链接: {file_url}\n"
                            output += f"提示: PDF内容需要专门的PDF阅读工具处理"
                            
                        elif any(ext in content_type for ext in ["image", "png", "jpg", "jpeg", "gif"]):
                            # 图片文件
                            output = f"🖼️ 图片文件: {file_name}\n"
                            output += f"类型: {content_type}\n"
                            output += f"大小: {file_info.get('size', 0) / 1024:.2f} KB\n"
                            output += f"预览链接: {file_url}"
                            
                        else:
                            # 其他文件类型
                            output = f"📎 文件: {file_name}\n"
                            output += f"类型: {content_type}\n"
                            output += f"大小: {file_info.get('size', 0) / (1024*1024):.2f} MB\n"
                            output += f"下载链接: {file_url}"
                        
                        return ToolResult(output=output, error=None)
                    else:
                        return ToolResult(
                            output=None, 
                            error=f"下载文件失败 (状态码: {response.status})"
                        )
            
        except Exception as e:
            return ToolResult(output=None, error=f"下载文件失败: {str(e)}")


@TOOL.register_module(name="canvas_get_folders", force=True)
class CanvasGetFolders(CanvasAPIBase):
    """获取课程文件夹列表"""
    
    name = "canvas_get_folders"
    description = "获取指定课程的文件夹结构"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            }
        },
        "required": ["course_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str) -> ToolResult:
        """获取文件夹列表"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/folders",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📂 课程 {course_id} 的文件夹:\n"
            for folder in result:
                output += f"• [{folder.get('id')}] {folder.get('full_name')}\n"
                output += f"  文件数: {folder.get('files_count', 0)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取文件夹列表失败: {str(e)}")


@TOOL.register_module(name="canvas_get_folder_files", force=True)
class CanvasGetFolderFiles(CanvasAPIBase):
    """获取文件夹中的文件"""
    
    name = "canvas_get_folder_files"
    description = "获取指定文件夹中的所有文件"
    
    parameters = {
        "type": "object",
        "properties": {
            "folder_id": {
                "type": "string",
                "description": "文件夹ID"
            }
        },
        "required": ["folder_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, folder_id: str) -> ToolResult:
        """获取文件夹中的文件"""
        try:
            result = await self._make_request(
                "GET",
                f"folders/{folder_id}/files",
                params={"per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"📂 文件夹 {folder_id} 中的文件:\n"
            for file in result:
                size_mb = file.get('size', 0) / (1024 * 1024)
                output += f"📄 [{file.get('id')}] {file.get('display_name')}\n"
                output += f"   大小: {size_mb:.2f} MB\n"
                output += f"   类型: {file.get('content-type', '未知')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取文件夹文件失败: {str(e)}")


@TOOL.register_module(name="canvas_search_files", force=True)
class CanvasSearchFiles(CanvasAPIBase):
    """搜索课程中的文件"""
    
    name = "canvas_search_files"
    description = "在指定课程中搜索文件"
    
    parameters = {
        "type": "object",
        "properties": {
            "course_id": {
                "type": "string",
                "description": "课程ID"
            },
            "search_term": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["course_id", "search_term"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, course_id: str, search_term: str) -> ToolResult:
        """搜索文件"""
        try:
            result = await self._make_request(
                "GET",
                f"courses/{course_id}/files",
                params={"search_term": search_term, "per_page": 50}
            )
            
            if isinstance(result, dict) and "error" in result:
                return ToolResult(output=None, error=result["error"])
            
            output = f"🔍 搜索 '{search_term}' 的结果:\n"
            if len(result) == 0:
                output += "未找到匹配的文件"
            else:
                for file in result:
                    output += f"\n📄 {file.get('display_name')}\n"
                    output += f"   文件ID: {file.get('id')}\n"
                    output += f"   大小: {file.get('size', 0) / 1024:.2f} KB\n"
                    output += f"   下载: {file.get('url')}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"搜索文件失败: {str(e)}")


# 导出所有工具
__all__ = [
    "CanvasListCourses",
    "CanvasGetAssignments",
    "CanvasSubmitAssignment",
    "CanvasGetModules",
    "CanvasGetModuleItems",
    "CanvasGetFiles",
    "CanvasGetFileInfo",
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
]


