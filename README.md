# LLODE - LLM-Powered Code Editor

LLODE (Large Language Model Optimized Development Environment) is an AI-powered coding assistant that provides a chat-based interface for interacting with codebases. It leverages Mammouth.ai to perform file operations, search code, manage tasks, and assist with development workflows through natural language conversation.

## Features

### 🤖 AI-Powered Coding Assistant
- Interactive chat interface with all AIs from mammouth.ai (e.g. Sonnet, ChatGPT, …)
- Context-aware responses based on your entire codebase
- Automatic conversation history management with summarization

### 🔌 Plugin-Based Architecture
- **Extensible tool system**: Add new capabilities by dropping Python files in `tools/` directory
- **Six built-in plugins**: File operations, git integration, semantic code search, document conversion, task management, and web tools
- **Dynamic loading**: Plugins are discovered and loaded automatically at startup
- **Isolated functionality**: Each plugin is self-contained with its own tools and storage
- **Use `/plugins` command**: View loaded plugins and their status

### 🛠️ File Operations (via `file_operations` plugin)
- **List Files**: Recursively browse project directory structure
- **Read Files**: View file contents with optional line ranges and automatic gitignore respect
- **Edit Files**: AI can modify files with precise search-and-replace operations
- **Create Files**: Generate new files from scratch
- **Move/Rename Files**: Relocate or rename files with automatic directory creation
- **Delete Files**: Remove files safely with git tracking
- **Search & Replace**: Multi-file search and replace across your codebase

### 🔍 Semantic Code Search (via `codebase_index` plugin)
- **Symbol Search**: Find function and class definitions instantly
- **Reference Tracking**: See where symbols are used across the codebase
- **Dependency Analysis**: Understand import relationships between files
- **Symbol Listing**: Browse all functions/classes in files or by pattern
- **Fast Indexing**: SQLite-based index stored in `.llode/codebase_index.db`
- **Python Support**: Analyzes Python codebases (extensible to other languages)

### 🔄 Git Integration (via `git_operations` plugin)
- **Automatic Staging**: Files are automatically staged after modifications
- **Smart Commits**: AI creates meaningful commit messages (automatically prefixed with `[llode]`)
- **Diff Viewing**: Review staged and unstaged changes
- **Change Tracking**: All file operations are tracked in git history
- **Undo/Redo**: Revert commits using `/undo` command with git-native revert operations

### 📄 Document Conversion (via `document_conversion` plugin)
- **To Markdown**: Convert documents (DOCX, ODT, RTF, HTML, EPUB, PDF) to markdown
- **From Markdown**: Convert markdown back to various formats
- **Automatic Handling**: System suggests conversion when reading binary formats
- **Workflow**: Convert → Edit → Convert back (optional)

### 📋 Task Management (via `todo_manager` plugin)
- Built-in todo list system stored in `.llode/todo.json`
- Track progress on complex multi-step tasks
- Task status tracking (pending, in_progress, completed)
- Persistent storage across sessions

### 🌐 Web Integration (via `web_tools` plugin)
- Fetch content from URLs for context
- Integrate external documentation or resources
- Supports HTTP and HTTPS

### 💾 Smart History Management
- Automatic conversation summarization when approaching token limits
- Preserves context across long coding sessions
- Rolling history window to maintain recent interactions

## Installation

### Prerequisites
- Python 3.7 or higher
- API key (mammouth AI or others)
- **Pandoc** (optional, for document conversion support)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd llode
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your Anthropic API key:
```bash
export OPENAI_API_KEY='your-api-key-here'
```

Or create a `.env` file (not recommended for security):
```
OPENAI_API_KEY=your-api-key-here
```

4. **(Optional)** Install Pandoc for document conversion:
```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt-get install pandoc

# Windows
# Download from https://pandoc.org/installing.html
```

## Usage

### Basic Usage

Start LLODE in your project directory:
```bash
python llode.py
```

### Interactive Commands

Once started, you can interact with the AI assistant naturally:

```
You: Create a new Python file called utils.py with a function to calculate factorial
You: Search for all TODO comments in the codebase
You: Refactor the main.py file to use type hints
You: What files are in this project?
You: Read lines 50-100 from main.py
You: Replace all instances of 'old_function' with 'new_function' in *.py files
You: Move src/old.py to src/new.py
You: Show me the git diff of my changes
```

