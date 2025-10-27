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
        if "http://" in self.canvas_url:
            self.canvas_url = self.canvas_url.replace("http://", "https://")
        if "http" not in self.canvas_url:
            self.canvas_url = "https://" + self.canvas_url
        
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
                        return {"error": "Resource not found"}
                    else:
                        error_text = await response.text()
                        return {"error": f"API Request Failed (Status Code {response.status}): {error_text}"}
        except Exception as e:
            return {"error": f"Request Error: {str(e)}"}


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


# @TOOL.register_module(name="canvas_submit_assignment", force=True)
# class CanvasSubmitAssignment(CanvasAPIBase):
#     """提交作业"""
    
#     name = "canvas_submit_assignment"
#     description = "提交指定课程的作业，支持文本、URL等提交类型"
    
#     parameters = {
#         "type": "object",
#         "properties": {
#             "course_id": {
#                 "type": "string",
#                 "description": "课程ID"
#             },
#             "assignment_id": {
#                 "type": "string",
#                 "description": "作业ID"
#             },
#             "submission_type": {
#                 "type": "string",
#                 "description": "提交类型: online_text_entry, online_url, online_upload"
#             },
#             "body": {
#                 "type": "string",
#                 "description": "提交内容（文本提交时使用）",
#                 "nullable": True
#             },
#             "url": {
#                 "type": "string",
#                 "description": "提交的URL（URL提交时使用）",
#                 "nullable": True
#             }
#         },
#         "required": ["course_id", "assignment_id", "submission_type"],
#         "additionalProperties": False
#     }
    
#     output_type = "any"
    
#     async def forward(
#         self, 
#         course_id: str, 
#         assignment_id: str,
#         submission_type: str,
#         body: str = "",
#         url: str = ""
#     ) -> ToolResult:
#         """提交作业"""
#         try:
#             data = {
#                 "submission": {
#                     "submission_type": submission_type
#                 }
#             }
            
#             if submission_type == "online_text_entry" and body:
#                 data["submission"]["body"] = body
#             elif submission_type == "online_url" and url:
#                 data["submission"]["url"] = url
            
#             result = await self._make_request(
#                 "POST",
#                 f"courses/{course_id}/assignments/{assignment_id}/submissions",
#                 data=data
#             )
            
#             if isinstance(result, dict) and "error" in result:
#                 return ToolResult(output=None, error=result["error"])
            
#             return ToolResult(
#                 output=f"作业提交成功！\n"
#                        f"- 作业ID: {assignment_id}\n"
#                        f"- 提交类型: {submission_type}\n"
#                        f"- 提交时间: {result.get('submitted_at', '未知')}",
#                 error=None
#             )
            
#         except Exception as e:
#             return ToolResult(output=None, error=f"提交作业失败: {str(e)}")


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


# @TOOL.register_module(name="canvas_post_discussion", force=True)
# class CanvasPostDiscussion(CanvasAPIBase):
#     """在讨论中发帖"""
    
#     name = "canvas_post_discussion"
#     description = "在指定的讨论主题中发表回复或评论"
    
#     parameters = {
#         "type": "object",
#         "properties": {
#             "course_id": {
#                 "type": "string",
#                 "description": "课程ID"
#             },
#             "topic_id": {
#                 "type": "string",
#                 "description": "讨论主题ID"
#             },
#             "message": {
#                 "type": "string",
#                 "description": "发帖内容"
#             }
#         },
#         "required": ["course_id", "topic_id", "message"],
#         "additionalProperties": False
#     }
    
#     output_type = "any"
    
#     async def forward(
#         self, 
#         course_id: str, 
#         topic_id: str, 
#         message: str
#     ) -> ToolResult:
#         """发表讨论回复"""
#         try:
#             data = {"message": message}
            
#             result = await self._make_request(
#                 "POST",
#                 f"courses/{course_id}/discussion_topics/{topic_id}/entries",
#                 data=data
#             )
            
#             if isinstance(result, dict) and "error" in result:
#                 return ToolResult(output=None, error=result["error"])
            
#             return ToolResult(
#                 output=f"讨论回复发表成功！\n"
#                        f"- 主题ID: {topic_id}\n"
#                        f"- 发表时间: {result.get('created_at', '未知')}",
#                 error=None
#             )
            
#         except Exception as e:
#             return ToolResult(output=None, error=f"发表讨论失败: {str(e)}")


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


