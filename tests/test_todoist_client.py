"""Tests for TodoistClient REST v2 operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from gtd_mcp.todoist.client import TodoistClient
from gtd_mcp.todoist.exceptions import TodoistAPIError

# --- Fixtures / Fake models ---


@dataclass
class FakeDue:
    date: str = "2026-03-10"
    string: str = "Mar 10"
    is_recurring: bool = False


@dataclass
class FakeTask:
    id: str = "task_1"
    content: str = "Buy milk"
    description: str = ""
    labels: list[str] = field(default_factory=lambda: ["Shopping"])
    priority: int = 1
    project_id: str = "proj_inbox"
    is_completed: bool = False
    due: FakeDue | None = None


@dataclass
class FakeProject:
    id: str = "proj_inbox"
    name: str = "Inbox"


@dataclass
class FakeLabel:
    id: str = "label_1"
    name: str = "Home"
    color: str = "blue"


def make_client() -> tuple[TodoistClient, MagicMock]:
    """Create a TodoistClient with a mocked TodoistAPI."""
    with patch("gtd_mcp.todoist.client.TodoistAPI") as mock_cls:
        mock_api = MagicMock()
        mock_cls.return_value = mock_api
        client = TodoistClient("fake-token")
    return client, mock_api


def setup_projects(mock_api: MagicMock, projects: list[FakeProject] | None = None) -> None:
    """Configure mock_api.get_projects() to return project pages."""
    if projects is None:
        projects = [
            FakeProject(id="proj_inbox", name="Inbox"),
            FakeProject(id="proj_active", name="Active"),
            FakeProject(id="proj_backlog", name="Backlog"),
            FakeProject(id="proj_waiting", name="Waiting For"),
        ]
    mock_api.get_projects.return_value = iter([projects])


# --- Project resolution tests ---


class TestProjectResolution:
    def test_resolve_project_by_name(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        project_id = client._resolve_project("Inbox")
        assert project_id == "proj_inbox"

    def test_resolve_project_case_insensitive(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        assert client._resolve_project("inbox") == "proj_inbox"
        assert client._resolve_project("ACTIVE") == "proj_active"
        assert client._resolve_project("Waiting For") == "proj_waiting"

    def test_resolve_project_not_found_lists_available(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        with pytest.raises(ValueError, match="Project 'Nonexistent' not found"):
            client._resolve_project("Nonexistent")

    def test_resolve_project_caches_after_first_call(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        client._resolve_project("Inbox")
        client._resolve_project("Active")
        # Should only fetch projects once
        assert mock_api.get_projects.call_count == 1

    def test_invalidate_project_cache(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        client._resolve_project("Inbox")
        client.invalidate_project_cache()
        setup_projects(mock_api)  # re-setup for second call
        client._resolve_project("Inbox")
        assert mock_api.get_projects.call_count == 2

    def test_resolve_project_api_error(self):
        client, mock_api = make_client()
        mock_api.get_projects.side_effect = Exception("Network error")

        with pytest.raises(TodoistAPIError, match="Failed to fetch projects"):
            client._resolve_project("Inbox")


# --- list_projects tests ---


class TestListProjects:
    def test_list_projects_returns_all(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        projects = client.list_projects()
        assert len(projects) == 4
        assert projects[0] == {"id": "proj_inbox", "name": "Inbox"}

    def test_list_projects_api_error(self):
        client, mock_api = make_client()
        mock_api.get_projects.side_effect = Exception("Timeout")

        with pytest.raises(TodoistAPIError, match="Failed to fetch projects"):
            client.list_projects()


# --- get_tasks tests ---


class TestGetTasks:
    def test_get_tasks_resolves_project_and_returns_dicts(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        task = FakeTask(due=FakeDue())
        mock_api.get_tasks.return_value = iter([[task]])

        tasks = client.get_tasks("Inbox")
        assert len(tasks) == 1
        assert tasks[0]["id"] == "task_1"
        assert tasks[0]["content"] == "Buy milk"
        assert tasks[0]["labels"] == ["Shopping"]
        assert tasks[0]["project_name"] == "Inbox"
        assert tasks[0]["due"]["date"] == "2026-03-10"
        mock_api.get_tasks.assert_called_once_with(project_id="proj_inbox")

    def test_get_tasks_no_due_date(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        task = FakeTask(due=None)
        mock_api.get_tasks.return_value = iter([[task]])

        tasks = client.get_tasks("Inbox")
        assert tasks[0]["due"] is None

    def test_get_tasks_invalid_project(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        with pytest.raises(ValueError, match="not found"):
            client.get_tasks("Nonexistent")

    def test_get_tasks_api_error(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        mock_api.get_tasks.side_effect = Exception("API down")

        with pytest.raises(TodoistAPIError, match="Failed to fetch tasks"):
            client.get_tasks("Inbox")


# --- create_task tests ---


class TestCreateTask:
    def test_create_task_minimal(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        mock_api.add_task.return_value = FakeTask()

        result = client.create_task("Buy milk")
        assert result["content"] == "Buy milk"
        mock_api.add_task.assert_called_once_with(content="Buy milk", project_id="proj_inbox")

    def test_create_task_with_all_fields(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        mock_api.add_task.return_value = FakeTask()

        client.create_task(
            content="Buy milk",
            project="Active",
            labels=["Shopping", "Home"],
            due_date="tomorrow",
            description="From the store",
        )
        mock_api.add_task.assert_called_once_with(
            content="Buy milk",
            project_id="proj_active",
            labels=["Shopping", "Home"],
            due_string="tomorrow",
            description="From the store",
        )

    def test_create_task_api_error(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        mock_api.add_task.side_effect = Exception("Rate limited")

        with pytest.raises(TodoistAPIError, match="Failed to create task"):
            client.create_task("Test")


# --- update_task tests ---


class TestUpdateTask:
    def test_update_task_partial(self):
        client, mock_api = make_client()
        mock_api.update_task.return_value = FakeTask(content="Updated")

        result = client.update_task("task_1", content="Updated")
        assert result["content"] == "Updated"
        mock_api.update_task.assert_called_once_with("task_1", content="Updated")

    def test_update_task_all_fields(self):
        client, mock_api = make_client()
        mock_api.update_task.return_value = FakeTask()

        client.update_task(
            "task_1",
            content="New content",
            labels=["Work"],
            due_date="next week",
            description="Details",
        )
        mock_api.update_task.assert_called_once_with(
            "task_1",
            content="New content",
            labels=["Work"],
            due_string="next week",
            description="Details",
        )

    def test_update_task_no_fields_does_nothing(self):
        client, mock_api = make_client()
        mock_api.update_task.return_value = FakeTask()

        client.update_task("task_1")
        mock_api.update_task.assert_called_once_with("task_1")

    def test_update_task_api_error(self):
        client, mock_api = make_client()
        mock_api.update_task.side_effect = Exception("Not found")

        with pytest.raises(TodoistAPIError, match="Failed to update task"):
            client.update_task("task_1", content="X")


# --- complete_task tests ---


class TestCompleteTask:
    def test_complete_task(self):
        client, mock_api = make_client()
        mock_api.complete_task.return_value = True

        assert client.complete_task("task_1") is True
        mock_api.complete_task.assert_called_once_with("task_1")

    def test_complete_task_api_error(self):
        client, mock_api = make_client()
        mock_api.complete_task.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to complete task"):
            client.complete_task("task_1")


# --- delete_task tests ---


class TestDeleteTask:
    def test_delete_task(self):
        client, mock_api = make_client()
        mock_api.delete_task.return_value = True

        assert client.delete_task("task_1") is True

    def test_delete_task_api_error(self):
        client, mock_api = make_client()
        mock_api.delete_task.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to delete task"):
            client.delete_task("task_1")


# --- move_task tests ---


class TestMoveTask:
    def test_move_task_resolves_project(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        mock_api.move_task.return_value = True

        assert client.move_task("task_1", "Active") is True
        mock_api.move_task.assert_called_once_with("task_1", project_id="proj_active")

    def test_move_task_invalid_project(self):
        client, mock_api = make_client()
        setup_projects(mock_api)

        with pytest.raises(ValueError, match="not found"):
            client.move_task("task_1", "Nonexistent")

    def test_move_task_api_error(self):
        client, mock_api = make_client()
        setup_projects(mock_api)
        mock_api.move_task.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to move task"):
            client.move_task("task_1", "Active")


# --- Label tests ---


class TestLabels:
    def test_get_labels(self):
        client, mock_api = make_client()
        mock_api.get_labels.return_value = iter([[FakeLabel()]])

        labels = client.get_labels()
        assert len(labels) == 1
        assert labels[0] == {"id": "label_1", "name": "Home", "color": "blue"}

    def test_create_label(self):
        client, mock_api = make_client()
        mock_api.add_label.return_value = FakeLabel(name="Work", color="red")

        result = client.create_label("Work", color="red")
        assert result["name"] == "Work"
        mock_api.add_label.assert_called_once_with(name="Work", color="red")

    def test_create_label_no_color(self):
        client, mock_api = make_client()
        mock_api.add_label.return_value = FakeLabel(name="Work")

        client.create_label("Work")
        mock_api.add_label.assert_called_once_with(name="Work")

    def test_rename_label(self):
        client, mock_api = make_client()
        mock_api.update_label.return_value = FakeLabel(name="NewName")

        result = client.rename_label("label_1", "NewName")
        assert result["name"] == "NewName"
        mock_api.update_label.assert_called_once_with("label_1", name="NewName")

    def test_delete_label(self):
        client, mock_api = make_client()
        mock_api.delete_label.return_value = True

        assert client.delete_label("label_1") is True

    def test_get_labels_api_error(self):
        client, mock_api = make_client()
        mock_api.get_labels.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to fetch labels"):
            client.get_labels()

    def test_create_label_api_error(self):
        client, mock_api = make_client()
        mock_api.add_label.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to create label"):
            client.create_label("X")

    def test_rename_label_api_error(self):
        client, mock_api = make_client()
        mock_api.update_label.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to rename label"):
            client.rename_label("x", "y")

    def test_delete_label_api_error(self):
        client, mock_api = make_client()
        mock_api.delete_label.side_effect = Exception("Fail")

        with pytest.raises(TodoistAPIError, match="Failed to delete label"):
            client.delete_label("x")
