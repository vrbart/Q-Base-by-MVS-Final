"""Built-in MCP server adapters."""

from .filesystem import read_file, write_file
from .shell import exec_shell
from .zip_vault import list_entries, read_entry

__all__ = ["read_file", "write_file", "exec_shell", "list_entries", "read_entry"]