@TOOL.register_module(name="vector_store_list", force=True)
class VectorStoreList(AsyncTool):
    """列出所有可用的 Vector Stores"""
    
    name = "vector_store_list"
    description = "列出所有可用的课程知识库（Vector Stores），显示每个知识库的ID、名称和文件数量"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self) -> ToolResult:
        """获取 Vector Store 列表"""
        try:
            # 导入 OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI 库未安装，请运行: pip install openai"
                )
            
            # 获取 API Key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="未配置 OPENAI_API_KEY，请在 .env 文件中添加"
                )
            
            # 创建客户端
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # 获取 Vector Stores
            response = client.vector_stores.list(limit=100)
            vector_stores = list(response.data)
            
            if not vector_stores:
                return ToolResult(
                    output="📋 当前没有可用的知识库\n请先运行 file_index_downloader.py 创建知识库",
                    error=None
                )
            
            # 格式化输出
            output = f"📚 找到 {len(vector_stores)} 个课程知识库:\n\n"
            
            for i, vs in enumerate(vector_stores, 1):
                file_count = vs.file_counts.total if hasattr(vs, 'file_counts') else 0
                output += f"{i}. [{vs.id}] {vs.name}\n"
                output += f"   📁 文件数量: {file_count}\n"
                if hasattr(vs, 'created_at'):
                    output += f"   📅 创建时间: {vs.created_at}\n"
                output += "\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            return ToolResult(output=None, error=f"获取知识库列表失败: {str(e)}")


@TOOL.register_module(name="vector_store_search", force=True)
class VectorStoreSearch(AsyncTool):
    """在 Vector Store 中搜索相关内容"""
    
    name = "vector_store_search"
    description = "在指定的课程知识库中搜索相关内容，可以回答关于课程材料、讲义、作业等的问题"
    
    parameters = {
        "type": "object",
        "properties": {
            "vector_store_id": {
                "type": "string",
                "description": "Vector Store ID（从 vector_store_list 工具获取）"
            },
            "query": {
                "type": "string",
                "description": "搜索查询，例如：'这门课的主要内容是什么？'、'作业1的要求'等"
            },
            "max_results": {
                "type": "integer",
                "description": "返回的最大结果数（默认5）",
                "nullable": True
            }
        },
        "required": ["vector_store_id", "query"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, vector_store_id: str, query: str, max_results: int = 5) -> ToolResult:
        """搜索 Vector Store"""
        try:
            # 导入 OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI 库未安装，请运行: pip install openai"
                )
            
            # 获取 API Key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="未配置 OPENAI_API_KEY，请在 .env 文件中添加"
                )
            
            # 创建客户端
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # 执行搜索
            response = client.vector_stores.search(
                vector_store_id=vector_store_id,
                query=query,
                max_num_results=max_results
            )
            
            # 检查结果
            if not response or not hasattr(response, 'data') or not response.data:
                return ToolResult(
                    output=f"🔍 搜索查询: \"{query}\"\n❌ 未找到相关内容",
                    error=None
                )
            
            # 格式化输出
            output = f"🔍 搜索查询: \"{query}\"\n"
            output += f"📊 找到 {len(response.data)} 个相关结果:\n\n"
            
            for i, result in enumerate(response.data, 1):
                output += f"{'='*60}\n"
                output += f"结果 {i}:\n"
                
                # 相关性分数
                if hasattr(result, 'score'):
                    output += f"📈 相关性: {result.score:.2%}\n"
                
                # 文件名
                if hasattr(result, 'filename'):
                    output += f"📄 来源: {result.filename}\n"
                
                # 元数据
                if hasattr(result, 'attributes') and result.attributes:
                    output += f"🏷️  属性: {result.attributes}\n"
                
                # 内容
                if hasattr(result, 'content'):
                    content = result.content
                    # 限制长度
                    if len(content) > 800:
                        content = content[:800] + "...\n(内容已截断)"
                    output += f"\n📝 内容:\n{content}\n"
                
                output += "\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ToolResult(
                output=None,
                error=f"搜索失败: {str(e)}\n详情: {error_detail[:500]}"
            )


