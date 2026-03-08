"""Todoist API client wrapping REST v2 and Sync API v1."""

from __future__ import annotations

import logging
import uuid

import httpx
from todoist_api_python.api import TodoistAPI

from gtd_mcp.todoist.exceptions import TodoistAPIError

logger = logging.getLogger(__name__)

SYNC_API_URL = "https://api.todoist.com/api/v1/sync"


class TodoistClient:
    """Client for Todoist REST v2 and Sync API v1.

    Projects and labels are resolved dynamically by name — no hardcoded IDs.
    Use list_projects() and get_labels() to discover available values.
    """

    def __init__(self, api_token: str) -> None:
        self._api = TodoistAPI(api_token)
        self._http = httpx.Client(
            base_url=SYNC_API_URL,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30.0,
        )
        self._projects_cache: dict[str, str] | None = None

    def _get_projects_map(self) -> dict[str, str]:
        """Fetch all projects and return {name_lower: id} mapping. Cached after first call."""
        if self._projects_cache is None:
            self._projects_cache = {}
            try:
                for page in self._api.get_projects():
                    for project in page:
                        self._projects_cache[project.name.lower()] = project.id
            except Exception as e:
                raise TodoistAPIError(f"Failed to fetch projects: {e}") from e
        return self._projects_cache

    def _resolve_project(self, name: str) -> str:
        """Resolve a project name (case-insensitive) to its ID.

        Raises ValueError if the project is not found, listing available projects.
        """
        projects = self._get_projects_map()
        project_id = projects.get(name.lower())
        if project_id is None:
            available = ", ".join(sorted(projects.keys()))
            raise ValueError(f"Project '{name}' not found. Available projects: {available}")
        return project_id

    def invalidate_project_cache(self) -> None:
        """Clear the cached project mapping, forcing a refresh on next resolve."""
        self._projects_cache = None

    def list_projects(self) -> list[dict]:
        """Return all projects with id and name."""
        try:
            projects = []
            for page in self._api.get_projects():
                for project in page:
                    projects.append({"id": project.id, "name": project.name})
            return projects
        except Exception as e:
            raise TodoistAPIError(f"Failed to fetch projects: {e}") from e

    def get_tasks(self, project: str) -> list[dict]:
        """Get all tasks from a project, resolved by name."""
        project_id = self._resolve_project(project)
        try:
            tasks = []
            for page in self._api.get_tasks(project_id=project_id):
                for task in page:
                    tasks.append(self._task_to_dict(task, project_name=project))
            return tasks
        except ValueError:
            raise
        except Exception as e:
            raise TodoistAPIError(f"Failed to fetch tasks for '{project}': {e}") from e

    def create_task(
        self,
        content: str,
        project: str = "Inbox",
        labels: list[str] | None = None,
        due_date: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a new task in the specified project."""
        project_id = self._resolve_project(project)
        try:
            kwargs: dict = {"content": content, "project_id": project_id}
            if labels is not None:
                kwargs["labels"] = labels
            if due_date is not None:
                kwargs["due_string"] = due_date
            if description is not None:
                kwargs["description"] = description
            task = self._api.add_task(**kwargs)
            return self._task_to_dict(task, project_name=project)
        except ValueError:
            raise
        except Exception as e:
            raise TodoistAPIError(f"Failed to create task: {e}") from e

    def update_task(
        self,
        task_id: str,
        content: str | None = None,
        labels: list[str] | None = None,
        due_date: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Update fields on an existing task."""
        try:
            kwargs: dict = {}
            if content is not None:
                kwargs["content"] = content
            if labels is not None:
                kwargs["labels"] = labels
            if due_date is not None:
                kwargs["due_string"] = due_date
            if description is not None:
                kwargs["description"] = description
            task = self._api.update_task(task_id, **kwargs)
            return self._task_to_dict(task)
        except Exception as e:
            raise TodoistAPIError(f"Failed to update task {task_id}: {e}") from e

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as complete."""
        try:
            return self._api.complete_task(task_id)
        except Exception as e:
            raise TodoistAPIError(f"Failed to complete task {task_id}: {e}") from e

    def delete_task(self, task_id: str) -> bool:
        """Delete a task permanently."""
        try:
            return self._api.delete_task(task_id)
        except Exception as e:
            raise TodoistAPIError(f"Failed to delete task {task_id}: {e}") from e

    def move_task(self, task_id: str, project: str) -> bool:
        """Move a task to a different project, resolved by name."""
        project_id = self._resolve_project(project)
        try:
            return self._api.move_task(task_id, project_id=project_id)
        except ValueError:
            raise
        except Exception as e:
            raise TodoistAPIError(f"Failed to move task {task_id}: {e}") from e

    def get_labels(self) -> list[dict]:
        """Return all personal labels."""
        try:
            labels = []
            for page in self._api.get_labels():
                for label in page:
                    labels.append(
                        {
                            "id": label.id,
                            "name": label.name,
                            "color": label.color,
                        }
                    )
            return labels
        except Exception as e:
            raise TodoistAPIError(f"Failed to fetch labels: {e}") from e

    def create_label(self, name: str, color: str | None = None) -> dict:
        """Create a new personal label."""
        try:
            kwargs: dict = {"name": name}
            if color is not None:
                kwargs["color"] = color
            label = self._api.add_label(**kwargs)
            return {"id": label.id, "name": label.name, "color": label.color}
        except Exception as e:
            raise TodoistAPIError(f"Failed to create label '{name}': {e}") from e

    def rename_label(self, label_id: str, new_name: str) -> dict:
        """Rename an existing label."""
        try:
            label = self._api.update_label(label_id, name=new_name)
            return {"id": label.id, "name": label.name, "color": label.color}
        except Exception as e:
            raise TodoistAPIError(f"Failed to rename label {label_id}: {e}") from e

    def delete_label(self, label_id: str) -> bool:
        """Delete a label."""
        try:
            return self._api.delete_label(label_id)
        except Exception as e:
            raise TodoistAPIError(f"Failed to delete label {label_id}: {e}") from e

    # --- Batch operations (Sync API v1) ---

    def batch_update(self, operations: list[dict]) -> dict:
        """Batch update multiple tasks via the Sync API v1.

        Each operation is a dict with 'id' (required) and optional fields:
        content, labels, due_date, project (name, resolved dynamically).

        Returns a summary with per-operation results.
        """
        commands = self._build_sync_commands(operations)
        if not commands:
            return {"succeeded": 0, "failed": 0, "results": {}}

        try:
            response = self._http.post("", json={"commands": commands})
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            raise TodoistAPIError(
                f"Sync API returned {e.response.status_code}: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.HTTPError as e:
            raise TodoistAPIError(f"Sync API request failed: {e}") from e

        sync_status = data.get("sync_status", {})
        succeeded = sum(1 for v in sync_status.values() if v == "ok")
        failed = len(sync_status) - succeeded

        # Invalidate project cache since moves may have changed state
        if any("project" in op for op in operations):
            self.invalidate_project_cache()

        return {"succeeded": succeeded, "failed": failed, "results": sync_status}

    def _build_sync_commands(self, operations: list[dict]) -> list[dict]:
        """Translate operation dicts into Sync API v1 command objects."""
        commands = []
        for op in operations:
            task_id = op.get("id")
            if not task_id:
                logger.warning("Skipping operation without 'id': %s", op)
                continue

            # Build item_update command for field changes
            update_args: dict = {}
            if "content" in op:
                update_args["content"] = op["content"]
            if "labels" in op:
                update_args["labels"] = op["labels"]
            if "due_date" in op:
                update_args["due_string"] = op["due_date"]
            if "description" in op:
                update_args["description"] = op["description"]

            if update_args:
                update_args["id"] = task_id
                commands.append(
                    {
                        "type": "item_update",
                        "uuid": str(uuid.uuid4()),
                        "args": update_args,
                    }
                )

            # Build item_move command for project changes
            if "project" in op:
                project_id = self._resolve_project(op["project"])
                commands.append(
                    {
                        "type": "item_move",
                        "uuid": str(uuid.uuid4()),
                        "args": {"id": task_id, "project_id": project_id},
                    }
                )

        return commands

    # --- Helpers ---

    @staticmethod
    def _task_to_dict(task, project_name: str | None = None) -> dict:
        """Convert a Todoist Task object to a plain dict."""
        result = {
            "id": task.id,
            "content": task.content,
            "description": task.description,
            "labels": task.labels,
            "priority": task.priority,
            "project_id": task.project_id,
            "is_completed": task.is_completed,
        }
        if project_name:
            result["project_name"] = project_name
        if task.due:
            result["due"] = {
                "date": task.due.date,
                "string": task.due.string,
                "is_recurring": task.due.is_recurring,
            }
        else:
            result["due"] = None
        return result
