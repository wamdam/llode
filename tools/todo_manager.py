"""
Todo management plugin.

Provides task tracking and todo list management.

Dependencies:
- None (uses stdlib only)

Description:
Built-in todo list system for tracking complex multi-step tasks.
Stores todos in llode_todo.json at the project root.
"""

import json


def register_tools(registry, git_root):
    """Register todo management tools."""
    
    @registry.register("todo_read", """Reads the current todo list from llode_todo.json.

Returns the current todo list or empty structure if none exists.""")
    def todo_read() -> str:
        """Read the todo list."""
        todo_path = git_root / "llode_todo.json"
        if todo_path.exists():
            return todo_path.read_text()
        return json.dumps({"tasks": []}, indent=2)

    @registry.register("todo_write", """Writes/updates the todo list to llode_todo.json.

Parameters:
- content: JSON string with the todo list structure

Expected format:
{
  "tasks": [
    {"id": 1, "description": "Task description", "status": "pending|in_progress|completed"}
  ]
}

CRITICAL: Mark in_progress BEFORE starting work. Only mark completed when FULLY done.""")
    def todo_write(content: str) -> str:
        """Write/update the todo list to llode_todo.json."""
        json.loads(content)  # Validate JSON
        (git_root / "llode_todo.json").write_text(content)
        return "Todo list updated successfully"