@TOOL.register_module(name="vector_store_list_files", force=True)
class VectorStoreListFiles(AsyncTool):
    """列出 Vector Store 中的所有文件"""
    
    name = "vector_store_list_files"
    description = "列出指定知识库中的所有文件，显示文件ID、名称、状态等信息，可选择读取文件内容"
    
    parameters = {
        "type": "object",
        "properties": {
            "vector_store_id": {
                "type": "string",
                "description": "Vector Store ID（从 vector_store_list 工具获取）"
            },
            "read_content": {
                "type": "boolean",
                "description": "是否读取文件内容（默认False，仅列出文件信息）",
                "nullable": True
            },
            "limit": {
                "type": "integer",
                "description": "返回的最大文件数（默认100，设置为0或负数表示获取所有文件）",
                "nullable": True
            }
        },
        "required": ["vector_store_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, vector_store_id: str, read_content: bool = False, limit: int = 100) -> ToolResult:
        """列出 Vector Store 文件"""
        try:
            # 导入 OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI 库未安装，请运行: pip install openai"
                )
            
            # 获取 API Key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="未配置 OPENAI_API_KEY，请在 .env 文件中添加"
                )
            
            # 创建客户端
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # 获取 Vector Store 文件列表
            files = []
            
            # 如果 limit <= 0，获取所有文件（分页）
            if limit <= 0:
                after = None
                while True:
                    if after:
                        response = client.vector_stores.files.list(
                            vector_store_id=vector_store_id,
                            limit=100,  # 每页最多100个
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
                    
                    # 检查是否还有更多数据
                    if hasattr(response, 'has_more') and response.has_more:
                        # 使用最后一个文件的 ID 作为 after 参数
                        after = batch_files[-1].id
                    else:
                        break
            else:
                # 限制数量获取
                response = client.vector_stores.files.list(
                    vector_store_id=vector_store_id,
                    limit=limit
                )
                files = list(response.data)
            
            if not files:
                return ToolResult(
                    output=f"📋 Vector Store [{vector_store_id}] 中没有文件",
                    error=None
                )
            
            # 格式化输出
            output = f"📚 Vector Store [{vector_store_id}] 文件列表:\n"
            output += f"找到 {len(files)} 个文件\n\n"
            
            for i, file in enumerate(files, 1):
                output += f"{'='*60}\n"
                output += f"文件 {i}:\n"
                output += f"🆔 File ID: {file.id}\n"
                
                if hasattr(file, 'status'):
                    status_emoji = "✅" if file.status == "completed" else "⏳"
                    output += f"{status_emoji} 状态: {file.status}\n"
                
                if hasattr(file, 'created_at'):
                    from datetime import datetime
                    created = datetime.fromtimestamp(file.created_at)
                    output += f"📅 创建时间: {created.strftime('%Y-%m-%d %H:%M:%S')}\n"
                
                # 总是获取文件基本信息（文件名、大小等）
                try:
                    # 获取文件详细信息
                    file_info = client.files.retrieve(file.id)
                    
                    if hasattr(file_info, 'filename'):
                        output += f"📄 文件名: {file_info.filename}\n"
                    
                    if hasattr(file_info, 'bytes'):
                        size_kb = file_info.bytes / 1024
                        if size_kb >= 1024:
                            output += f"📦 大小: {size_kb / 1024:.2f} MB\n"
                        else:
                            output += f"📦 大小: {size_kb:.2f} KB\n"
                    
                    if hasattr(file_info, 'purpose'):
                        output += f"🎯 用途: {file_info.purpose}\n"
                    
                    # 如果需要读取内容
                    if read_content and file.status == "completed":
                        # 尝试读取文件内容
                        try:
                            content_response = client.files.content(file.id)
                            content = content_response.read()
                            
                            # 尝试解码为文本
                            try:
                                text_content = content.decode('utf-8')
                                # 限制长度
                                if len(text_content) > 1000:
                                    text_content = text_content[:1000] + "\n...(内容已截断)"
                                output += f"\n📝 内容预览:\n{text_content}\n"
                            except:
                                output += f"\n⚠️  无法显示文件内容（非文本文件或编码问题）\n"
                                output += f"   文件大小: {len(content)} 字节\n"
                        except Exception as e:
                            output += f"\n⚠️  读取内容失败: {str(e)}\n"
                
                except Exception as e:
                    output += f"\n⚠️  获取文件信息失败: {str(e)}\n"
                
                output += "\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ToolResult(
                output=None,
                error=f"获取文件列表失败: {str(e)}\n详情: {error_detail[:500]}"
            )


