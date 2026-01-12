# LLODE - LLM-Powered Code Editor

LLODE (Large Language Model Optimized Development Environment) is an AI-powered coding assistant that provides a chat-based interface for interacting with codebases. It leverages Mammouth.ai to perform file operations, search code, manage tasks, and assist with development workflows through natural language conversation.

## Features

### 🤖 AI-Powered Coding Assistant
- Interactive chat interface with all AIs from mammouth.ai (e.g. Sonnet, chatgpt, …)
- Context-aware responses based on your entire codebase
- Automatic conversation history management with summarization

### 🛠️ File Operations
- **List Files**: Recursively browse project directory structure
- **Read Files**: View file contents with automatic gitignore respect
- **Edit Files**: AI can modify files with precise search-and-replace operations
- **Create Files**: Generate new files from scratch
- **Document Conversion**: Convert between document formats (docx, odt, rtf, html, epub, pdf) and markdown using Pandoc

### 🔍 Code Search
- Full-text search across your entire codebase
- Case-sensitive and case-insensitive search options
- Respects `.gitignore` patterns
- Excludes dotfiles automatically
- Stays in the project directory

### 📋 Task Management
- Built-in todo list system (`LLODE_TODO.json`)
- Track progress on complex multi-step tasks
- Priority-based task organization
- Persistent task storage across sessions

### 🌐 Web Integration
- Fetch content from URLs for context
- Integrate external documentation or resources

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
```

### Special Commands

- **Exit**: Type `exit`, `quit`, or press `Ctrl+D` to quit
- **Clear History**: The assistant automatically manages conversation history

## How It Works

### Architecture

LLODE uses Claude's tool-calling capabilities to provide the AI assistant with access to:

1. **File System Tools**
   - `list_files`: Browse project structure
   - `read_file`: Read file contents (with binary format detection)
   - `edit_file`: Modify files with exact string matching

2. **Document Conversion Tools** (requires Pandoc)
   - `convert_to_markdown`: Convert documents (docx, odt, rtf, html, epub, pdf) to markdown
   - `convert_from_markdown`: Convert markdown back to various formats

3. **Search Tools**
   - `search_codebase`: Full-text search with context

4. **Web Tools**
   - `fetch_url`: Retrieve content from URLs

5. **Task Management Tools**
   - `todo_read`: View current task list
   - `todo_write`: Update task list

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
