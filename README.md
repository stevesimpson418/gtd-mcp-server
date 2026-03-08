# GTD MCP Server

A local [MCP](https://modelcontextprotocol.io/) server that gives Claude native, tool-level access to **Todoist** and **Gmail** for GTD (Getting Things Done) workflows. Runs locally via stdio transport — all tokens and credentials stay on your machine.

## Prerequisites

- Python 3.12+
- A [Todoist](https://todoist.com) account (for the Todoist module)
- A Google account with Gmail API enabled (for the Gmail module)

## Quick Start

```bash
# Clone the repo
git clone https://github.com/your-username/gtd-mcp-server.git
cd gtd-mcp-server

# Create a virtual environment and install
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure your credentials
cp .env.example .env
# Edit .env — see sections below for each module
```

### Setting up Todoist

1. Open [Todoist Settings > Integrations > Developer](https://app.todoist.com/app/settings/integrations/developer)
2. Copy your API token
3. Paste it into your `.env` file as `TODOIST_API_TOKEN=your_token_here`

### Setting up Gmail

1. Create a [Google Cloud project](https://console.cloud.google.com/)
2. Enable the **Gmail API**: APIs & Services > Library > Gmail API
3. Create **OAuth 2.0 credentials**: APIs & Services > Credentials > Create > OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON file and save it as `credentials/gmail_credentials.json`
4. Run the OAuth consent flow once to generate a token:

```bash
source .venv/bin/activate
python -c "
from gtd_mcp.gmail.auth import GmailAuth
auth = GmailAuth('credentials/gmail_credentials.json', 'credentials/token.json')
auth.get_service()
print('Token saved to credentials/token.json')
"
```

A browser window will open — sign in and grant permissions. The token auto-refreshes after this.

Update your `.env`:

```
GMAIL_CREDENTIALS_PATH=credentials/gmail_credentials.json
GMAIL_TOKEN_PATH=credentials/token.json
```

### Adding to Claude Desktop

Add the following to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS).

> **Note:** Use the absolute path to the Python binary inside your virtualenv for `command`.

```json
{
  "mcpServers": {
    "gtd": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "gtd_mcp.server"],
      "env": {
        "TODOIST_API_TOKEN": "your_token_here",
        "GMAIL_CREDENTIALS_PATH": "/absolute/path/to/credentials/gmail_credentials.json",
        "GMAIL_TOKEN_PATH": "/absolute/path/to/credentials/token.json"
      }
    }
  }
}
```

Restart Claude Desktop after saving. You should see all tools in the tools menu.

## Available Tools

### Todoist

> **Important:** Project and label names are dynamic — they come from your Todoist account.
> Use `list_todoist_projects()` and `list_todoist_labels()` to discover valid values.

| Tool | Description |
|------|-------------|
| `list_todoist_projects()` | List all projects (id, name) — use to discover valid project names |
| `get_project_tasks(project)` | Get all tasks from a project by name (case-insensitive) |
| `list_todoist_labels()` | List all personal labels (id, name, color) |
| `create_task(content, project?, labels?, due_date?, description?)` | Create a new task |
| `update_task(task_id, content?, labels?, due_date?, description?)` | Update fields on a task |
| `move_task(task_id, project)` | Move a task to a different project |
| `complete_task(task_id)` | Mark a task as complete |
| `delete_task(task_id)` | Permanently delete a task |
| `batch_update_tasks(operations)` | Batch update multiple tasks in one API call |
| `create_todoist_label(name, color?)` | Create a new label |
| `rename_todoist_label(label_id, new_name)` | Rename an existing label |
| `delete_todoist_label(label_id)` | Delete a label |

#### Todoist Usage Examples

**Triage your inbox:**

```
1. list_todoist_projects()           → find your project names
2. get_project_tasks(project="Inbox") → see what needs processing
3. batch_update_tasks(operations=[
     {"id": "123", "labels": ["Home"], "project": "Active"},
     {"id": "456", "project": "Backlog"},
     {"id": "789", "labels": ["Work"], "due_date": "tomorrow", "project": "Active"}
   ])
```

**Create a task with context:**

```
create_task(
    content="Book dentist appointment",
    project="Active",
    labels=["Health", "Admin"],
    due_date="next Monday",
    description="Dr. Smith, call during lunch"
)
```

### Gmail

> **Setup required:** You need a Google Cloud project with the Gmail API enabled and OAuth 2.0 credentials.
> See [Setting up Gmail](#setting-up-gmail) above.

| Tool | Description |
|------|-------------|
| `search_gmail(query, max_results?)` | Search messages using Gmail query syntax (e.g. `is:unread in:inbox`) |
| `read_gmail_message(message_id)` | Read a full message including body text |
| `read_gmail_thread(thread_id)` | Read all messages in a thread |
| `list_gmail_labels()` | List all labels (system and user-created) |
| `archive_gmail_messages(message_ids)` | Archive messages (remove from inbox) |
| `bulk_archive_gmail(query)` | Search and archive all matching messages in one call |
| `apply_gmail_label(message_ids, label_name)` | Apply a label to messages |
| `remove_gmail_label(message_ids, label_name)` | Remove a label from messages |
| `create_gmail_label(name, text_color?, background_color?)` | Create a new label |
| `mark_gmail_read(message_ids)` | Mark messages as read |
| `mark_gmail_unread(message_ids)` | Mark messages as unread |
| `create_gmail_draft(to, subject, body, thread_id?, cc?)` | Create a draft email |
| `send_gmail(to, subject, body, cc?)` | Send an email directly |
| `send_gmail_draft(draft_id)` | Send a previously created draft |
| `trash_gmail_messages(message_ids)` | Move messages to trash (recoverable for 30 days) |

#### Gmail Usage Examples

**Triage your inbox:**

```
1. search_gmail(query="is:unread in:inbox")          → see what's new
2. read_gmail_message(message_id="msg_123")           → read the full message
3. archive_gmail_messages(message_ids=["msg_123"])     → archive after reading
```

**Bulk cleanup:**

```
bulk_archive_gmail(query="from:noreply@marketing.com in:inbox")
bulk_archive_gmail(query="is:unread in:inbox older_than:7d subject:newsletter")
```

**Draft a reply:**

```
create_gmail_draft(
    to="alice@example.com",
    subject="Re: Meeting",
    body="Sounds good, see you then!",
    thread_id="thread_abc"
)
```

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov=gtd_mcp --cov-report=term-missing

# Lint
ruff check src/ tests/

# Format
black src/ tests/
```

## Status

- [x] Project scaffolding
- [x] Todoist module (REST v2 + Sync API v1 batch)
- [x] Gmail module (read, archive, compose, labels, drafts, send)
- [ ] Outlook module (future)
