"""Tests for GmailClient operations."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from gtd_mcp.gmail.client import GmailClient
from gtd_mcp.gmail.exceptions import GmailAPIError


def make_client() -> tuple[GmailClient, MagicMock]:
    """Create a GmailClient with a mocked Gmail service."""
    mock_service = MagicMock()
    client = GmailClient(mock_service)
    return client, mock_service


def make_message(
    msg_id: str = "msg_1",
    thread_id: str = "thread_1",
    subject: str = "Test Subject",
    sender: str = "alice@example.com",
    date: str = "Mon, 1 Mar 2026 10:00:00 +0000",
    snippet: str = "Preview text...",
    body_text: str = "Hello world",
    label_ids: list[str] | None = None,
    format_type: str = "full",
) -> dict:
    """Build a realistic Gmail API message response."""
    encoded_body = base64.urlsafe_b64encode(body_text.encode()).decode()
    msg = {
        "id": msg_id,
        "threadId": thread_id,
        "snippet": snippet,
        "labelIds": label_ids or ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": date},
                {"name": "To", "value": "me@example.com"},
                {"name": "Cc", "value": ""},
            ],
        },
    }
    if format_type == "full":
        msg["payload"]["body"] = {"data": encoded_body}
    return msg


def make_multipart_message(msg_id: str = "msg_1") -> dict:
    """Build a multipart Gmail message."""
    plain_body = base64.urlsafe_b64encode(b"Plain text body").decode()
    html_body = base64.urlsafe_b64encode(b"<p>HTML body</p>").decode()
    return {
        "id": msg_id,
        "threadId": "thread_1",
        "snippet": "Preview...",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Multipart"},
                {"name": "From", "value": "bob@example.com"},
                {"name": "Date", "value": "Tue, 2 Mar 2026"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Cc", "value": ""},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": plain_body}},
                {"mimeType": "text/html", "body": {"data": html_body}},
            ],
        },
    }


# --- Search tests ---


class TestSearchMessages:
    def test_search_returns_summaries(self):
        client, svc = make_client()
        svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_1"}, {"id": "msg_2"}]
        }
        svc.users().messages().get().execute.side_effect = [
            make_message(msg_id="msg_1", format_type="metadata"),
            make_message(msg_id="msg_2", subject="Second", format_type="metadata"),
        ]

        results = client.search_messages("is:unread")
        assert len(results) == 2
        assert results[0]["id"] == "msg_1"
        assert results[0]["subject"] == "Test Subject"
        assert "body" not in results[0]

    def test_search_empty_results(self):
        client, svc = make_client()
        svc.users().messages().list().execute.return_value = {}

        results = client.search_messages("nonexistent")
        assert results == []

    def test_search_api_error(self):
        client, svc = make_client()
        svc.users().messages().list().execute.side_effect = Exception("API error")

        with pytest.raises(GmailAPIError, match="Failed to search"):
            client.search_messages("test")


# --- Read message tests ---


class TestReadMessage:
    def test_read_full_message(self):
        client, svc = make_client()
        svc.users().messages().get().execute.return_value = make_message()

        result = client.read_message("msg_1")
        assert result["id"] == "msg_1"
        assert result["subject"] == "Test Subject"
        assert result["body"] == "Hello world"
        assert result["from"] == "alice@example.com"

    def test_read_multipart_prefers_plain(self):
        client, svc = make_client()
        svc.users().messages().get().execute.return_value = make_multipart_message()

        result = client.read_message("msg_1")
        assert result["body"] == "Plain text body"

    def test_read_message_api_error(self):
        client, svc = make_client()
        svc.users().messages().get().execute.side_effect = Exception("Not found")

        with pytest.raises(GmailAPIError, match="Failed to read message"):
            client.read_message("bad_id")


# --- Read thread tests ---


class TestReadThread:
    def test_read_thread_returns_all_messages(self):
        client, svc = make_client()
        svc.users().threads().get().execute.return_value = {
            "messages": [make_message(msg_id="msg_1"), make_message(msg_id="msg_2")]
        }

        result = client.read_thread("thread_1")
        assert result["thread_id"] == "thread_1"
        assert result["message_count"] == 2
        assert len(result["messages"]) == 2

    def test_read_thread_api_error(self):
        client, svc = make_client()
        svc.users().threads().get().execute.side_effect = Exception("Fail")

        with pytest.raises(GmailAPIError, match="Failed to read thread"):
            client.read_thread("bad_id")


# --- Label tests ---


class TestLabels:
    def test_list_labels(self):
        client, svc = make_client()
        svc.users().labels().list().execute.return_value = {
            "labels": [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "Label_1", "name": "Work", "type": "user"},
            ]
        }

        labels = client.list_labels()
        assert len(labels) == 2
        assert labels[1] == {"id": "Label_1", "name": "Work", "type": "user"}

    def test_create_label(self):
        client, svc = make_client()
        svc.users().labels().create().execute.return_value = {
            "id": "Label_new",
            "name": "Receipts",
        }

        result = client.create_label("Receipts")
        assert result == {"id": "Label_new", "name": "Receipts"}

    def test_apply_label_resolves_name(self):
        client, svc = make_client()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_1", "name": "Work", "type": "user"}]
        }
        svc.users().messages().batchModify().execute.return_value = None

        result = client.apply_label(["msg_1"], "Work")
        assert result["modified"] == 1

    def test_apply_label_unknown_raises(self):
        client, svc = make_client()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_1", "name": "Work", "type": "user"}]
        }

        with pytest.raises(ValueError, match="Label 'Unknown' not found"):
            client.apply_label(["msg_1"], "Unknown")

    def test_remove_label(self):
        client, svc = make_client()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_1", "name": "Work", "type": "user"}]
        }
        svc.users().messages().batchModify().execute.return_value = None

        result = client.remove_label(["msg_1"], "Work")
        assert result["modified"] == 1

    def test_label_cache_reused(self):
        client, svc = make_client()
        svc.users().labels().list().execute.return_value = {
            "labels": [{"id": "Label_1", "name": "Work", "type": "user"}]
        }
        svc.users().messages().batchModify().execute.return_value = None

        client.apply_label(["msg_1"], "Work")
        client.apply_label(["msg_2"], "Work")
        # labels().list() should only be called once (cached)
        assert svc.users().labels().list().execute.call_count == 1


# --- Archive tests ---


class TestArchive:
    def test_archive_messages(self):
        client, svc = make_client()
        svc.users().messages().batchModify().execute.return_value = None

        result = client.archive_messages(["msg_1", "msg_2"])
        assert result["modified"] == 2

    def test_bulk_archive(self):
        client, svc = make_client()
        svc.users().messages().list().execute.return_value = {
            "messages": [{"id": "msg_1"}, {"id": "msg_2"}, {"id": "msg_3"}]
        }
        svc.users().messages().batchModify().execute.return_value = None

        result = client.bulk_archive("from:spam@example.com")
        assert result["archived"] == 3
        assert result["query"] == "from:spam@example.com"

    def test_bulk_archive_no_matches(self):
        client, svc = make_client()
        svc.users().messages().list().execute.return_value = {}

        result = client.bulk_archive("nonexistent")
        assert result["archived"] == 0

    def test_bulk_archive_api_error(self):
        client, svc = make_client()
        svc.users().messages().list().execute.side_effect = Exception("Fail")

        with pytest.raises(GmailAPIError, match="Failed to bulk archive"):
            client.bulk_archive("test")


# --- Read state tests ---


class TestReadState:
    def test_mark_read(self):
        client, svc = make_client()
        svc.users().messages().batchModify().execute.return_value = None

        result = client.mark_read(["msg_1"])
        assert result["modified"] == 1

    def test_mark_unread(self):
        client, svc = make_client()
        svc.users().messages().batchModify().execute.return_value = None

        result = client.mark_unread(["msg_1", "msg_2"])
        assert result["modified"] == 2


# --- Star / Important tests ---


class TestStarImportant:
    def test_star_messages(self):
        client, svc = make_client()
        svc.users().messages().batchModify().execute.return_value = None

        result = client.star_messages(["msg_1", "msg_2"])
        assert result["modified"] == 2

    def test_mark_important(self):
        client, svc = make_client()
        svc.users().messages().batchModify().execute.return_value = None

        result = client.mark_important(["msg_1"])
        assert result["modified"] == 1


# --- Compose / Send tests ---


class TestCompose:
    def test_create_draft(self):
        client, svc = make_client()
        svc.users().drafts().create().execute.return_value = {
            "id": "draft_1",
            "message": {"id": "msg_1", "threadId": "thread_1"},
        }

        result = client.create_draft("bob@example.com", "Hello", "Hi Bob")
        assert result["draft_id"] == "draft_1"
        assert result["message_id"] == "msg_1"

    def test_create_draft_with_thread(self):
        client, svc = make_client()
        svc.users().drafts().create().execute.return_value = {
            "id": "draft_1",
            "message": {"id": "msg_1", "threadId": "thread_existing"},
        }

        result = client.create_draft(
            "bob@example.com", "Re: Hello", "Reply text", thread_id="thread_existing"
        )
        assert result["thread_id"] == "thread_existing"

    def test_send_email(self):
        client, svc = make_client()
        svc.users().messages().send().execute.return_value = {
            "id": "msg_sent",
            "threadId": "thread_new",
        }

        result = client.send_email("bob@example.com", "Test", "Body text")
        assert result["message_id"] == "msg_sent"

    def test_send_draft(self):
        client, svc = make_client()
        svc.users().drafts().send().execute.return_value = {
            "id": "msg_sent",
            "threadId": "thread_1",
        }

        result = client.send_draft("draft_1")
        assert result["message_id"] == "msg_sent"

    def test_create_draft_api_error(self):
        client, svc = make_client()
        svc.users().drafts().create().execute.side_effect = Exception("Fail")

        with pytest.raises(GmailAPIError, match="Failed to create draft"):
            client.create_draft("to@x.com", "Sub", "Body")

    def test_send_email_api_error(self):
        client, svc = make_client()
        svc.users().messages().send().execute.side_effect = Exception("Fail")

        with pytest.raises(GmailAPIError, match="Failed to send email"):
            client.send_email("to@x.com", "Sub", "Body")

    def test_send_draft_api_error(self):
        client, svc = make_client()
        svc.users().drafts().send().execute.side_effect = Exception("Fail")

        with pytest.raises(GmailAPIError, match="Failed to send draft"):
            client.send_draft("bad_id")


# --- Trash tests ---


class TestTrash:
    def test_trash_messages(self):
        client, svc = make_client()
        svc.users().messages().trash().execute.return_value = {}

        result = client.trash_messages(["msg_1", "msg_2"])
        assert result["succeeded"] == 2
        assert result["failed"] == 0

    def test_trash_partial_failure(self):
        client, svc = make_client()
        svc.users().messages().trash().execute.side_effect = [
            {},
            Exception("Not found"),
            {},
        ]

        result = client.trash_messages(["msg_1", "msg_2", "msg_3"])
        assert result["succeeded"] == 2
        assert result["failed"] == 1


# --- MIME building tests ---


class TestBuildMime:
    def test_builds_basic_message(self):
        raw = GmailClient._build_mime_message("to@x.com", "Subject", "Body")
        decoded = base64.urlsafe_b64decode(raw).decode()
        assert "to@x.com" in decoded
        assert "Subject" in decoded
        assert "Body" in decoded

    def test_builds_message_with_cc(self):
        raw = GmailClient._build_mime_message("to@x.com", "Sub", "Body", cc="cc@x.com")
        decoded = base64.urlsafe_b64decode(raw).decode()
        assert "cc@x.com" in decoded


# --- Body extraction tests ---


class TestExtractBody:
    def test_simple_body(self):
        data = base64.urlsafe_b64encode(b"Simple text").decode()
        payload = {"body": {"data": data}}
        assert GmailClient._extract_body(payload) == "Simple text"

    def test_multipart_prefers_plain(self):
        plain = base64.urlsafe_b64encode(b"Plain").decode()
        html = base64.urlsafe_b64encode(b"<p>HTML</p>").decode()
        payload = {
            "parts": [
                {"mimeType": "text/html", "body": {"data": html}},
                {"mimeType": "text/plain", "body": {"data": plain}},
            ]
        }
        assert GmailClient._extract_body(payload) == "Plain"

    def test_multipart_falls_back_to_html(self):
        html = base64.urlsafe_b64encode(b"<p>HTML</p>").decode()
        payload = {
            "parts": [
                {"mimeType": "text/html", "body": {"data": html}},
            ]
        }
        assert GmailClient._extract_body(payload) == "<p>HTML</p>"

    def test_nested_multipart(self):
        plain = base64.urlsafe_b64encode(b"Nested plain").decode()
        payload = {
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {"mimeType": "text/plain", "body": {"data": plain}},
                    ],
                }
            ]
        }
        assert GmailClient._extract_body(payload) == "Nested plain"

    def test_empty_payload(self):
        assert GmailClient._extract_body({}) == ""
