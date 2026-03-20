"""Tests for GmailClient operations."""

from __future__ import annotations

import base64
from pathlib import Path
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


# --- Attachment helpers ---


def make_attachment_message(
    msg_id: str = "msg_att",
    attachments: list[dict] | None = None,
    inline_images: bool = False,
    nested: bool = False,
) -> dict:
    """Build a Gmail message with attachment parts.

    Args:
        attachments: List of dicts with keys: filename, mime_type, size, attachment_id.
        inline_images: If True, include an inline image part (no filename).
        nested: If True, wrap text parts inside a nested multipart/alternative.
    """
    if attachments is None:
        attachments = [
            {
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": 12345,
                "attachment_id": "att_1",
            }
        ]

    plain_body = base64.urlsafe_b64encode(b"Email body text").decode()

    text_part = {"mimeType": "text/plain", "body": {"data": plain_body}}
    attachment_parts = []
    for att in attachments:
        attachment_parts.append(
            {
                "partId": f"part_{att['attachment_id']}",
                "mimeType": att["mime_type"],
                "filename": att["filename"],
                "body": {
                    "attachmentId": att["attachment_id"],
                    "size": att["size"],
                },
            }
        )

    parts = []
    if nested:
        html_body = base64.urlsafe_b64encode(b"<p>Email body</p>").decode()
        parts.append(
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    text_part,
                    {"mimeType": "text/html", "body": {"data": html_body}},
                ],
            }
        )
    else:
        parts.append(text_part)

    if inline_images:
        parts.append(
            {
                "partId": "part_inline",
                "mimeType": "image/png",
                "filename": "",
                "body": {"attachmentId": "inline_1", "size": 500},
                "headers": [
                    {"name": "Content-Disposition", "value": "inline"},
                ],
            }
        )

    parts.extend(attachment_parts)

    return {
        "id": msg_id,
        "threadId": "thread_1",
        "snippet": "Preview...",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "Subject", "value": "With attachments"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "Date", "value": "Wed, 3 Mar 2026"},
                {"name": "To", "value": "me@example.com"},
                {"name": "Cc", "value": ""},
            ],
            "mimeType": "multipart/mixed",
            "parts": parts,
        },
    }


# --- List attachments tests ---


class TestListAttachments:
    def test_multipart_with_attachments(self):
        client, svc = make_client()
        msg = make_attachment_message(
            attachments=[
                {
                    "filename": "report.pdf",
                    "mime_type": "application/pdf",
                    "size": 12345,
                    "attachment_id": "att_1",
                },
                {
                    "filename": "data.csv",
                    "mime_type": "text/csv",
                    "size": 678,
                    "attachment_id": "att_2",
                },
            ]
        )
        svc.users().messages().get().execute.return_value = msg

        result = client.list_attachments("msg_att")
        assert len(result) == 2
        assert result[0]["filename"] == "report.pdf"
        assert result[0]["mime_type"] == "application/pdf"
        assert result[0]["size"] == 12345
        assert result[0]["attachment_id"] == "att_1"
        assert result[0]["part_id"] == "part_att_1"
        assert result[1]["filename"] == "data.csv"

    def test_no_attachments(self):
        client, svc = make_client()
        msg = make_multipart_message()
        svc.users().messages().get().execute.return_value = msg

        result = client.list_attachments("msg_1")
        assert result == []

    def test_inline_images_excluded(self):
        client, svc = make_client()
        msg = make_attachment_message(inline_images=True)
        svc.users().messages().get().execute.return_value = msg

        result = client.list_attachments("msg_att")
        assert len(result) == 1
        assert result[0]["filename"] == "report.pdf"

    def test_nested_multipart(self):
        client, svc = make_client()
        msg = make_attachment_message(nested=True)
        svc.users().messages().get().execute.return_value = msg

        result = client.list_attachments("msg_att")
        assert len(result) == 1
        assert result[0]["filename"] == "report.pdf"


# --- Get attachment tests ---


class TestGetAttachment:
    def test_fetch_and_decode(self):
        client, svc = make_client()
        raw_data = b"PDF file contents here"
        encoded = base64.urlsafe_b64encode(raw_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(raw_data),
        }

        result = client.get_attachment("msg_1", "att_1")
        assert result == raw_data

    def test_api_error(self):
        client, svc = make_client()
        svc.users().messages().attachments().get().execute.side_effect = Exception("Not found")

        with pytest.raises(GmailAPIError, match="Failed to get attachment"):
            client.get_attachment("msg_1", "bad_att")


