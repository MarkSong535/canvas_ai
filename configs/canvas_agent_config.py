"""
Canvas Student Agent configuration.

Defines an agent tailored for student access to Canvas LMS with the complete Canvas API toolset available to student accounts.
"""

from typing import Optional

from src.tools.canvas_tools import (
    CanvasListCourses,
    CanvasGetAssignments,
    CanvasSubmitAssignment,
    CanvasGetModules,
    CanvasGetModuleItems,
    CanvasGetFiles,
    CanvasGetFileInfo,
    CanvasReadFile,
    CanvasGetFolders,
    CanvasGetFolderFiles,
    CanvasSearchFiles,
    CanvasGetDiscussions,
    CanvasPostDiscussion,
    CanvasGetAnnouncements,
    CanvasGetCalendarEvents,
    CanvasGetGrades,
    CanvasGetPages,
    CanvasGetPageContent,
    CanvasGetQuizzes,
    CanvasGetTodoItems,
    CanvasGetUpcomingEvents,
    CanvasGetGroups,
    VectorStoreList,
    VectorStoreSearch,
    VectorStoreListFiles,
    VectorStoreGetFile,
)
from src.tools.latex_tools import CheckLatex
from src.canvas_account import CanvasAccount


def build_tools(account: Optional[CanvasAccount] = None) -> list:
    """A fresh set of every Canvas tool available to students, calling Canvas as `account`.

    The WebSocket server builds one set per conversation so no two students share a tool. Without an account
    the tools read CANVAS_URL / CANVAS_ACCESS_TOKEN on every request (the command-line entry points).
    """
    return [
        CanvasListCourses(account),       # List enrolled courses
        CanvasGetAssignments(account),    # Retrieve assignments
        CanvasSubmitAssignment(account),  # Submit an assignment (never reaches live Canvas: blocked, or recorded in sandbox)
        CanvasGetModules(account),        # Retrieve course modules
        CanvasGetModuleItems(account),    # Retrieve module items
        CanvasGetFiles(account),          # List course files
        CanvasGetFileInfo(account),       # Retrieve file details
        CanvasReadFile(account),          # Read a file's text (sandbox: from the downloaded copy)
        CanvasGetFolders(account),        # List folders
        CanvasGetFolderFiles(account),    # List files inside a folder
        CanvasSearchFiles(account),       # Search files by keyword
        CanvasGetDiscussions(account),    # Retrieve discussions
        CanvasPostDiscussion(account),    # Post a discussion reply (never reaches live Canvas: blocked, or recorded in sandbox)
        CanvasGetAnnouncements(account),  # Retrieve announcements
        CanvasGetCalendarEvents(account), # Retrieve calendar events
        CanvasGetGrades(account),         # Retrieve grades
        CanvasGetPages(account),          # List course pages
        CanvasGetPageContent(account),    # Retrieve page content
        CanvasGetQuizzes(account),        # List quizzes
        CanvasGetTodoItems(account),      # Retrieve to-do items
        CanvasGetUpcomingEvents(account), # Retrieve upcoming events
        CanvasGetGroups(account),         # List groups
        VectorStoreList(account),         # List knowledge bases
        VectorStoreSearch(account),       # Search knowledge bases
        VectorStoreListFiles(account),    # List files inside a knowledge base
        VectorStoreGetFile(account),      # Read the contents of a file
        CheckLatex(),                     # Compile math / chemfig the way the student will see it
    ]


# Canvas student agent configuration
canvas_student_agent_config = dict(
    type="general_agent",
    name="canvas_student_agent",
    description="Canvas LMS study assistant that helps manage courses, assignments, discussions, and more",
    model_id="gpt-6-luna",  # Must be one of the models registered in src/models/models.py (all <= $5 / 1M tokens)
    max_steps=15,
    stream_outputs=True,     # Stream model output so the CLI / web UI can render the answer as it is generated
    max_history_turns=10,    # Multi-turn memory: earlier exchanges kept in context per conversation
    # Each question is routed once, before the agent starts, to a tier by difficulty (src/agent/routing.py).
    # If an answer struggled, the user is offered a retry one tier up; nothing escalates on its own.
    routing=dict(
        tiers={"simple": "gpt-5-nano", "standard": "gpt-6-luna", "hard": "gpt-5.4-mini"},
        classifier_model_id="gpt-5-nano",
    ),
    template_path="src/agent/general_agent/prompts/general_agent.yaml",  # Prompt template path
    
    # Every Canvas tool available to students (the WebSocket server builds its own per conversation)
    tools=build_tools(),
    
    # Customize the system prompt here or edit src/agent/general_agent/prompts/general_agent.yaml
)

# Expose the config for use in main.py and other entry points
agent_config = canvas_student_agent_config

