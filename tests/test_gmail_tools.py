"""Tests for Gmail MCP tool registration and delegation."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import FastMCP

from gtd_mcp.gmail.tools import register_gmail_tools


@pytest.fixture
def mcp_server():
    return FastMCP("test-server")


@pytest.fixture
def mock_gmail():
    """Mock GmailAuth and GmailClient."""
    with (
        patch("gtd_mcp.gmail.tools.GmailAuth") as mock_auth_cls,
        patch("gtd_mcp.gmail.tools.GmailClient") as mock_client_cls,
    ):
        mock_auth = MagicMock()
        mock_auth_cls.return_value = mock_auth
        mock_auth.get_service.return_value = MagicMock()
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        yield mock_client, mock_auth_cls, mock_client_cls


def register_with_env(mcp_server, mock_gmail_fixture):
    """Register tools with fake Gmail env vars."""
    env = {
        "GMAIL_CREDENTIALS_PATH": "/fake/creds.json",
        "GMAIL_TOKEN_PATH": "/fake/token.json",
    }
    with patch.dict(os.environ, env):
        register_gmail_tools(mcp_server)
    return mock_gmail_fixture


def get_tool_names(mcp_server: FastMCP) -> set[str]:
    tools = asyncio.new_event_loop().run_until_complete(mcp_server.list_tools())
    return {t.name for t in tools}


def get_tool_fn(mcp_server: FastMCP, name: str):
    tool = asyncio.new_event_loop().run_until_complete(mcp_server.get_tool(name))
    if tool is None:
        raise KeyError(f"Tool '{name}' not registered")
    return tool.fn


# --- Registration ---


class TestRegistration:
    def test_all_tools_registered(self, mcp_server, mock_gmail):
        register_with_env(mcp_server, mock_gmail)

        expected = {
            "search_gmail",
            "read_gmail_message",
            "read_gmail_thread",
            "list_gmail_labels",
            "archive_gmail_messages",
            "bulk_archive_gmail",
            "apply_gmail_label",
            "remove_gmail_label",
            "create_gmail_label",
            "mark_gmail_read",
            "mark_gmail_unread",
            "create_gmail_draft",
            "send_gmail",
            "send_gmail_draft",
            "trash_gmail_messages",
        }
        assert get_tool_names(mcp_server) == expected

    def test_no_tools_when_env_missing(self, mcp_server):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GMAIL_CREDENTIALS_PATH", None)
            os.environ.pop("GMAIL_TOKEN_PATH", None)
            register_gmail_tools(mcp_server)

        assert len(get_tool_names(mcp_server)) == 0


# --- Delegation ---


class TestSearchGmail:
    def test_delegates(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.search_messages.return_value = [{"id": "msg_1"}]

        fn = get_tool_fn(mcp_server, "search_gmail")
        result = fn(query="is:unread")

        mock_client.search_messages.assert_called_once_with("is:unread", 20)
        assert result == [{"id": "msg_1"}]


class TestReadMessage:
    def test_delegates(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.read_message.return_value = {"id": "msg_1", "body": "text"}

        fn = get_tool_fn(mcp_server, "read_gmail_message")
        result = fn(message_id="msg_1")

        mock_client.read_message.assert_called_once_with("msg_1")
        assert result["body"] == "text"


class TestReadThread:
    def test_delegates(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.read_thread.return_value = {"thread_id": "t1", "messages": []}

        fn = get_tool_fn(mcp_server, "read_gmail_thread")
        fn(thread_id="t1")

        mock_client.read_thread.assert_called_once_with("t1")


class TestArchive:
    def test_archive_delegates(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.archive_messages.return_value = {"modified": 2}

        fn = get_tool_fn(mcp_server, "archive_gmail_messages")
        result = fn(message_ids=["m1", "m2"])

        mock_client.archive_messages.assert_called_once_with(["m1", "m2"])
        assert result["modified"] == 2

    def test_bulk_archive_delegates(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.bulk_archive.return_value = {"archived": 10, "query": "test"}

        fn = get_tool_fn(mcp_server, "bulk_archive_gmail")
        result = fn(query="from:spam@x.com")

        mock_client.bulk_archive.assert_called_once_with("from:spam@x.com")
        assert result["archived"] == 10


class TestLabels:
    def test_apply_label(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.apply_label.return_value = {"modified": 1}

        fn = get_tool_fn(mcp_server, "apply_gmail_label")
        fn(message_ids=["m1"], label_name="Work")
        mock_client.apply_label.assert_called_once_with(["m1"], "Work")

    def test_remove_label(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.remove_label.return_value = {"modified": 1}

        fn = get_tool_fn(mcp_server, "remove_gmail_label")
        fn(message_ids=["m1"], label_name="Work")
        mock_client.remove_label.assert_called_once_with(["m1"], "Work")

    def test_create_label(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.create_label.return_value = {"id": "L1", "name": "New"}

        fn = get_tool_fn(mcp_server, "create_gmail_label")
        result = fn(name="New")
        mock_client.create_label.assert_called_once_with(
            "New", text_color=None, background_color=None
        )
        assert result["name"] == "New"


class TestReadState:
    def test_mark_read(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.mark_read.return_value = {"modified": 2}

        fn = get_tool_fn(mcp_server, "mark_gmail_read")
        fn(message_ids=["m1", "m2"])
        mock_client.mark_read.assert_called_once_with(["m1", "m2"])

    def test_mark_unread(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.mark_unread.return_value = {"modified": 1}

        fn = get_tool_fn(mcp_server, "mark_gmail_unread")
        fn(message_ids=["m1"])
        mock_client.mark_unread.assert_called_once_with(["m1"])


class TestCompose:
    def test_create_draft(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.create_draft.return_value = {"draft_id": "d1"}

        fn = get_tool_fn(mcp_server, "create_gmail_draft")
        fn(to="x@y.com", subject="Hi", body="Hello")
        mock_client.create_draft.assert_called_once_with(
            "x@y.com", "Hi", "Hello", thread_id=None, cc=None
        )

    def test_send_email(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.send_email.return_value = {"message_id": "m1"}

        fn = get_tool_fn(mcp_server, "send_gmail")
        fn(to="x@y.com", subject="Hi", body="Hello")
        mock_client.send_email.assert_called_once_with("x@y.com", "Hi", "Hello", cc=None)

    def test_send_draft(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.send_draft.return_value = {"message_id": "m1"}

        fn = get_tool_fn(mcp_server, "send_gmail_draft")
        fn(draft_id="d1")
        mock_client.send_draft.assert_called_once_with("d1")


class TestTrash:
    def test_trash_delegates(self, mcp_server, mock_gmail):
        mock_client, _, _ = register_with_env(mcp_server, mock_gmail)
        mock_client.trash_messages.return_value = {"succeeded": 2, "failed": 0}

        fn = get_tool_fn(mcp_server, "trash_gmail_messages")
        result = fn(message_ids=["m1", "m2"])
        mock_client.trash_messages.assert_called_once_with(["m1", "m2"])
        assert result["succeeded"] == 2
