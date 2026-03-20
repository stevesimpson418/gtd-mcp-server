"""FastMCP tool definitions for Gmail."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.resources import BinaryResource
from pydantic import Field

from gtd_mcp.gmail.auth import GmailAuth
from gtd_mcp.gmail.client import GmailClient

logger = logging.getLogger(__name__)


def register_gmail_tools(mcp: FastMCP) -> None:
    """Register all Gmail tools with the MCP server.

    Requires GMAIL_CREDENTIALS_PATH and GMAIL_TOKEN_PATH env vars.
    If missing, logs a warning and skips registration.
    """
    credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH")
    token_path = os.getenv("GMAIL_TOKEN_PATH")

    if not credentials_path or not token_path:
        logger.warning("GMAIL_CREDENTIALS_PATH or GMAIL_TOKEN_PATH not set — Gmail tools disabled")
        return

    auth = GmailAuth(credentials_path, token_path)
    try:
        service = auth.get_service()
    except FileNotFoundError as e:
        logger.warning("Gmail credentials not found: %s — Gmail tools disabled", e)
        return
    except Exception as e:
        logger.warning("Gmail auth failed: %s — Gmail tools disabled", e)
        return

    client = GmailClient(service)

    # --- Read tools ---

    @mcp.tool(annotations={"readOnlyHint": True})
    def search_gmail(
        query: Annotated[
            str,
            Field(
                description=(
                    "Gmail search query using standard Gmail syntax. "
                    "Examples: 'is:unread in:inbox', 'from:boss@company.com', "
                    "'subject:invoice after:2026/01/01', 'has:attachment'"
                )
            ),
        ],
        max_results: Annotated[
            int,
            Field(
                default=20,
                description="Maximum number of messages to return (1-100).",
                ge=1,
                le=100,
            ),
        ] = 20,
    ) -> list[dict]:
        """Search Gmail messages matching a query.

        Uses standard Gmail search syntax. Returns message summaries
        (id, thread_id, subject, from, date, snippet). Use read_gmail_message()
        for the full body.

        Args:
            query: Gmail search query, e.g. "is:unread in:inbox", "from:alice@example.com".
            max_results: Max messages to return (default 20, max 100).

        Example:
            search_gmail(query="is:unread in:inbox")
            search_gmail(query="from:noreply@github.com after:2026/03/01", max_results=50)

        Returns:
            [{"id": "abc123", "thread_id": "xyz", "subject": "Hello", "from": "...",
              "date": "...", "snippet": "...", "label_ids": ["INBOX", "UNREAD"]}]
        """
        return client.search_messages(query, max_results)

    @mcp.tool(annotations={"readOnlyHint": True})
    def read_gmail_message(
        message_id: Annotated[str, Field(description="The Gmail message ID (from search_gmail)")],
    ) -> dict:
        """Read a full Gmail message including the body text.

        Args:
            message_id: The message ID from search_gmail() results.

        Example:
            read_gmail_message(message_id="18e2f3a4b5c6d7e8")

        Returns:
            {"id": "...", "subject": "...", "from": "...", "to": "...", "date": "...",
             "body": "Full message text...", "label_ids": [...]}
        """
        return client.read_message(message_id)

    @mcp.tool(annotations={"readOnlyHint": True})
    def read_gmail_thread(
        thread_id: Annotated[str, Field(description="The Gmail thread ID (from search_gmail)")],
    ) -> dict:
        """Read all messages in a Gmail thread.

        Args:
            thread_id: The thread ID from search_gmail() results.

        Example:
            read_gmail_thread(thread_id="18e2f3a4b5c6d7e8")

        Returns:
            {"thread_id": "...", "message_count": 3, "messages": [{...}, {...}, {...}]}
        """
        return client.read_thread(thread_id)

    @mcp.tool(annotations={"readOnlyHint": True})
    def list_gmail_labels() -> list[dict]:
        """List all Gmail labels.

        Returns both system labels (INBOX, SENT, TRASH, etc.) and user-created labels.
        Use label names with apply_gmail_label() and remove_gmail_label().

        Example:
            list_gmail_labels()

        Returns:
            [{"id": "INBOX", "name": "INBOX", "type": "system"},
             {"id": "Label_123", "name": "Work", "type": "user"}]
        """
        return client.list_labels()

    # --- Archive / move ---

    @mcp.tool
    def archive_gmail_messages(
        message_ids: Annotated[
            list[str],
            Field(description="List of Gmail message IDs to archive (remove from inbox)."),
        ],
    ) -> dict:
        """Archive Gmail messages by removing the INBOX label.

        Messages remain accessible via search and labels, just removed from inbox.

        Args:
            message_ids: List of message IDs from search_gmail().

        Example:
            archive_gmail_messages(message_ids=["msg1", "msg2", "msg3"])

        Returns:
            {"modified": 3}
        """
        return client.archive_messages(message_ids)

    @mcp.tool
    def bulk_archive_gmail(
        query: Annotated[
            str,
            Field(
                description=(
                    "Gmail search query — all matching messages will be archived. "
                    "Use specific queries to avoid archiving important mail."
                )
            ),
        ],
    ) -> dict:
        """Search for Gmail messages and archive all results in one operation.

        This is the most powerful cleanup tool — clears matching mail from inbox
        in a single call. Use specific queries to target exactly what you want.

        Args:
            query: Gmail search query, e.g. "from:noreply@marketing.com in:inbox".

        Example:
            bulk_archive_gmail(query="from:noreply@news.example.com in:inbox")
            bulk_archive_gmail(query="is:unread in:inbox older_than:7d subject:newsletter")

        Returns:
            {"archived": 42, "query": "from:noreply@news.example.com in:inbox"}
        """
        return client.bulk_archive(query)

    # --- Labels ---

    @mcp.tool
    def apply_gmail_label(
        message_ids: Annotated[list[str], Field(description="List of Gmail message IDs.")],
        label_name: Annotated[
            str,
            Field(
                description=(
                    "Label name to apply (case-insensitive). "
                    "Use list_gmail_labels() to see available labels."
                )
            ),
        ],
    ) -> dict:
        """Apply a label to Gmail messages.

        Args:
            message_ids: List of message IDs.
            label_name: The label name, e.g. "Work", "Follow Up".

        Example:
            apply_gmail_label(message_ids=["msg1", "msg2"], label_name="Work")

        Returns:
            {"modified": 2}
        """
        return client.apply_label(message_ids, label_name)

    @mcp.tool
    def remove_gmail_label(
        message_ids: Annotated[list[str], Field(description="List of Gmail message IDs.")],
        label_name: Annotated[
            str,
            Field(description="Label name to remove (case-insensitive)."),
        ],
    ) -> dict:
        """Remove a label from Gmail messages.

        Args:
            message_ids: List of message IDs.
            label_name: The label name to remove.

        Example:
            remove_gmail_label(message_ids=["msg1"], label_name="Work")

        Returns:
            {"modified": 1}
        """
        return client.remove_label(message_ids, label_name)

    @mcp.tool
    def create_gmail_label(
        name: Annotated[str, Field(description="Name for the new label.")],
        text_color: Annotated[
            str | None,
            Field(default=None, description="Text color hex code, e.g. '#ffffff'."),
        ] = None,
        background_color: Annotated[
            str | None,
            Field(default=None, description="Background color hex code, e.g. '#4986e7'."),
        ] = None,
    ) -> dict:
        """Create a new Gmail label.

        Args:
            name: The label name, e.g. "Receipts", "Project X".
            text_color: Optional text color (hex), e.g. "#ffffff".
            background_color: Optional background color (hex), e.g. "#4986e7".

        Example:
            create_gmail_label(name="Receipts")
            create_gmail_label(name="Urgent", text_color="#ffffff", background_color="#cc3a21")

        Returns:
            {"id": "Label_123", "name": "Receipts"}
        """
        return client.create_label(name, text_color=text_color, background_color=background_color)

    # --- Read state ---

    @mcp.tool
    def mark_gmail_read(
        message_ids: Annotated[
            list[str], Field(description="List of Gmail message IDs to mark as read.")
        ],
    ) -> dict:
        """Mark Gmail messages as read.

        Args:
            message_ids: List of message IDs.

        Example:
            mark_gmail_read(message_ids=["msg1", "msg2"])

        Returns:
            {"modified": 2}
        """
        return client.mark_read(message_ids)

    @mcp.tool
    def mark_gmail_unread(
        message_ids: Annotated[
            list[str], Field(description="List of Gmail message IDs to mark as unread.")
        ],
    ) -> dict:
        """Mark Gmail messages as unread.

        Args:
            message_ids: List of message IDs.

        Example:
            mark_gmail_unread(message_ids=["msg1"])

        Returns:
            {"modified": 1}
        """
        return client.mark_unread(message_ids)

    # --- Star / Important ---

    @mcp.tool
    def star_gmail_message(
        message_ids: Annotated[list[str], Field(description="List of Gmail message IDs to star.")],
    ) -> dict:
        """Star Gmail messages.

        Adds the STARRED label to messages, making them appear in the
        Starred view in Gmail.

        Args:
            message_ids: List of message IDs from search_gmail().

        Example:
            star_gmail_message(message_ids=["msg1", "msg2"])

        Returns:
            {"modified": 2}
        """
        return client.star_messages(message_ids)

    @mcp.tool
    def mark_gmail_important(
        message_ids: Annotated[
            list[str], Field(description="List of Gmail message IDs to mark as important.")
        ],
    ) -> dict:
        """Mark Gmail messages as important.

        Adds the IMPORTANT label to messages, making them appear in the
        Important view in Gmail.

        Args:
            message_ids: List of message IDs from search_gmail().

        Example:
            mark_gmail_important(message_ids=["msg1"])

        Returns:
            {"modified": 1}
        """
        return client.mark_important(message_ids)

    # --- Compose / Send ---

    @mcp.tool
    def create_gmail_draft(
        to: Annotated[str, Field(description="Recipient email address.")],
        subject: Annotated[str, Field(description="Email subject line.")],
        body: Annotated[str, Field(description="Email body text (plain text).")],
        thread_id: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "Thread ID for in-thread replies. "
                    "Get from search_gmail() or read_gmail_message()."
                ),
            ),
        ] = None,
        cc: Annotated[
            str | None,
            Field(default=None, description="CC recipients (comma-separated email addresses)."),
        ] = None,
    ) -> dict:
        """Create a draft email in Gmail.

        Use thread_id to create an in-thread reply. The draft is saved
        but not sent — use send_gmail_draft() to send it.

        Args:
            to: Recipient email address.
            subject: Subject line.
            body: Plain text body.
            thread_id: Optional thread ID for replies.
            cc: Optional CC addresses.

        Example:
            create_gmail_draft(to="alice@example.com", subject="Re: Meeting",
                               body="Sounds good, see you then!", thread_id="thread_abc")

        Returns:
            {"draft_id": "draft_123", "message_id": "msg_456", "thread_id": "thread_abc"}
        """
        return client.create_draft(to, subject, body, thread_id=thread_id, cc=cc)

    @mcp.tool
    def send_gmail(
        to: Annotated[str, Field(description="Recipient email address.")],
        subject: Annotated[str, Field(description="Email subject line.")],
        body: Annotated[str, Field(description="Email body text (plain text).")],
        cc: Annotated[
            str | None,
            Field(default=None, description="CC recipients (comma-separated email addresses)."),
        ] = None,
    ) -> dict:
        """Send an email directly via Gmail.

        Sends immediately — no draft is created. For sensitive emails,
        consider create_gmail_draft() first to review before sending.

        Args:
            to: Recipient email address.
            subject: Subject line.
            body: Plain text body.
            cc: Optional CC addresses.

        Example:
            send_gmail(to="bob@example.com", subject="Quick question",
                       body="Hey Bob, what time is the meeting?")

        Returns:
            {"message_id": "msg_789", "thread_id": "thread_xyz"}
        """
        return client.send_email(to, subject, body, cc=cc)

    @mcp.tool
    def send_gmail_draft(
        draft_id: Annotated[
            str,
            Field(description="The draft ID to send (from create_gmail_draft())."),
        ],
    ) -> dict:
        """Send a previously created Gmail draft.

        Args:
            draft_id: The draft ID from create_gmail_draft().

        Example:
            send_gmail_draft(draft_id="draft_123")

        Returns:
            {"message_id": "msg_789", "thread_id": "thread_xyz"}
        """
        return client.send_draft(draft_id)

    # --- Attachments ---

    @mcp.tool(annotations={"readOnlyHint": True})
    def list_gmail_attachments(
        message_id: Annotated[str, Field(description="The Gmail message ID.")],
    ) -> list[dict]:
        """List attachments on a Gmail message.

        Returns metadata for each attachment (id, filename, mime_type, size).
        Use with read_gmail_attachment() or download_gmail_attachment().

        Args:
            message_id: The message ID from search_gmail().

        Example:
            list_gmail_attachments(message_id="18e2f3a4b5c6d7e8")

        Returns:
            [{"attachment_id": "att_1", "filename": "report.pdf",
              "mime_type": "application/pdf", "size": 12345, "part_id": "2"}]
        """
        return client.list_attachments(message_id)

    @mcp.tool(annotations={"readOnlyHint": True})
    def read_gmail_attachment(
        message_id: Annotated[str, Field(description="The Gmail message ID.")],
        attachment_id: Annotated[
            str, Field(description="The attachment ID from list_gmail_attachments().")
        ],
        filename: Annotated[str, Field(description="Original filename of the attachment.")],
        mime_type: Annotated[str, Field(description="MIME type of the attachment.")],
    ) -> dict:
        """Read attachment content inline.

        Text files (text/*, JSON, CSV, XML) are returned as decoded text.
        Binary files (PDF, images, etc.) are returned as base64-encoded strings.

        Args:
            message_id: The message ID.
            attachment_id: The attachment ID from list_gmail_attachments().
            filename: The attachment filename.
            mime_type: The attachment MIME type.

        Example:
            read_gmail_attachment(message_id="msg1", attachment_id="att1",
                                 filename="data.csv", mime_type="text/csv")

        Returns:
            {"filename": "data.csv", "mime_type": "text/csv", "size": 1234,
             "encoding": "text", "content": "name,value\\nalice,42"}
        """
        return client.read_attachment_content(message_id, attachment_id, filename, mime_type)

    @mcp.tool
    def download_gmail_attachment(
        message_id: Annotated[str, Field(description="The Gmail message ID.")],
        attachment_id: Annotated[
            str, Field(description="The attachment ID from list_gmail_attachments().")
        ],
        filename: Annotated[str, Field(description="Original filename of the attachment.")],
    ) -> dict:
        """Download a Gmail attachment, returning a resource URI to fetch it.

        The attachment content is registered as an MCP resource. Use the
        returned resource_uri to read the binary content via the MCP protocol.

        Args:
            message_id: The message ID.
            attachment_id: The attachment ID from list_gmail_attachments().
            filename: The attachment filename.

        Example:
            download_gmail_attachment(message_id="msg1", attachment_id="att1",
                                     filename="report.pdf")

        Returns:
            {"filename": "report.pdf", "size": 12345,
             "resource_uri": "attachment://gmail/msg1/report.pdf"}
        """
        result = client.download_attachment(message_id, attachment_id, filename)
        uri = f"attachment://gmail/{message_id}/{result['filename']}"
        resource = BinaryResource(uri=uri, data=result["data"])
        mcp.add_resource(resource)
        return {
            "filename": result["filename"],
            "size": result["size"],
            "resource_uri": uri,
        }

    # --- Delete ---

    @mcp.tool(annotations={"destructiveHint": True})
    def trash_gmail_messages(
        message_ids: Annotated[
            list[str],
            Field(description="List of Gmail message IDs to move to trash."),
        ],
    ) -> dict:
        """Move Gmail messages to trash.

        Messages in trash are recoverable for 30 days, then permanently deleted.
        This is safer than permanent deletion which is not supported.

        Args:
            message_ids: List of message IDs to trash.

        Example:
            trash_gmail_messages(message_ids=["msg1", "msg2"])

        Returns:
            {"succeeded": 2, "failed": 0}
        """
        return client.trash_messages(message_ids)