# --- Read attachment content tests ---


class TestReadAttachmentContent:
    def test_text_csv_decoded(self):
        client, svc = make_client()
        csv_data = b"name,value\nalice,42"
        encoded = base64.urlsafe_b64encode(csv_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(csv_data),
        }

        result = client.read_attachment_content("msg_1", "att_1", "data.csv", "text/csv")
        assert result["encoding"] == "text"
        assert result["content"] == "name,value\nalice,42"
        assert result["filename"] == "data.csv"
        assert result["mime_type"] == "text/csv"
        assert result["size"] == len(csv_data)

    def test_binary_pdf_base64(self):
        client, svc = make_client()
        pdf_data = b"%PDF-1.4 binary content"
        encoded = base64.urlsafe_b64encode(pdf_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(pdf_data),
        }

        result = client.read_attachment_content("msg_1", "att_1", "doc.pdf", "application/pdf")
        assert result["encoding"] == "base64"
        assert base64.b64decode(result["content"]) == pdf_data

    def test_json_as_text(self):
        client, svc = make_client()
        json_data = b'{"key": "value"}'
        encoded = base64.urlsafe_b64encode(json_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(json_data),
        }

        result = client.read_attachment_content("msg_1", "att_1", "data.json", "application/json")
        assert result["encoding"] == "text"
        assert result["content"] == '{"key": "value"}'

    def test_xml_as_text(self):
        client, svc = make_client()
        xml_data = b"<root><item>value</item></root>"
        encoded = base64.urlsafe_b64encode(xml_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(xml_data),
        }

        result = client.read_attachment_content("msg_1", "att_1", "data.xml", "application/xml")
        assert result["encoding"] == "text"
        assert result["content"] == "<root><item>value</item></root>"


# --- Download attachment tests ---


class TestDownloadAttachment:
    def test_saves_file(self, tmp_path):
        client, svc = make_client()
        file_data = b"file contents"
        encoded = base64.urlsafe_b64encode(file_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(file_data),
        }

        result = client.download_attachment("msg_1", "att_1", "report.pdf", str(tmp_path))
        assert result["filename"] == "report.pdf"
        assert result["size"] == len(file_data)
        saved = Path(result["path"])
        assert saved.exists()
        assert saved.read_bytes() == file_data

    def test_invalid_dir_raises(self):
        client, _ = make_client()
        with pytest.raises(ValueError, match="not a valid directory"):
            client.download_attachment("msg_1", "att_1", "file.pdf", "/nonexistent/path")

    def test_path_traversal_sanitized(self, tmp_path):
        client, svc = make_client()
        file_data = b"data"
        encoded = base64.urlsafe_b64encode(file_data).decode()
        svc.users().messages().attachments().get().execute.return_value = {
            "data": encoded,
            "size": len(file_data),
        }

        result = client.download_attachment("msg_1", "att_1", "../../etc/passwd", str(tmp_path))
        assert result["filename"] == "passwd"
        assert str(tmp_path) in result["path"]


# --- _parse_full_message attachment fields ---


class TestParseFullMessageAttachments:
    def test_has_attachments_true(self):
        client, _ = make_client()
        msg = make_attachment_message()
        result = client._parse_full_message(msg)
        assert result["has_attachments"] is True
        assert result["attachment_count"] == 1

    def test_has_attachments_false(self):
        client, _ = make_client()
        msg = make_message()
        result = client._parse_full_message(msg)
        assert result["has_attachments"] is False
        assert result["attachment_count"] == 0

    def test_multiple_attachments_count(self):
        client, _ = make_client()
        msg = make_attachment_message(
            attachments=[
                {
                    "filename": "a.pdf",
                    "mime_type": "application/pdf",
                    "size": 100,
                    "attachment_id": "att_1",
                },
                {
                    "filename": "b.csv",
                    "mime_type": "text/csv",
                    "size": 200,
                    "attachment_id": "att_2",
                },
                {
                    "filename": "c.docx",
                    "mime_type": "application/vnd.openxmlformats",
                    "size": 300,
                    "attachment_id": "att_3",
                },
            ]
        )
        result = client._parse_full_message(msg)
        assert result["has_attachments"] is True
        assert result["attachment_count"] == 3