### Special Commands

- `/help` - Show available commands
- `/clear` - Clear conversation history
- `/model` - Change AI model
- `/plan` - Toggle planning mode (disables file editing for exploration)
- `/plugins` - Show loaded plugins and their status
- `/multiline` - Enter multiline input mode
- `/undo` - Revert a previous commit (shows recent llode commits)
- `/quit` - Exit the assistant

**Note**: You can also use `exit`, `quit`, or press `Ctrl+D` to quit

## How It Works

### Architecture Overview

LLODE combines a plugin-based architecture with Claude's tool-calling capabilities to provide an extensible AI coding assistant.

**Core Components:**
- **Main Loop** (`llode.py`): Chat interface, command handling, and plugin management
- **Tool Parser** (`tool_parser.py`): MIME-style boundary format parser for tool calls
- **API Client** (`api.py`): Claude API integration with streaming responses
- **Plugin System**: Dynamic plugin discovery and loading from `tools/` directory

**Plugin Architecture:**

1. **Discovery Phase**: At startup, scans `tools/` directory for Python modules
2. **Loading Phase**: Each plugin's `register_tools(registry, git_root)` function is called
3. **Registration**: Plugins register tools with descriptions via the `ToolRegistry`
4. **Integration**: Tool descriptions are injected into the system prompt for Claude
5. **Execution**: When Claude calls a tool, the registered function is invoked

**Built-in Plugins:**

1. **file_operations** - File system manipulation
   - `file_list`, `file_read`, `file_edit`, `file_move`, `file_delete`, `search_codebase`, `search_replace`

2. **codebase_index** - Semantic code analysis (Python)
   - `index_codebase`, `find_symbol`, `analyze_dependencies`, `list_symbols`

3. **git_operations** - Version control integration
   - `git_add`, `git_commit`, `git_diff`

4. **document_conversion** - Format conversion (requires Pandoc)
   - `convert_to_markdown`, `convert_from_markdown`

5. **todo_manager** - Task tracking
   - `todo_read`, `todo_write`

6. **web_tools** - Web content fetching
   - `fetch_url`

### Creating Custom Plugins

LLODE's plugin system makes it easy to add new functionality. Plugins are simply Python files placed in the `tools/` directory.

#### Quick Start

1. Create a new `.py` file in the `tools/` directory
2. Define a `register_tools(registry, git_root)` function
3. Use `@registry.register()` decorator to add tools
4. Restart LLODE to load the new plugin

#### Example Plugin

```python
"""
My custom tool - does something useful.
"""

def register_tools(registry, git_root):
    @registry.register("my_tool", """
    Description of what this tool does.
    
    Parameters:
    - param1: description of param1
    - param2: description of param2
    
    Returns information about what was done.
    """)
    def my_tool(param1: str, param2: str = "default"):
        # Your implementation here
        result = f"Processed {param1} with {param2}"
        return result
```

#### Plugin Features

- **Automatic Discovery**: Drop Python files in `tools/` directory, no registration needed
- **Core Utilities**: Access `validate_path()`, `get_gitignore_spec()`, `walk_files()`, `is_dotfile()`
- **Project Context**: Receive `git_root` parameter to work within project boundaries
- **Error Isolation**: Plugin failures don't crash LLODE
- **Status Reporting**: Use `/plugins` command to see loaded plugins and any errors

#### Plugin Requirements

- Must define `register_tools(registry, git_root)` function
- Should include module docstring (shown in `/plugins` command)
- Tool functions must return strings (for LLM to read)
- Use `validate_path()` to check file paths are within project
- Handle errors gracefully with try/except blocks

#### Plugin Storage

Plugins can store persistent data in the `.llode/` directory:
```python
import os
import json

def register_tools(registry, git_root):
    storage_dir = os.path.join(git_root, ".llode")
    os.makedirs(storage_dir, exist_ok=True)
    
    db_path = os.path.join(storage_dir, "my_plugin.db")
    # Use db_path for SQLite or other storage
```

