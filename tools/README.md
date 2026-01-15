# llode Tools

This directory contains tool modules that extend llode's capabilities with additional functionality.

## How Tools Work

1. **Discovery**: llode automatically discovers all `.py` files in this directory at startup
2. **Loading**: Each tool module is loaded and its `register_tools()` function is called
3. **Registration**: Tools register using the same `ToolRegistry` API as core tools
4. **Integration**: Tool functions appear in the system prompt and are available to the LLM

## Creating a Tool Module

### Basic Structure

```python
"""
Tool module description shown in /plugins command.

Dependencies:
- package>=version (list any required packages)

Description:
What this tool module does.
"""

def register_tools(registry, git_root):
    """
    Called by llode to register tools.
    
    Args:
        registry: ToolRegistry instance to register tools with
        git_root: Path to the git repository root
    """
    
    @registry.register("tool_name", """Tool description for LLM.
    
    Parameters:
    - param1: description
    - param2: description
    
    What the tool does and returns.""")
    def tool_name(param1: str, param2: str = "default"):
        """Implementation."""
        # Your code here
        return "result string"
```

### Guidelines

1. **Error Handling**: Tools should handle errors gracefully
2. **Dependencies**: Document any required packages in the docstring
3. **Return Values**: Always return strings (tools output text to the LLM)
4. **File Access**: Use the provided `git_root` path for file operations
5. **Naming**: Use descriptive tool names that don't conflict with core tools

### Accessing Core Utilities

Tool modules can access llode's core functions:

```python
def register_tools(registry, git_root):
    import sys
    parent_module = sys.modules['__main__']
    
    # Access core functions
    validate_path = parent_module.validate_path
    get_gitignore_spec = parent_module.get_gitignore_spec
    walk_files = parent_module.walk_files
    is_dotfile = parent_module.is_dotfile
```

## Included Tools

### codebase_index.py

Semantic code understanding and search for Python projects.

**Tools:**
- `index_codebase()` - Build/update semantic index
- `find_symbol(name)` - Find symbol definitions and references
- `analyze_dependencies(path)` - Show import relationships
- `list_symbols(path)` - List all symbols in a file

**Storage:** Creates `.llode/index.db` SQLite database

### document_conversion.py

Document format conversion using pandoc and pdftotext.

**Tools:**
- `convert_to_markdown(path)` - Convert documents to markdown
- `convert_from_markdown(path, format)` - Convert markdown to other formats

**Dependencies:** pandoc, poppler-utils (for pdftotext)

### git_operations.py

Git version control operations.

**Tools:**
- `git_add(paths)` - Stage files for commit
- `git_commit(message)` - Create a commit
- `git_diff(staged, file_path)` - Show changes

### todo_manager.py

Task list management.

**Tools:**
- `todo_read()` - Read current todo list
- `todo_write(content)` - Update todo list

**Storage:** Uses `llode_todo.json` in project root

### web_tools.py

Web content fetching.

**Tools:**
- `fetch_url(url)` - Fetch content from HTTP/HTTPS URLs

## Tool Ideas

Some ideas for future tool modules:

- **test_runner**: Run pytest/unittest and report results
- **linter**: Run pylint/flake8/mypy and show issues
- **git_advanced**: More git operations (branch, merge, stash)
- **docker**: Interact with Docker containers
- **api_client**: Make HTTP requests with authentication
- **diagram**: Generate mermaid/graphviz diagrams from code
- **refactor**: Safe refactoring operations using AST manipulation

## Troubleshooting

### Tool Not Loading

Check `/plugins` command output for error messages:
- **Missing register_tools**: Add the required function
- **Import errors**: Install missing dependencies
- **Syntax errors**: Fix Python syntax issues

### Tool Errors at Runtime

- Check .llode/log.md for detailed error messages
- Ensure tool returns strings, not other types
- Validate all file paths relative to git_root
- Handle missing files/data gracefully

## Contributing Tools

When contributing tool modules:

1. Document all parameters clearly
2. Include usage examples in tool descriptions
3. Add error messages that help users fix issues
4. Test with various project structures
5. Keep dependencies minimal when possible