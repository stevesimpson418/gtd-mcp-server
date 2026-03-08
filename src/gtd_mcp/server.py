"""GTD MCP Server entry point."""

from dotenv import load_dotenv
from fastmcp import FastMCP

from gtd_mcp.gmail.tools import register_gmail_tools
from gtd_mcp.todoist.tools import register_todoist_tools

mcp = FastMCP("gtd-mcp-server")
register_todoist_tools(mcp)
register_gmail_tools(mcp)


def main():
    load_dotenv()
    mcp.run()


if __name__ == "__main__":
    main()