Examples:
- `.llode/codebase_index.db` - SQLite database for code indexing
- `.llode/todo.json` - JSON file for task management
- `.llode/my_plugin/` - Directory for file-based storage

The `.llode/` directory is automatically created and is git-ignored by default.

### Token Budget Management

- TO CHECK: Maximum token budget: 200,000 tokens
- Automatic summarization when approaching limits
- TO CHECK: Preserves last 5 messages for immediate context
- Generates concise summaries of older conversation history

## Configuration

### Gitignore Integration

LLODE automatically respects your `.gitignore` patterns and excludes:
- Files matching `.gitignore` patterns
- Dotfiles (files starting with `.`)
- Common directories: `node_modules`, `.git`, `__pycache__`, etc.

## Advanced Features

### Todo List System

The AI proactively uses the todo list for:
- Complex multi-step tasks
- Progress tracking across conversations
- Systematic organization of work

Example todo structure:
```json
[
  {
    "task": "Implement user authentication",
    "status": "in_progress",
    "priority": "high"
  },
  {
    "task": "Add unit tests for auth module",
    "status": "pending",
    "priority": "medium"
  }
]
```

### Git Undo/Redo System

LLODE provides a safe, git-native undo system:

**Using /undo**:
1. Type `/undo` to see recent llode commits
2. Select a commit by number or hash
3. LLODE creates a git revert commit (safe for multi-user repos)
4. The LLM is automatically notified of the revert

**Redoing Changes**:
- Simply use `/undo` again on the revert commit
- This reverts the revert, effectively redoing the original change

**Benefits**:
- ✅ Safe for collaborative repositories (uses `git revert`, not `git reset`)
- ✅ Preserves full git history
- ✅ LLM maintains awareness of all changes and reverts
- ✅ Multiple undo/redo operations supported
- ✅ Handles merge conflicts gracefully

Example:
```
You: /undo

Recent commits:
  1. 7ce8580a [llode] Implement /undo command (1 minute ago)
  2. 7f56fd2e [llode] Add user authentication (5 minutes ago)
  3. abc1234 [llode] Refactor login module (1 hour ago)

Enter number or hash to revert: 2

✓ Reverted: 7f56fd2e [llode] Add user authentication
LLM has been notified of the revert
```

### Context-Aware Editing

The AI assistant can:
- Understand your project structure
- Make consistent changes across multiple files
- Follow coding patterns in your codebase
- Suggest improvements based on best practices

### Document Conversion Workflow

Working with documents (requires Pandoc):

1. **Convert to Markdown**: The AI will automatically suggest conversion when you try to read binary document formats
   ```
   You: Read the report.docx file
   AI: [Suggests using convert_to_markdown]
   AI: [Converts report.docx → report.docx.md]
   ```

2. **Edit the Markdown**: Work with the markdown version using standard editing tools
   ```
   You: Update the introduction section in the report
   AI: [Edits report.docx.md]
   ```

3. **Convert Back** (optional): Convert the markdown back to the original format
   ```
   You: Convert the markdown back to docx
   AI: [Converts report.docx.md → report.docx]
   ```

**Supported Formats**:
- Input: docx, odt, rtf, html, epub, pdf, and more
- Output: docx, odt, rtf, html, epub, pdf, rst, latex, tex

## Security Considerations

- **API Key**: Store your Anthropic API key securely using environment variables
- **File Access**: LLODE can read and modify files in the current directory
- **Dotfiles**: Automatically excluded to protect sensitive configuration
- **Gitignore**: Respects `.gitignore` to avoid accessing sensitive files

## Limitations

- Requires active internet connection for Claude API
- Token budget limits conversation length (automatically managed)
- File edits require exact string matching
- Cannot execute code directly (file operations only)
- Document conversion requires Pandoc to be installed (optional feature)
- Binary files cannot be directly edited (must be converted to markdown first)

## Contributing

Not yet.

## License

Not yet.

## Acknowledgments

- Built with [Anthropic's Claude AI](https://www.anthropic.com/)
- Uses the Claude 3.7 Sonnet model for optimal coding assistance

## Support

For issues, questions, or contributions, please [open an issue](link-to-issues) on GitHub.

---

**Note**: LLODE is a powerful tool that can modify your codebase. Always use version control (git) and review changes before committing.
```