@TOOL.register_module(name="vector_store_get_file", force=True)
class VectorStoreGetFile(AsyncTool):
    """根据 file_id 获取和读取文件内容"""
    
    name = "vector_store_get_file"
    description = "根据 file_id 获取文件详细信息并读取内容，支持文本文件的完整内容展示"
    
    parameters = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "OpenAI File ID（从 vector_store_list_files 工具获取）"
            },
            "max_length": {
                "type": "integer",
                "description": "最大显示长度（默认5000字符）",
                "nullable": True
            }
        },
        "required": ["file_id"],
        "additionalProperties": False
    }
    
    output_type = "any"
    
    async def forward(self, file_id: str, max_length: int = 5000) -> ToolResult:
        """获取文件内容"""
        try:
            # 导入 OpenAI
            try:
                from openai import OpenAI
            except ImportError:
                return ToolResult(
                    output=None,
                    error="OpenAI 库未安装，请运行: pip install openai"
                )
            
            # 获取 API Key
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if not openai_api_key:
                return ToolResult(
                    output=None,
                    error="未配置 OPENAI_API_KEY，请在 .env 文件中添加"
                )
            
            # 创建客户端
            client = OpenAI(
                api_key=openai_api_key,
                default_headers={"OpenAI-Beta": "assistants=v2"}
            )
            
            # 获取文件信息
            file_info = client.files.retrieve(file_id)
            
            output = f"📄 文件详细信息:\n"
            output += f"{'='*60}\n"
            output += f"🆔 File ID: {file_info.id}\n"
            
            if hasattr(file_info, 'filename'):
                output += f"📝 文件名: {file_info.filename}\n"
            
            if hasattr(file_info, 'purpose'):
                output += f"🎯 用途: {file_info.purpose}\n"
            
            if hasattr(file_info, 'bytes'):
                size_kb = file_info.bytes / 1024
                size_mb = size_kb / 1024
                if size_mb >= 1:
                    output += f"📦 大小: {size_mb:.2f} MB\n"
                else:
                    output += f"📦 大小: {size_kb:.2f} KB\n"
            
            if hasattr(file_info, 'created_at'):
                from datetime import datetime
                created = datetime.fromtimestamp(file_info.created_at)
                output += f"📅 创建时间: {created.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if hasattr(file_info, 'status'):
                status_emoji = "✅" if file_info.status == "processed" else "⏳"
                output += f"{status_emoji} 状态: {file_info.status}\n"
            
            output += f"\n{'='*60}\n"
            
            # 尝试读取文件内容
            try:
                content_response = client.files.content(file_id)
                content = content_response.read()
                
                # 尝试解码为文本
                try:
                    text_content = content.decode('utf-8')
                    
                    output += f"\n📖 文件内容:\n"
                    output += f"{'='*60}\n"
                    
                    if len(text_content) > max_length:
                        output += text_content[:max_length]
                        output += f"\n\n{'='*60}\n"
                        output += f"⚠️  内容已截断（显示 {max_length}/{len(text_content)} 字符）\n"
                        output += f"完整内容共 {len(text_content)} 字符\n"
                    else:
                        output += text_content
                        output += f"\n{'='*60}\n"
                        output += f"✅ 已显示完整内容（{len(text_content)} 字符）\n"
                
                except UnicodeDecodeError:
                    output += f"\n⚠️  文件是二进制格式，无法显示为文本\n"
                    output += f"文件大小: {len(content)} 字节\n"
                    
                    # 尝试判断文件类型
                    if content.startswith(b'%PDF'):
                        output += f"文件类型: PDF 文档\n"
                    elif content.startswith(b'\x50\x4b'):
                        output += f"文件类型: ZIP/Office 文档\n"
                    else:
                        output += f"文件类型: 未知二进制文件\n"
            
            except Exception as e:
                output += f"\n⚠️  读取文件内容失败: {str(e)}\n"
            
            return ToolResult(output=output, error=None)
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return ToolResult(
                output=None,
                error=f"获取文件失败: {str(e)}\n详情: {error_detail[:500]}"
            )


# 导出所有工具
__all__ = [
    "CanvasListCourses",
    "CanvasGetAssignments",
    # "CanvasSubmitAssignment",
    "CanvasGetModules",
    "CanvasGetModuleItems",
    "CanvasGetFiles",
    "CanvasGetFileInfo",
    "CanvasDownloadFile",
    "CanvasGetFolders",
    "CanvasGetFolderFiles",
    "CanvasSearchFiles",
    "CanvasGetDiscussions",
    # "CanvasPostDiscussion",
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


