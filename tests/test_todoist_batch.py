"""Tests for TodoistClient batch operations (Sync API v1)."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import httpx
import pytest

from gtd_mcp.todoist.client import TodoistClient
from gtd_mcp.todoist.exceptions import TodoistAPIError


@dataclass
class FakeProject:
    id: str
    name: str


def make_client() -> tuple[TodoistClient, MagicMock, MagicMock]:
    """Create a TodoistClient with mocked TodoistAPI and httpx.Client."""
    with (
        patch("gtd_mcp.todoist.client.TodoistAPI") as mock_api_cls,
        patch("gtd_mcp.todoist.client.httpx.Client") as mock_http_cls,
    ):
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_http = MagicMock()
        mock_http_cls.return_value = mock_http
        client = TodoistClient("fake-token")
    return client, mock_api, mock_http


def setup_projects(mock_api: MagicMock) -> None:
    projects = [
        FakeProject(id="proj_inbox", name="Inbox"),
        FakeProject(id="proj_active", name="Active"),
        FakeProject(id="proj_backlog", name="Backlog"),
    ]
    mock_api.get_projects.return_value = iter([projects])


class TestBuildSyncCommands:
    def test_update_fields_only(self):
        client, mock_api, _ = make_client()

        ops = [{"id": "task_1", "content": "New title", "labels": ["Home"]}]
        commands = client._build_sync_commands(ops)

        assert len(commands) == 1
        assert commands[0]["type"] == "item_update"
        assert commands[0]["args"]["id"] == "task_1"
        assert commands[0]["args"]["content"] == "New title"
        assert commands[0]["args"]["labels"] == ["Home"]
        assert "uuid" in commands[0]

    def test_move_only(self):
        client, mock_api, _ = make_client()
        setup_projects(mock_api)

        ops = [{"id": "task_1", "project": "Active"}]
        commands = client._build_sync_commands(ops)

        assert len(commands) == 1
        assert commands[0]["type"] == "item_move"
        assert commands[0]["args"]["project_id"] == "proj_active"

    def test_update_and_move_generates_two_commands(self):
        client, mock_api, _ = make_client()
        setup_projects(mock_api)

        ops = [{"id": "task_1", "content": "Updated", "project": "Backlog"}]
        commands = client._build_sync_commands(ops)

        assert len(commands) == 2
        types = {c["type"] for c in commands}
        assert types == {"item_update", "item_move"}

    def test_multiple_operations(self):
        client, mock_api, _ = make_client()
        setup_projects(mock_api)

        ops = [
            {"id": "task_1", "labels": ["Home"]},
            {"id": "task_2", "project": "Active"},
            {"id": "task_3", "content": "X", "project": "Backlog"},
        ]
        commands = client._build_sync_commands(ops)

        # task_1: 1 update, task_2: 1 move, task_3: 1 update + 1 move
        assert len(commands) == 4

    def test_skip_operation_without_id(self):
        client, _, _ = make_client()

        ops = [{"content": "No ID"}]
        commands = client._build_sync_commands(ops)

        assert len(commands) == 0

    def test_due_date_maps_to_due_string(self):
        client, _, _ = make_client()

        ops = [{"id": "task_1", "due_date": "2026-03-15"}]
        commands = client._build_sync_commands(ops)

        assert commands[0]["args"]["due_string"] == "2026-03-15"

    def test_clear_due_date_with_none(self):
        client, _, _ = make_client()

        ops = [{"id": "task_1", "due_date": None}]
        commands = client._build_sync_commands(ops)

        args = commands[0]["args"]
        assert args["due"] is None
        assert "due_string" not in args

    def test_clear_due_date_with_empty_string(self):
        client, _, _ = make_client()

        ops = [{"id": "task_1", "due_date": ""}]
        commands = client._build_sync_commands(ops)

        args = commands[0]["args"]
        assert args["due"] is None
        assert "due_string" not in args

    def test_clear_due_date_with_no_date_string(self):
        client, _, _ = make_client()

        ops = [{"id": "task_1", "due_date": "no date"}]
        commands = client._build_sync_commands(ops)

        args = commands[0]["args"]
        assert args["due"] is None
        assert "due_string" not in args

    def test_description_included(self):
        client, _, _ = make_client()

        ops = [{"id": "task_1", "description": "Some notes"}]
        commands = client._build_sync_commands(ops)

        assert commands[0]["args"]["description"] == "Some notes"

    def test_unique_uuids(self):
        client, mock_api, _ = make_client()
        setup_projects(mock_api)

        ops = [
            {"id": "task_1", "content": "A", "project": "Active"},
            {"id": "task_2", "content": "B", "project": "Backlog"},
        ]
        commands = client._build_sync_commands(ops)
        uuids = [c["uuid"] for c in commands]
        assert len(uuids) == len(set(uuids))

    def test_empty_operations(self):
        client, _, _ = make_client()

        commands = client._build_sync_commands([])
        assert commands == []

    def test_operation_with_id_only_no_changes(self):
        client, _, _ = make_client()

        ops = [{"id": "task_1"}]
        commands = client._build_sync_commands(ops)
        assert len(commands) == 0

    def test_move_invalid_project_raises(self):
        client, mock_api, _ = make_client()
        setup_projects(mock_api)

        ops = [{"id": "task_1", "project": "Nonexistent"}]
        with pytest.raises(ValueError, match="not found"):
            client._build_sync_commands(ops)


class TestBatchUpdate:
    def test_successful_batch(self):
        client, mock_api, mock_http = make_client()

        response = MagicMock()
        response.json.return_value = {"sync_status": {"uuid1": "ok", "uuid2": "ok"}}
        response.raise_for_status = MagicMock()
        mock_http.post.return_value = response

        ops = [{"id": "task_1", "content": "Updated"}]
        result = client.batch_update(ops)

        assert result["succeeded"] == 2
        assert result["failed"] == 0
        mock_http.post.assert_called_once()

    def test_partial_failure(self):
        client, mock_api, mock_http = make_client()

        response = MagicMock()
        response.json.return_value = {
            "sync_status": {"uuid1": "ok", "uuid2": {"error": "not found"}}
        }
        response.raise_for_status = MagicMock()
        mock_http.post.return_value = response

        ops = [{"id": "task_1", "content": "X"}]
        result = client.batch_update(ops)

        assert result["succeeded"] == 1
        assert result["failed"] == 1

    def test_empty_operations_returns_zero(self):
        client, _, mock_http = make_client()

        result = client.batch_update([])

        assert result == {"succeeded": 0, "failed": 0, "results": {}}
        mock_http.post.assert_not_called()

    def test_http_status_error(self):
        client, _, mock_http = make_client()

        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"
        mock_http.post.return_value = response
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server error", request=MagicMock(), response=response
        )

        ops = [{"id": "task_1", "content": "X"}]
        with pytest.raises(TodoistAPIError, match="Sync API returned 500"):
            client.batch_update(ops)

    def test_http_network_error(self):
        client, _, mock_http = make_client()

        mock_http.post.side_effect = httpx.ConnectError("Connection refused")

        ops = [{"id": "task_1", "content": "X"}]
        with pytest.raises(TodoistAPIError, match="Sync API request failed"):
            client.batch_update(ops)

    def test_batch_with_move_invalidates_cache(self):
        client, mock_api, mock_http = make_client()
        setup_projects(mock_api)

        # Prime the cache
        client._resolve_project("Inbox")
        assert client._projects_cache is not None

        response = MagicMock()
        response.json.return_value = {"sync_status": {"uuid1": "ok"}}
        response.raise_for_status = MagicMock()
        mock_http.post.return_value = response

        ops = [{"id": "task_1", "project": "Active"}]
        client.batch_update(ops)

        # Cache should be invalidated after a move
        assert client._projects_cache is None
