"""Tests for Todoist MCP tool registration and delegation."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import FastMCP

from gtd_mcp.todoist.tools import register_todoist_tools


@pytest.fixture
def mcp_server():
    """Create a fresh FastMCP server for each test."""
    return FastMCP("test-server")


@pytest.fixture
def mock_client():
    """Create a mocked TodoistClient."""
    with patch("gtd_mcp.todoist.tools.TodoistClient") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance, mock_cls


def register_with_token(mcp_server, mock_client_fixture):
    """Register tools with a fake token set."""
    with patch.dict(os.environ, {"TODOIST_API_TOKEN": "fake-token"}):
        register_todoist_tools(mcp_server)
    return mock_client_fixture


def get_tool_names(mcp_server: FastMCP) -> set[str]:
    """Get the set of registered tool names."""
    tools = asyncio.new_event_loop().run_until_complete(mcp_server.list_tools())
    return {t.name for t in tools}


def get_tool_fn(mcp_server: FastMCP, name: str):
    """Get a registered tool's underlying function by name."""
    tool = asyncio.new_event_loop().run_until_complete(mcp_server.get_tool(name))
    if tool is None:
        raise KeyError(f"Tool '{name}' not registered")
    return tool.fn


# --- Registration tests ---


class TestToolRegistration:
    def test_tools_registered_when_token_present(self, mcp_server, mock_client):
        _, mock_cls = mock_client
        register_with_token(mcp_server, mock_client)

        mock_cls.assert_called_once_with("fake-token")

        tool_names = get_tool_names(mcp_server)
        expected = {
            "list_todoist_projects",
            "get_project_tasks",
            "list_todoist_labels",
            "create_task",
            "update_task",
            "move_task",
            "complete_task",
            "delete_task",
            "batch_update_tasks",
            "create_todoist_label",
            "rename_todoist_label",
            "delete_todoist_label",
            "get_task_comments",
            "add_task_comment",
        }
        assert expected == tool_names

    def test_no_tools_when_token_missing(self, mcp_server):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("TODOIST_API_TOKEN", None)
            register_todoist_tools(mcp_server)

        tool_names = get_tool_names(mcp_server)
        assert len(tool_names) == 0


# --- Delegation tests ---


class TestListProjects:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.list_projects.return_value = [{"id": "1", "name": "Inbox"}]

        fn = get_tool_fn(mcp_server, "list_todoist_projects")
        result = fn()

        mock_instance.list_projects.assert_called_once()
        assert result == [{"id": "1", "name": "Inbox"}]


class TestGetProjectTasks:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.get_tasks.return_value = [{"id": "t1", "content": "Test"}]

        fn = get_tool_fn(mcp_server, "get_project_tasks")
        result = fn(project="Inbox")

        mock_instance.get_tasks.assert_called_once_with("Inbox")
        assert result == [{"id": "t1", "content": "Test"}]


class TestListLabels:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.get_labels.return_value = [{"id": "l1", "name": "Home"}]

        fn = get_tool_fn(mcp_server, "list_todoist_labels")
        result = fn()

        mock_instance.get_labels.assert_called_once()
        assert result == [{"id": "l1", "name": "Home"}]


class TestCreateTask:
    def test_delegates_with_defaults(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.create_task.return_value = {"id": "t1", "content": "Buy milk"}

        fn = get_tool_fn(mcp_server, "create_task")
        result = fn(content="Buy milk")

        mock_instance.create_task.assert_called_once_with(
            content="Buy milk",
            project="Inbox",
            labels=None,
            due_date=None,
            description=None,
        )
        assert result["content"] == "Buy milk"

    def test_delegates_with_all_params(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.create_task.return_value = {"id": "t1"}

        fn = get_tool_fn(mcp_server, "create_task")
        fn(
            content="Task",
            project="Active",
            labels=["Work"],
            due_date="tomorrow",
            description="Notes",
        )

        mock_instance.create_task.assert_called_once_with(
            content="Task",
            project="Active",
            labels=["Work"],
            due_date="tomorrow",
            description="Notes",
        )


class TestUpdateTask:
    def test_delegates_partial_update(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.update_task.return_value = {"id": "t1"}

        fn = get_tool_fn(mcp_server, "update_task")
        fn(task_id="t1", content="New title")

        mock_instance.update_task.assert_called_once_with(
            task_id="t1",
            content="New title",
            labels=None,
            due_date=None,
            description=None,
        )


class TestMoveTask:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.move_task.return_value = True

        fn = get_tool_fn(mcp_server, "move_task")
        result = fn(task_id="t1", project="Active")

        mock_instance.move_task.assert_called_once_with("t1", "Active")
        assert result == {"success": True}


class TestCompleteTask:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.complete_task.return_value = True

        fn = get_tool_fn(mcp_server, "complete_task")
        result = fn(task_id="t1")

        mock_instance.complete_task.assert_called_once_with("t1")
        assert result == {"success": True}


class TestDeleteTask:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.delete_task.return_value = True

        fn = get_tool_fn(mcp_server, "delete_task")
        result = fn(task_id="t1")

        mock_instance.delete_task.assert_called_once_with("t1")
        assert result == {"success": True}


class TestBatchUpdateTasks:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.batch_update.return_value = {
            "succeeded": 2,
            "failed": 0,
            "results": {},
        }

        fn = get_tool_fn(mcp_server, "batch_update_tasks")
        ops = [{"id": "t1", "labels": ["Home"]}, {"id": "t2", "project": "Active"}]
        result = fn(operations=ops)

        mock_instance.batch_update.assert_called_once_with(ops)
        assert result["succeeded"] == 2


class TestCreateLabel:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.create_label.return_value = {"id": "l1", "name": "Errands"}

        fn = get_tool_fn(mcp_server, "create_todoist_label")
        result = fn(name="Errands", color="green")

        mock_instance.create_label.assert_called_once_with("Errands", color="green")
        assert result["name"] == "Errands"


class TestRenameLabel:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.rename_label.return_value = {"id": "l1", "name": "New"}

        fn = get_tool_fn(mcp_server, "rename_todoist_label")
        result = fn(label_id="l1", new_name="New")

        mock_instance.rename_label.assert_called_once_with("l1", "New")
        assert result["name"] == "New"


class TestGetTaskComments:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.get_task_comments.return_value = [
            {"id": "c1", "content": "Note", "task_id": "t1", "posted_at": "2026-03-19"}
        ]

        fn = get_tool_fn(mcp_server, "get_task_comments")
        result = fn(task_id="t1")

        mock_instance.get_task_comments.assert_called_once_with("t1")
        assert result == [
            {"id": "c1", "content": "Note", "task_id": "t1", "posted_at": "2026-03-19"}
        ]


class TestAddTaskComment:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.add_task_comment.return_value = {
            "id": "c1",
            "content": "Follow up",
            "task_id": "t1",
            "posted_at": "2026-03-19",
        }

        fn = get_tool_fn(mcp_server, "add_task_comment")
        result = fn(task_id="t1", content="Follow up")

        mock_instance.add_task_comment.assert_called_once_with("t1", "Follow up")
        assert result["content"] == "Follow up"


class TestDeleteLabel:
    def test_delegates_to_client(self, mcp_server, mock_client):
        mock_instance, _ = register_with_token(mcp_server, mock_client)
        mock_instance.delete_label.return_value = True

        fn = get_tool_fn(mcp_server, "delete_todoist_label")
        result = fn(label_id="l1")

        mock_instance.delete_label.assert_called_once_with("l1")
        assert result == {"success": True}
