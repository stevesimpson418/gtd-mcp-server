"""FastMCP tool definitions for Todoist."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from gtd_mcp.todoist.client import TodoistClient

logger = logging.getLogger(__name__)


def register_todoist_tools(mcp: FastMCP) -> None:
    """Register all Todoist tools with the MCP server.

    Requires TODOIST_API_TOKEN env var. If missing, logs a warning
    and skips registration (server still starts without Todoist tools).
    """
    token = os.getenv("TODOIST_API_TOKEN")
    if not token:
        logger.warning("TODOIST_API_TOKEN not set — Todoist tools disabled")
        return

    client = TodoistClient(token)

    @mcp.tool(annotations={"readOnlyHint": True})
    def list_todoist_projects() -> list[dict]:
        """List all Todoist projects.

        Returns every project in the user's account with its ID and name.
        Use this to discover valid project names for other tools.

        Example:
            list_todoist_projects()

        Returns:
            [{"id": "12345", "name": "Inbox"}, {"id": "67890", "name": "Work Tasks"}, ...]
        """
        return client.list_projects()

    @mcp.tool(annotations={"readOnlyHint": True})
    def get_project_tasks(
        project: Annotated[
            str,
            Field(
                description=(
                    "Project name as it appears in Todoist (case-insensitive). "
                    "Use list_todoist_projects() to see available projects."
                )
            ),
        ],
    ) -> list[dict]:
        """Get all tasks from a Todoist project.

        Returns tasks with: id, content, description, labels, due, priority, project_id.

        Args:
            project: The project name, e.g. "Inbox", "Active", "Backlog".

        Example:
            get_project_tasks(project="Inbox")
            get_project_tasks(project="My Custom Project")

        Returns:
            [{"id": "123", "content": "Buy milk", "labels": ["Shopping"],
              "due": {"date": "2026-03-10", ...}, "priority": 1, ...}]
        """
        return client.get_tasks(project)

    @mcp.tool(annotations={"readOnlyHint": True})
    def list_todoist_labels() -> list[dict]:
        """List all personal Todoist labels.

        Returns every label with its ID, name, and color.
        Labels are referenced by name in task operations.

        Example:
            list_todoist_labels()

        Returns:
            [{"id": "111", "name": "Home", "color": "blue"}, ...]
        """
        return client.get_labels()

    @mcp.tool
    def create_task(
        content: Annotated[str, Field(description="The task title/content")],
        project: Annotated[
            str,
            Field(
                default="Inbox",
                description=(
                    "Project name to create the task in (case-insensitive). "
                    "Defaults to 'Inbox'. Use list_todoist_projects() for valid names."
                ),
            ),
        ] = "Inbox",
        labels: Annotated[
            list[str],
            Field(
                default=[],
                description=(
                    "Labels to apply, by name. " "Use list_todoist_labels() for available labels."
                ),
            ),
        ] = [],
        due_date: Annotated[
            str,
            Field(
                default="",
                description=(
                    "Due date — natural language ('tomorrow', 'next Monday') "
                    "or date string ('2026-03-15')."
                ),
            ),
        ] = "",
        description: Annotated[
            str,
            Field(default="", description="Optional longer description for the task."),
        ] = "",
    ) -> dict:
        """Create a new task in Todoist.

        Creates a task with the given content in the specified project.
        Optionally attach labels, a due date, and a description.

        Args:
            content: The task title, e.g. "Buy groceries".
            project: Target project name. Defaults to "Inbox".
            labels: List of label names to apply, e.g. ["Shopping", "Home"].
            due_date: When it's due — "tomorrow", "next Friday", or "2026-03-15".
            description: Additional notes or details.

        Example:
            create_task(content="Buy groceries", project="Active", labels=["Shopping"],
                        due_date="tomorrow")

        Returns:
            {"id": "123", "content": "Buy groceries", "labels": ["Shopping"], ...}
        """
        return client.create_task(
            content=content,
            project=project,
            labels=labels or None,
            due_date=due_date or None,
            description=description or None,
        )

    @mcp.tool
    def update_task(
        task_id: Annotated[str, Field(description="The Todoist task ID to update")],
        content: Annotated[
            str,
            Field(
                default="",
                description="New task title/content. Leave empty to keep current.",
            ),
        ] = "",
        labels: Annotated[
            list[str],
            Field(
                default=[],
                description=(
                    "New labels (replaces existing). Use label names, not IDs. "
                    "Leave empty to keep current."
                ),
            ),
        ] = [],
        due_date: Annotated[
            str,
            Field(
                default="",
                description=(
                    "New due date — natural language or date string. "
                    "Leave empty to keep current."
                ),
            ),
        ] = "",
        description: Annotated[
            str,
            Field(
                default="",
                description="New description text. Leave empty to keep current.",
            ),
        ] = "",
    ) -> dict:
        """Update fields on an existing Todoist task.

        Only specified fields are changed; others remain untouched.
        Note: setting labels replaces all existing labels on the task.

        Args:
            task_id: The task ID (from get_project_tasks or create_task).
            content: New title. Leave empty to keep current.
            labels: New label list. Leave empty to keep current.
            due_date: New due date. Leave empty to keep current.
            description: New description. Leave empty to keep current.

        Example:
            update_task(task_id="123", content="Buy organic groceries",
                        labels=["Shopping", "Health"])

        Returns:
            {"id": "123", "content": "Buy organic groceries", ...}
        """
        return client.update_task(
            task_id=task_id,
            content=content or None,
            labels=labels or None,
            due_date=due_date or None,
            description=description or None,
        )

    @mcp.tool
    def move_task(
        task_id: Annotated[str, Field(description="The Todoist task ID to move")],
        project: Annotated[
            str,
            Field(
                description=(
                    "Target project name (case-insensitive). "
                    "Use list_todoist_projects() for valid names."
                )
            ),
        ],
    ) -> dict:
        """Move a task to a different Todoist project.

        Args:
            task_id: The task ID to move.
            project: Destination project name, e.g. "Active", "Backlog", "Waiting For".

        Example:
            move_task(task_id="123", project="Active")

        Returns:
            {"success": true}
        """
        result = client.move_task(task_id, project)
        return {"success": result}

    @mcp.tool
    def complete_task(
        task_id: Annotated[str, Field(description="The Todoist task ID to complete")],
    ) -> dict:
        """Mark a Todoist task as complete.

        The task will be moved to completed status. For recurring tasks,
        this advances to the next occurrence.

        Args:
            task_id: The task ID to complete.

        Example:
            complete_task(task_id="123")

        Returns:
            {"success": true}
        """
        result = client.complete_task(task_id)
        return {"success": result}

    @mcp.tool(annotations={"destructiveHint": True})
    def delete_task(
        task_id: Annotated[str, Field(description="The Todoist task ID to delete")],
    ) -> dict:
        """Permanently delete a Todoist task.

        This action is irreversible. Consider complete_task() instead
        if you want to keep a record of the task.

        Args:
            task_id: The task ID to delete.

        Example:
            delete_task(task_id="123")

        Returns:
            {"success": true}
        """
        result = client.delete_task(task_id)
        return {"success": result}

    @mcp.tool
    def batch_update_tasks(
        operations: Annotated[
            list[dict],
            Field(
                description=(
                    "List of operations. Each dict must include 'id' (task ID). "
                    "Optional fields: 'content' (str), 'labels' (list of label names), "
                    "'due_date' (str, natural language or YYYY-MM-DD), "
                    "'description' (str), 'project' (project name to move to)."
                )
            ),
        ],
    ) -> dict:
        """Batch update multiple Todoist tasks in a single API call.

        Uses the Todoist Sync API for efficiency — processes all operations in one request.
        Each operation can update fields and/or move a task to a different project.
        This is ideal for triage workflows where you need to process many tasks at once.

        Args:
            operations: List of update operations. Each must include 'id' (task ID).
                Optional fields per operation:
                - content: New task title
                - labels: List of label names (replaces existing)
                - due_date: Due date string (natural language or YYYY-MM-DD)
                - description: New description text
                - project: Project name to move the task to

        Example:
            batch_update_tasks(operations=[
                {"id": "123", "labels": ["Home"], "project": "Active"},
                {"id": "456", "content": "Updated task name", "due_date": "2026-03-15"},
                {"id": "789", "project": "Backlog"}
            ])

        Returns:
            {"succeeded": 3, "failed": 0, "results": {"uuid1": "ok", ...}}
        """
        return client.batch_update(operations)

    @mcp.tool
    def create_todoist_label(
        name: Annotated[str, Field(description="Label name to create")],
        color: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Label color. Valid values: berry_red, red, orange, yellow, "
                    "olive_green, lime_green, green, mint_green, teal, sky_blue, "
                    "light_blue, blue, grape, violet, lavender, magenta, salmon, charcoal."
                ),
            ),
        ] = None,
    ) -> dict:
        """Create a new personal label in Todoist.

        Args:
            name: The label name, e.g. "Urgent", "Errands".
            color: Optional color name from Todoist's palette.

        Example:
            create_todoist_label(name="Errands", color="green")

        Returns:
            {"id": "111", "name": "Errands", "color": "green"}
        """
        return client.create_label(name, color=color)

    @mcp.tool
    def rename_todoist_label(
        label_id: Annotated[
            str,
            Field(description=("The label ID to rename. Use list_todoist_labels() to find IDs.")),
        ],
        new_name: Annotated[str, Field(description="New name for the label")],
    ) -> dict:
        """Rename an existing Todoist label.

        Args:
            label_id: The label's ID (from list_todoist_labels()).
            new_name: The new name for the label.

        Example:
            rename_todoist_label(label_id="111", new_name="Quick Errands")

        Returns:
            {"id": "111", "name": "Quick Errands", "color": "green"}
        """
        return client.rename_label(label_id, new_name)

    @mcp.tool(annotations={"destructiveHint": True})
    def delete_todoist_label(
        label_id: Annotated[
            str,
            Field(description=("The label ID to delete. Use list_todoist_labels() to find IDs.")),
        ],
    ) -> dict:
        """Permanently delete a Todoist label.

        This removes the label from all tasks that have it.
        This action is irreversible.

        Args:
            label_id: The label's ID (from list_todoist_labels()).

        Example:
            delete_todoist_label(label_id="111")

        Returns:
            {"success": true}
        """
        result = client.delete_label(label_id)
        return {"success": result}
