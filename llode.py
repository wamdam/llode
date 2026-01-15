#!/usr/bin/env python3
"""
LLM CLI Coding Assistant
A terminal-based coding assistant with file manipulation tools.
"""

import os
import sys
import re
import json
import argparse
import readline
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Callable, Optional, Tuple
from dotenv import load_dotenv
import requests
from difflib import unified_diff
import pathspec
from rich.console import Console
from rich.markdown import Markdown, Heading
from rich.live import Live
from rich.text import Text
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.history import FileHistory

# Load environment variables
load_dotenv()

# Configuration
DEFAULT_BASE_URL = "https://api.mammouth.ai/v1"
DEFAULT_MODEL = "claude-sonnet-4-5"
MAX_CONTEXT_TOKENS = 150000


# Custom Markdown class with left-aligned headings
class LeftAlignedMarkdown(Markdown):
    """Markdown renderer with left-aligned headings instead of centered."""
    
    elements = {
        **Markdown.elements,
    }
    
    # Override heading element to use left alignment
    elements["heading"] = Heading
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Modify heading styles to be left-aligned
        for element in self.elements.values():
            if hasattr(element, 'style_name') and 'heading' in str(element):
                element.justify = "left"


def find_git_root() -> Path:
    """Find the git root directory, starting from current directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


class ToolRegistry:
    """Registry for tool functions."""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.descriptions: Dict[str, str] = {}
    
    def register(self, name: str, description: str):
        """Decorator to register a tool function."""
        def decorator(func: Callable) -> Callable:
            self.tools[name] = func
            self.descriptions[name] = description
            return func
        return decorator
    
    def get_tools_description(self) -> str:
        """Get formatted description of all tools."""
        lines = ["Available tools:\n"]
        for name, desc in self.descriptions.items():
            lines.append(f"## {name}\n{desc}\n")
        return "\n".join(lines)
    
    def get_system_prompt(self, planning_mode: bool = False) -> str:
        """Generate system prompt with tool descriptions."""
        tools_desc = self.get_tools_description()
        
        planning_prefix = ""
        if planning_mode:
            planning_prefix = """⚠️ PLANNING MODE ACTIVE ⚠️

All file-modifying tools are DISABLED (file_edit, file_move, file_delete, search_replace, git_add, git_commit).
Focus on planning, analysis, and read-only operations.

"""
        
        # Check for custom local prompt
        local_prompt = ""
        local_prompt_path = GIT_ROOT / "llode_prompt.txt"
        if local_prompt_path.exists():
            try:
                local_prompt_content = local_prompt_path.read_text(encoding='utf-8').strip()
                if local_prompt_content:
                    local_prompt = f"""
PROJECT-SPECIFIC INSTRUCTIONS:

{local_prompt_content}

"""
            except Exception as e:
                # If we can't read the file, just skip it silently
                pass
        
        git_workflow = """
GIT WORKFLOW - MANDATORY:

After ANY successful file modification (file_edit, file_move, file_delete, search_replace):
1. Use git_add to stage the changed files
2. Use git_commit with a descriptive message

Example workflow:
- file_edit() → git_add() → git_commit()
- file_move() → git_add() → git_commit()
- search_replace() → git_add() → git_commit()

This ensures all changes are tracked and can be reverted if needed.

"""
        
        document_workflow = """
DOCUMENT CONVERSION WORKFLOW:

For non-plaintext documents (docx, odt, rtf, html, epub, pdf):
1. Use convert_to_markdown(path="document.docx") to create document.docx.md
2. Use file_read or file_edit on the .md version
3. Optionally use convert_from_markdown to convert back to original format

The system will automatically suggest conversion when you try to read binary files.

"""

        return f"""{planning_prefix}You are a coding assistant with access to file manipulation tools.

{local_prompt}{git_workflow}{document_workflow}IMPORTANT: Use tools with this EXACT MIME-style boundary format:

TOOL CALL FORMAT:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: [unique-id]

--[unique-id]
Content-Disposition: param; name="tool_name"

[tool_name_here]
--[unique-id]
Content-Disposition: param; name="param1"

[value1]
--[unique-id]
Content-Disposition: param; name="param2"

[value2]
--[unique-id]--
--TOOL_CALL_END

RULES:
1. Each tool call starts with --TOOL_CALL_BEGIN and ends with --TOOL_CALL_END
2. Generate a unique Boundary-ID (8+ alphanumeric chars) for each tool call
3. Parameter values preserve EXACT whitespace - no escaping needed
4. The boundary ID must NOT appear in any parameter value
5. If your content contains the boundary string, use a different boundary ID
6. For editing: old_str must match EXACTLY (every space, tab, newline)
7. For creating/overwriting: omit the old_str parameter entirely
8. All file paths are relative to the project root
9. Do not access dotfiles

NESTING: If you need to show example tool calls in your content, use a DIFFERENT
boundary ID than the outer tool call. The parser handles nesting automatically.

EXAMPLE - Reading a file:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: abc123

--abc123
Content-Disposition: param; name="tool_name"

file_read
--abc123
Content-Disposition: param; name="path"

src/main.py
--abc123--
--TOOL_CALL_END

EXAMPLE - Reading specific lines from a file:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: abc124

--abc124
Content-Disposition: param; name="tool_name"

file_read
--abc124
Content-Disposition: param; name="path"

src/main.py
--abc124
Content-Disposition: param; name="start_line"

10
--abc124
Content-Disposition: param; name="end_line"

50
--abc124--
--TOOL_CALL_END

EXAMPLE - Reading from a starting line to end of file:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: abc125

--abc125
Content-Disposition: param; name="tool_name"

file_read
--abc125
Content-Disposition: param; name="path"

src/main.py
--abc125
Content-Disposition: param; name="start_line"

100
--abc125--
--TOOL_CALL_END

EXAMPLE - Editing a file:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: xyz789

--xyz789
Content-Disposition: param; name="tool_name"

file_edit
--xyz789
Content-Disposition: param; name="path"

config.py
--xyz789
Content-Disposition: param; name="old_str"

def hello():
    print("Hello")
--xyz789
Content-Disposition: param; name="new_str"

def hello(name="World"):
    print(f"Hello, {{name}}!")
--xyz789--
--TOOL_CALL_END

EXAMPLE - Creating/overwriting a file (omit old_str parameter):
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: new456

--new456
Content-Disposition: param; name="tool_name"

file_edit
--new456
Content-Disposition: param; name="path"

new_file.py
--new456
Content-Disposition: param; name="new_str"

#!/usr/bin/env python3
print("New file!")
--new456--
--TOOL_CALL_END

EXAMPLE - Tool with no parameters:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: list99

--list99
Content-Disposition: param; name="tool_name"

file_list
--list99--
--TOOL_CALL_END

EXAMPLE - Git workflow (stage and commit):
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: git001

--git001
Content-Disposition: param; name="tool_name"

git_add
--git001
Content-Disposition: param; name="paths"

src/main.py, src/config.py
--git001--
--TOOL_CALL_END

--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: git002

--git002
Content-Disposition: param; name="tool_name"

git_commit
--git002
Content-Disposition: param; name="message"

Add user authentication feature
--git002--
--TOOL_CALL_END

EXAMPLE - Moving a file:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: move01

--move01
Content-Disposition: param; name="tool_name"

file_move
--move01
Content-Disposition: param; name="source"

old_location/file.py
--move01
Content-Disposition: param; name="destination"

new_location/file.py
--move01--
--TOOL_CALL_END

EXAMPLE - Multi-file search and replace:
--TOOL_CALL_BEGIN
Content-Type: tool-call
Boundary-ID: search01

--search01
Content-Disposition: param; name="tool_name"

search_replace
--search01
Content-Disposition: param; name="search_term"

old_function_name
--search01
Content-Disposition: param; name="replace_term"

new_function_name
--search01
Content-Disposition: param; name="file_pattern"

*.py
--search01--
--TOOL_CALL_END

VERIFICATION CHECKLIST before sending tool call:
* Starts with --TOOL_CALL_BEGIN
* Has Content-Type: tool-call header
* Has Boundary-ID: [id] header
* Each param has --[id] before and Content-Disposition header
* Ends with --[id]-- then --TOOL_CALL_END
* Boundary ID doesn't appear in any parameter values
* For edits: old_str matches file content EXACTLY (whitespace matters!)
* For new files: omit old_str parameter entirely to create/overwrite

{tools_desc}
"""


# Initialize tool registry and git root
tools = ToolRegistry()
GIT_ROOT = find_git_root()
LOG_FILE = GIT_ROOT / "llode_log.md"


def log_conversation(role: str, content: str) -> None:
    """Log a conversation message to llode_log.md"""
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n---\n\n")
        f.write(f"**{role.upper()}** ({timestamp})\n\n")
        f.write(f"{content}\n")


def log_session_start() -> None:
    """Log the start of a new session"""
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n{'='*80}\n")
        f.write(f"# NEW SESSION - {timestamp}\n")
        f.write(f"{'='*80}\n")


def check_pandoc_installed() -> bool:
    """Check if pandoc is installed and available in PATH."""
    return shutil.which("pandoc") is not None


def is_dotfile(path: Path) -> bool:
    """Check if path or any of its parents is a dotfile."""
    for part in path.parts:
        if part.startswith('.') and part not in ['.', '..']:
            return True
    return False


def get_gitignore_spec() -> Optional[pathspec.PathSpec]:
    """Load .gitignore patterns if it exists."""
    gitignore_path = GIT_ROOT / ".gitignore"
    if gitignore_path.exists():
        with open(gitignore_path, 'r') as f:
            patterns = f.read().splitlines()
        return pathspec.PathSpec.from_lines('gitwildmatch', patterns)
    return None


def is_ignored(path: Path, gitignore_spec: Optional[pathspec.PathSpec]) -> bool:
    """Check if path should be ignored."""
    if gitignore_spec is None:
        return False
    try:
        rel_path = path.relative_to(GIT_ROOT)
        return gitignore_spec.match_file(str(rel_path))
    except ValueError:
        return False


def validate_path(path: str) -> Path:
    """Validate and resolve a path relative to GIT_ROOT."""
    clean_path = Path(path).as_posix()
    if clean_path.startswith('/'):
        clean_path = clean_path[1:]
    
    full_path = (GIT_ROOT / clean_path).resolve()
    
    if not str(full_path).startswith(str(GIT_ROOT)):
        raise ValueError(f"Path escapes project root: {path}")
    
    rel_path = full_path.relative_to(GIT_ROOT)
    if is_dotfile(rel_path):
        raise ValueError(f"Access to dotfiles is not allowed: {path}")
    
    return full_path


def walk_files(gitignore_spec: Optional[pathspec.PathSpec]) -> List[Path]:
    """Walk directory tree and yield valid file paths."""
    files = []
    for root, dirs, filenames in os.walk(GIT_ROOT):
        root_path = Path(root)
        
        dirs[:] = [d for d in dirs 
                   if not is_dotfile(root_path.relative_to(GIT_ROOT) / d) 
                   and not is_ignored(root_path / d, gitignore_spec)]
        
        for filename in filenames:
            file_path = root_path / filename
            rel_path = file_path.relative_to(GIT_ROOT)
            if not is_dotfile(rel_path) and not is_ignored(file_path, gitignore_spec):
                files.append(rel_path)
    
    return sorted(files)


@tools.register("file_list", """Lists all files in the project directory recursively.

Returns a list of all files, excluding those in .gitignore and dotfiles.""")
def file_list() -> str:
    """List all files in the git root directory, respecting .gitignore."""
    files = walk_files(get_gitignore_spec())
    return "\n".join(str(f) for f in files) if files else "(no files found)"


@tools.register("file_read", """Reads the contents of a file.

Parameters:
- path: relative path to the file
- start_line: optional starting line number (1-indexed, inclusive)
- end_line: optional ending line number (1-indexed, inclusive)

Returns the file contents or specified line range.""")
def file_read(path: str, start_line: str = None, end_line: str = None) -> str:
    """Read the contents of a file, optionally within a line range."""
    file_path = validate_path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Check if this is a binary document format
    binary_extensions = ['.docx', '.odt', '.rtf', '.doc', '.epub', '.pdf']
    if file_path.suffix.lower() in binary_extensions:
        return (
            f"⚠️  Cannot read binary document format: {file_path.suffix}\n\n"
            f"This appears to be a {file_path.suffix.upper()} file. "
            f"Use convert_to_markdown tool first:\n\n"
            f"  convert_to_markdown(path=\"{path}\")\n\n"
            f"This will create a markdown version that you can read and edit."
        )
    
    try:
        content = file_path.read_text()
        
        # If no line range specified, return full content
        if start_line is None and end_line is None:
            return content
        
        # Parse line numbers
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        
        # Convert to integers and validate
        start = int(start_line) if start_line is not None else 1
        end = int(end_line) if end_line is not None else total_lines
        
        if start < 1:
            raise ValueError(f"start_line must be >= 1, got {start}")
        if end < start:
            raise ValueError(f"end_line ({end}) must be >= start_line ({start})")
        if start > total_lines:
            raise ValueError(f"start_line ({start}) exceeds file length ({total_lines} lines)")
        
        # Adjust end if it exceeds file length
        end = min(end, total_lines)
        
        # Extract the requested lines (convert to 0-indexed)
        selected_lines = lines[start - 1:end]
        result = ''.join(selected_lines)
        
        # Add context information
        if start_line is not None or end_line is not None:
            header = f"Lines {start}-{end} of {total_lines}:\n"
            return header + result
        
        return result
        
    except UnicodeDecodeError:
        return (
            f"⚠️  Cannot read file as text: {path}\n\n"
            f"This file appears to be binary or uses an unsupported encoding.\n"
            f"If this is a document file, try using convert_to_markdown."
        )
    except ValueError as e:
        raise ValueError(f"Invalid line range: {str(e)}")


@tools.register("file_edit", """Edits a file by replacing old_str with new_str, OR creates/overwrites a file.

Parameters:
- path: relative path to the file (required)
- new_str: replacement string or new file content (required)
- old_str: exact string to replace (optional)

BEHAVIOR:
- If old_str is NOT provided: Creates a new file or OVERWRITES existing file with new_str
- If old_str is provided: Searches for exact match and replaces with new_str

The old_str must match EXACTLY including all whitespace and newlines when provided.""")
def file_edit(path: str, new_str: str, old_str: str = None) -> str:
    """Edit a file by replacing old_str with new_str, or create/overwrite if old_str not provided."""
    file_path = validate_path(path)
    
    # Create/overwrite file if old_str is not provided
    if old_str is None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(new_str)
        action = "Overwrote" if file_path.exists() else "Created"
        return f"{action} file: {path}\n{len(new_str)} bytes written"
    
    # Edit existing file if old_str is provided
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}. Omit old_str parameter to create new file.")
    
    content = file_path.read_text()
    if old_str not in content:
        raise ValueError(
            f"old_str not found in file: {path}\n"
            f"Looking for ({len(old_str)} chars): {repr(old_str[:200])}\n"
            f"Tip: Ensure exact match including all spaces, tabs, and newlines"
        )
    
    new_content = content.replace(old_str, new_str, 1)
    file_path.write_text(new_content)
    
    diff = unified_diff(
        content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"{path} (old)",
        tofile=f"{path} (new)",
        lineterm=''
    )
    return "".join(diff) or "File updated (no diff to display)"


@tools.register("fetch_url", """Fetches content from a URL.

Parameters:
- url: The URL to fetch (must start with http:// or https://)

Returns the content from the URL. Supports HTTP and HTTPS.""")
def fetch_url(url: str) -> str:
    """Fetch content from a URL."""
    try:
        if not url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LLM-CLI-Assistant/1.0)'
        })
        response.raise_for_status()
        
        content_type = response.headers.get('content-type', '').lower()
        
        if 'application/json' in content_type:
            return response.text
        elif 'text/' in content_type or 'application/xml' in content_type:
            return response.text
        else:
            return f"Content-Type: {content_type}\nContent-Length: {len(response.content)} bytes\n\n(Binary or non-text content - first 500 chars):\n{response.text[:500]}"
        
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Request timed out after 30 seconds: {url}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to fetch URL: {str(e)}")


@tools.register("search_codebase", """Searches for a string in the codebase.

Parameters:
- search_term: The string to search for (required)
- case_sensitive: Whether to match case (default: false)

Returns matching lines with file paths and line numbers.""")
def search_codebase(search_term: str, case_sensitive: str = "false") -> str:
    """Search for a string in all files."""
    case_sensitive_bool = case_sensitive.lower() == "true"
    gitignore_spec = get_gitignore_spec()
    files = walk_files(gitignore_spec)
    
    results = []
    search_pattern = search_term if case_sensitive_bool else search_term.lower()
    
    for file_path in files:
        try:
            full_path = GIT_ROOT / file_path
            content = full_path.read_text()
            lines = content.splitlines()
            
            for line_num, line in enumerate(lines, 1):
                compare_line = line if case_sensitive_bool else line.lower()
                if search_pattern in compare_line:
                    results.append(f"{file_path}:{line_num}: {line.strip()}")
        except (UnicodeDecodeError, PermissionError):
            continue
    
    return "\n".join(results) if results else f"No matches found for: {search_term}"


@tools.register("todo_read", """Reads the current todo list from llode_todo.json.

Returns the current todo list or empty structure if none exists.""")
def todo_read() -> str:
    """Read the todo list."""
    todo_path = GIT_ROOT / "llode_todo.json"
    if todo_path.exists():
        return todo_path.read_text()
    return json.dumps({"tasks": []}, indent=2)


@tools.register("todo_write", """Writes/updates the todo list to llode_todo.json.

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
    (GIT_ROOT / "llode_todo.json").write_text(content)
    return "Todo list updated successfully"


@tools.register("convert_to_markdown", """Converts a document to markdown format using pandoc or pdftotext.

Parameters:
- path: relative path to the document file

Converts documents to markdown:
- PDF files: Uses pdftotext (from poppler-utils) to extract text
- Other formats (docx, odt, rtf, html, epub, etc.): Uses pandoc

Creates a new file with .md extension (e.g., document.pdf -> document.pdf.md).
Returns the path to the generated markdown file.

Requires pandoc for non-PDF files, and pdftotext for PDF files.""")
def convert_to_markdown(path: str) -> str:
    """Convert a document to markdown using pandoc or pdftotext."""
    file_path = validate_path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Generate output path (keep the same naming convention: file.pdf -> file.pdf.md)
    output_path = file_path.parent / f"{file_path.name}.md"
    
    # Check if output already exists
    if output_path.exists():
        return (
            f"⚠️  Markdown file already exists: {output_path.relative_to(GIT_ROOT)}\n"
            f"Use file_read to view it, or delete it first if you want to reconvert."
        )
    
    # Check if this is a PDF file
    if file_path.suffix.lower() == '.pdf':
        # Use pdftotext for PDF files
        if not shutil.which("pdftotext"):
            return (
                "❌ Error: pdftotext is not installed.\n\n"
                "To install pdftotext:\n"
                "  - macOS: brew install poppler\n"
                "  - Ubuntu/Debian: sudo apt-get install poppler-utils\n"
                "  - Windows: Download poppler from https://blog.alivate.com.au/poppler-windows/\n"
                "  - Other: See https://poppler.freedesktop.org/"
            )
        
        try:
            # pdftotext converts to plain text, saved with .md extension
            # Using -layout option to preserve text layout better
            result = subprocess.run(
                ["pdftotext", "-layout", str(file_path), str(output_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error"
                return f"❌ pdftotext conversion failed:\n{error_msg}"
            
            # Get size info
            original_size = file_path.stat().st_size
            markdown_size = output_path.stat().st_size
            
            rel_output = output_path.relative_to(GIT_ROOT)
            return (
                f"✓ Successfully converted PDF to markdown:\n"
                f"  Input:  {path} ({original_size:,} bytes)\n"
                f"  Output: {rel_output} ({markdown_size:,} bytes)\n\n"
                f"You can now use file_read or file_edit on: {rel_output}"
            )
            
        except subprocess.TimeoutExpired:
            return "❌ Error: pdftotext conversion timed out after 30 seconds"
        except Exception as e:
            return f"❌ Error during PDF conversion: {str(e)}"
    
    else:
        # Use pandoc for other document formats
        if not check_pandoc_installed():
            return (
                "❌ Error: pandoc is not installed.\n\n"
                "To install pandoc:\n"
                "  - macOS: brew install pandoc\n"
                "  - Ubuntu/Debian: sudo apt-get install pandoc\n"
                "  - Windows: Download from https://pandoc.org/installing.html\n"
                "  - Other: See https://pandoc.org/installing.html"
            )
        
        try:
            # Run pandoc conversion
            result = subprocess.run(
                ["pandoc", str(file_path), "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or "Unknown error"
                return f"❌ Pandoc conversion failed:\n{error_msg}"
            
            # Get size info
            original_size = file_path.stat().st_size
            markdown_size = output_path.stat().st_size
            
            rel_output = output_path.relative_to(GIT_ROOT)
            return (
                f"✓ Successfully converted to markdown:\n"
                f"  Input:  {path} ({original_size:,} bytes)\n"
                f"  Output: {rel_output} ({markdown_size:,} bytes)\n\n"
                f"You can now use file_read or file_edit on: {rel_output}"
            )
            
        except subprocess.TimeoutExpired:
            return "❌ Error: Pandoc conversion timed out after 30 seconds"
        except Exception as e:
            return f"❌ Error during conversion: {str(e)}"


@tools.register("convert_from_markdown", """Converts a markdown file back to another format using pandoc.

Parameters:
- path: relative path to the markdown file
- output_format: target format (docx, odt, rtf, html, epub, pdf, etc.)

Converts the markdown file to the specified format.
Creates output file by replacing .md extension with target format extension.
Returns the path to the generated file.

Requires pandoc to be installed.""")
def convert_from_markdown(path: str, output_format: str) -> str:
    """Convert a markdown file to another format using pandoc."""
    if not check_pandoc_installed():
        return (
            "❌ Error: pandoc is not installed.\n\n"
            "To install pandoc:\n"
            "  - macOS: brew install pandoc\n"
            "  - Ubuntu/Debian: sudo apt-get install pandoc\n"
            "  - Windows: Download from https://pandoc.org/installing.html\n"
            "  - Other: See https://pandoc.org/installing.html"
        )
    
    file_path = validate_path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    # Validate format
    valid_formats = ['docx', 'odt', 'rtf', 'html', 'epub', 'pdf', 'rst', 'latex', 'tex']
    if output_format.lower() not in valid_formats:
        return f"❌ Unsupported format: {output_format}\nSupported: {', '.join(valid_formats)}"
    
    # Generate output path
    # If path ends with .docx.md, output should be .docx
    # Otherwise, replace .md with the target extension
    if file_path.suffix == '.md':
        stem = file_path.stem
        # Check if stem ends with a document extension
        for ext in ['.docx', '.odt', '.rtf', '.html', '.epub']:
            if stem.endswith(ext):
                output_path = file_path.parent / stem
                break
        else:
            output_path = file_path.parent / f"{stem}.{output_format.lower()}"
    else:
        return f"❌ Input file must be a markdown file (.md): {path}"
    
    try:
        # Run pandoc conversion
        result = subprocess.run(
            ["pandoc", str(file_path), "-o", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            return f"❌ Pandoc conversion failed:\n{error_msg}"
        
        # Get size info
        markdown_size = file_path.stat().st_size
        output_size = output_path.stat().st_size
        
        rel_output = output_path.relative_to(GIT_ROOT)
        return (
            f"✓ Successfully converted from markdown:\n"
            f"  Input:  {path} ({markdown_size:,} bytes)\n"
            f"  Output: {rel_output} ({output_size:,} bytes)\n"
        )
        
    except subprocess.TimeoutExpired:
        return "❌ Error: Pandoc conversion timed out after 30 seconds"
    except Exception as e:
        return f"❌ Error during conversion: {str(e)}"


@tools.register("git_add", """Adds files to git staging area.

Parameters:
- paths: file paths to add (can be a single path or multiple comma-separated paths)

Adds the specified files to git staging area, ready for commit.""")
def git_add(paths: str) -> str:
    """Add files to git staging area."""
    # Parse paths (can be comma-separated)
    path_list = [p.strip() for p in paths.split(',')]
    
    # Validate all paths first
    validated_paths = []
    for path in path_list:
        try:
            file_path = validate_path(path)
            validated_paths.append(str(file_path.relative_to(GIT_ROOT)))
        except Exception as e:
            return f"❌ Invalid path '{path}': {str(e)}"
    
    try:
        # Run git add
        result = subprocess.run(
            ["git", "add"] + validated_paths,
            cwd=str(GIT_ROOT),
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            return f"❌ Git add failed:\n{error_msg}"
        
        # Show what was added
        files_str = "\n  ".join(validated_paths)
        return f"✓ Added to staging area:\n  {files_str}"
        
    except subprocess.TimeoutExpired:
        return "❌ Error: Git add timed out after 10 seconds"
    except FileNotFoundError:
        return "❌ Error: git command not found. Is git installed?"
    except Exception as e:
        return f"❌ Error during git add: {str(e)}"


@tools.register("git_commit", """Creates a git commit with staged changes.

Parameters:
- message: commit message (required)

Creates a git commit with the currently staged files.
All commits are automatically prefixed with [llode] for tracking.
Returns the commit hash and summary.""")
def git_commit(message: str) -> str:
    """Create a git commit with staged changes."""
    if not message or not message.strip():
        return "❌ Commit message cannot be empty"
    
    # Prefix message with [llode] if not already present
    if not message.startswith("[llode]"):
        message = f"[llode] {message}"
    
    try:
        # Run git commit
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(GIT_ROOT),
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            # Check for common issues
            if "nothing to commit" in error_msg.lower():
                return "❌ Nothing to commit. Use git_add to stage files first."
            return f"❌ Git commit failed:\n{error_msg}"
        
        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(GIT_ROOT),
            capture_output=True,
            text=True,
            timeout=5
        )
        
        commit_hash = hash_result.stdout.strip()[:8] if hash_result.returncode == 0 else "unknown"
        
        return f"✓ Commit created successfully\n  Hash: {commit_hash}\n  Message: {message}"
        
    except subprocess.TimeoutExpired:
        return "❌ Error: Git commit timed out"
    except FileNotFoundError:
        return "❌ Error: git command not found. Is git installed?"
    except Exception as e:
        return f"❌ Error during git commit: {str(e)}"


@tools.register("git_diff", """Shows git diff of changes.

Parameters:
- staged: whether to show staged changes only (default: false)
- file_path: optional specific file to diff (relative path)

Shows the git diff output. If staged=true, shows diff of staged changes (--cached).
If staged=false, shows diff of unstaged changes.
Optionally filter to a specific file path.""")
def git_diff(staged: str = "false", file_path: str = None) -> str:
    """Show git diff of changes."""
    try:
        # Build git diff command
        cmd = ["git", "diff"]
        
        # Add --cached flag if showing staged changes
        if staged.lower() == "true":
            cmd.append("--cached")
        
        # Add specific file path if provided
        if file_path:
            try:
                validated_path = validate_path(file_path)
                rel_path = str(validated_path.relative_to(GIT_ROOT))
                cmd.append("--")
                cmd.append(rel_path)
            except Exception as e:
                return f"❌ Invalid file path: {str(e)}"
        
        # Run git diff
        result = subprocess.run(
            cmd,
            cwd=str(GIT_ROOT),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            error_msg = result.stderr or "Unknown error"
            return f"❌ Git diff failed:\n{error_msg}"
        
        output = result.stdout.strip()
        
        if not output:
            if staged.lower() == "true":
                return "No staged changes to show"
            else:
                return "No unstaged changes to show"
        
        return output
        
    except subprocess.TimeoutExpired:
        return "❌ Error: Git diff timed out after 30 seconds"
    except FileNotFoundError:
        return "❌ Error: git command not found. Is git installed?"
    except Exception as e:
        return f"❌ Error during git diff: {str(e)}"


@tools.register("file_move", """Moves or renames a file.

Parameters:
- source: source file path
- destination: destination file path

Moves/renames a file from source to destination.
Creates parent directories if needed.""")
def file_move(source: str, destination: str) -> str:
    """Move or rename a file."""
    try:
        source_path = validate_path(source)
        dest_path = validate_path(destination)
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")
        
        if dest_path.exists():
            return f"❌ Destination already exists: {destination}"
        
        # Create parent directory if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        source_path.rename(dest_path)
        
        return f"✓ Moved: {source} → {destination}"
        
    except Exception as e:
        return f"❌ Error moving file: {str(e)}"


@tools.register("file_delete", """Deletes a file.

Parameters:
- path: file path to delete

Deletes the specified file. Use with caution!""")
def file_delete(path: str) -> str:
    """Delete a file."""
    try:
        file_path = validate_path(path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        if file_path.is_dir():
            return f"❌ Cannot delete directory with file_delete: {path}"
        
        # Delete the file
        file_path.unlink()
        
        return f"✓ Deleted: {path}"
        
    except Exception as e:
        return f"❌ Error deleting file: {str(e)}"


@tools.register("search_replace", """Search and replace text across multiple files.

Parameters:
- search_term: text to search for (required)
- replace_term: text to replace with (required)
- file_pattern: file pattern to match (optional, e.g., "*.py" or "src/*.js")
- case_sensitive: whether to match case (default: true)

Searches for text across files and replaces all occurrences.
Returns summary of changes made.""")
def search_replace(search_term: str, replace_term: str, file_pattern: str = "*", case_sensitive: str = "true") -> str:
    """Search and replace text across multiple files."""
    if not search_term:
        return "❌ search_term cannot be empty"
    
    case_sensitive_bool = case_sensitive.lower() == "true"
    gitignore_spec = get_gitignore_spec()
    all_files = walk_files(gitignore_spec)
    
    # Filter files by pattern
    from fnmatch import fnmatch
    if file_pattern and file_pattern != "*":
        matching_files = [f for f in all_files if fnmatch(str(f), file_pattern)]
    else:
        matching_files = all_files
    
    if not matching_files:
        return f"❌ No files match pattern: {file_pattern}"
    
    # Perform search and replace
    modified_files = []
    total_replacements = 0
    
    for file_path in matching_files:
        try:
            full_path = GIT_ROOT / file_path
            content = full_path.read_text()
            
            # Perform replacement
            if case_sensitive_bool:
                new_content = content.replace(search_term, replace_term)
            else:
                # Case-insensitive replacement
                import re
                pattern = re.compile(re.escape(search_term), re.IGNORECASE)
                new_content = pattern.sub(replace_term, content)
            
            # Check if content changed
            if new_content != content:
                replacements = content.count(search_term) if case_sensitive_bool else len(re.findall(re.escape(search_term), content, re.IGNORECASE))
                full_path.write_text(new_content)
                modified_files.append((str(file_path), replacements))
                total_replacements += replacements
                
        except (UnicodeDecodeError, PermissionError):
            continue
        except Exception as e:
            return f"❌ Error processing {file_path}: {str(e)}"
    
    if not modified_files:
        return f"❌ No matches found for: {search_term}"
    
    # Build summary
    summary = [f"✓ Replaced '{search_term}' with '{replace_term}' across {len(modified_files)} file(s):"]
    for file_path, count in modified_files:
        summary.append(f"  {file_path}: {count} replacement(s)")
    summary.append(f"\nTotal replacements: {total_replacements}")
    
    return "\n".join(summary)


class MIMEToolCallParser:
    """Parser for MIME-style tool calls with nesting support."""
    
    TOOL_BEGIN = "--TOOL_CALL_BEGIN"
    TOOL_END = "--TOOL_CALL_END"
    
    def __init__(self):
        self.buffer = ""
        self.in_tool = False
        self.nesting_depth = 0
    
    def feed(self, text: str) -> List[Tuple[Optional[str], str]]:
        """
        Feed text to parser and return completed tool calls.
        Returns list of (tool_call_content, preceding_text) tuples.
        tool_call_content is None for plain text segments.
        """
        results = []
        self.buffer += text
        
        while True:
            if not self.in_tool:
                # Look for start of tool call
                begin_idx = self.buffer.find(self.TOOL_BEGIN)
                if begin_idx != -1:
                    preceding = self.buffer[:begin_idx]
                    self.buffer = self.buffer[begin_idx:]
                    self.in_tool = True
                    self.nesting_depth = 1
                    if preceding:
                        results.append((None, preceding))
                else:
                    # No tool call found, keep buffer for potential partial markers
                    marker_len = len(self.TOOL_BEGIN)
                    if len(self.buffer) > marker_len:
                        results.append((None, self.buffer[:-marker_len]))
                        self.buffer = self.buffer[-marker_len:]
                    break
            else:
                # We're inside a tool call, look for nested begins or end
                search_start = len(self.TOOL_BEGIN)  # Skip the opening marker
                
                while True:
                    # Find next BEGIN or END marker
                    next_begin = self.buffer.find(self.TOOL_BEGIN, search_start)
                    next_end = self.buffer.find(self.TOOL_END, search_start)
                    
                    if next_end == -1:
                        # No end marker yet, wait for more content
                        break
                    
                    if next_begin != -1 and next_begin < next_end:
                        # Found nested tool call
                        self.nesting_depth += 1
                        search_start = next_begin + len(self.TOOL_BEGIN)
                    else:
                        # Found end marker
                        self.nesting_depth -= 1
                        if self.nesting_depth == 0:
                            # Complete tool call found
                            end_pos = next_end + len(self.TOOL_END)
                            tool_content = self.buffer[:end_pos]
                            self.buffer = self.buffer[end_pos:]
                            self.in_tool = False
                            results.append((tool_content, ""))
                            break
                        else:
                            search_start = next_end + len(self.TOOL_END)
                
                if self.in_tool:
                    # Still waiting for end marker
                    break
        
        return results
    
    def flush(self) -> str:
        """Get any remaining text in buffer."""
        remaining = self.buffer
        self.buffer = ""
        self.in_tool = False
        self.nesting_depth = 0
        return remaining


def parse_mime_tool_call(tool_content: str) -> Tuple[str, Dict[str, str]]:
    """
    Parse a MIME-style tool call and extract tool name and parameters.
    Returns (tool_name, parameters_dict)
    """
    # Remove the outer markers
    content = tool_content.strip()
    if content.startswith(MIMEToolCallParser.TOOL_BEGIN):
        content = content[len(MIMEToolCallParser.TOOL_BEGIN):].strip()
    if content.endswith(MIMEToolCallParser.TOOL_END):
        content = content[:-len(MIMEToolCallParser.TOOL_END)].strip()
    
    # Parse headers
    lines = content.split('\n')
    boundary_id = None
    header_end = 0
    
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('Boundary-ID:'):
            boundary_id = line.split(':', 1)[1].strip()
        elif line == '' and boundary_id:
            header_end = i + 1
            break
        elif line.startswith('Content-Type:'):
            continue
    
    if not boundary_id:
        raise ValueError("Missing Boundary-ID in tool call")
    
    # Parse the body using the boundary
    body = '\n'.join(lines[header_end:])
    boundary_marker = f"--{boundary_id}"
    boundary_end = f"--{boundary_id}--"
    
    # Split by boundary markers
    parts = []
    current_pos = 0
    
    while True:
        # Find next boundary
        next_boundary = body.find(boundary_marker, current_pos)
        if next_boundary == -1:
            break
        
        # Check if it's the ending boundary
        is_end = body[next_boundary:next_boundary + len(boundary_end)] == boundary_end
        
        if is_end:
            break
        
        # Find the end of this part (next boundary or end)
        part_start = next_boundary + len(boundary_marker)
        next_part = body.find(boundary_marker, part_start)
        
        if next_part == -1:
            part_content = body[part_start:]
        else:
            part_content = body[part_start:next_part]
        
        parts.append(part_content)
        current_pos = part_start
    
    # Parse each part
    params = {}
    tool_name = None
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Parse Content-Disposition header
        lines = part.split('\n')
        param_name = None
        content_start = 0
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped.startswith('Content-Disposition:'):
                # Extract name from Content-Disposition
                match = re.search(r'name="([^"]+)"', line_stripped)
                if match:
                    param_name = match.group(1)
            elif line_stripped == '' and param_name:
                content_start = i + 1
                break
        
        if param_name:
            # Get the content (everything after the blank line)
            value_lines = lines[content_start:]
            # Remove trailing empty lines but preserve internal structure
            while value_lines and value_lines[-1].strip() == '':
                value_lines.pop()
            value = '\n'.join(value_lines)
            
            if param_name == "tool_name":
                tool_name = value.strip()
            else:
                params[param_name] = value
    
    if not tool_name:
        raise ValueError("Missing tool_name in tool call")
    
    return tool_name, params


def format_tool_output_for_display(tool_name: str, result: str, args: Dict) -> str:
    """Format tool output for concise display."""
    
    if tool_name == "file_read":
        lines = result.splitlines()
        total_lines = len(lines)
        path = args.get('path', 'file')
        
        if total_lines <= 50:
            return f"```\n{result}\n```\n({total_lines} lines)"
        else:
            head = "\n".join(lines[:25])
            foot = "\n".join(lines[-25:])
            return f"```\n{head}\n\n... ({total_lines - 50} lines omitted) ...\n\n{foot}\n```\n({total_lines} lines total)"
    
    elif tool_name == "file_edit":
        lines = result.splitlines()
        additions = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
        return f"```diff\n{result}\n```\n(+{additions} -{deletions})"
    
    elif tool_name == "file_list":
        lines = result.splitlines()
        total_files = len(lines)
        
        if result == "(no files found)":
            return result
        
        if total_files <= 40:
            return f"```\n{result}\n```\n({total_files} files)"
        else:
            head = "\n".join(lines[:20])
            foot = "\n".join(lines[-20:])
            return f"```\n{head}\n... ({total_files - 40} more files) ...\n{foot}\n```\n({total_files} files total)"
    
    elif tool_name == "search_codebase":
        lines = result.splitlines()
        total_matches = len(lines)
        
        if total_matches <= 40:
            return f"```\n{result}\n```\n({total_matches} matches)"
        else:
            head = "\n".join(lines[:20])
            foot = "\n".join(lines[-20:])
            return f"```\n{head}\n... ({total_matches - 40} more matches) ...\n{foot}\n```\n({total_matches} matches total)"
    
    return result


def execute_tool(tool_content: str, console: Console, planning_mode: bool = False) -> str:
    """Execute a tool call and return the result."""
    try:
        tool_name, tool_args = parse_mime_tool_call(tool_content)
        
        # Block all modifying tools in planning mode
        modifying_tools = ["file_edit", "file_move", "file_delete", "search_replace", "git_add", "git_commit"]
        if planning_mode and tool_name in modifying_tools:
            result = f"❌ {tool_name} is disabled in planning mode. Use /plan to toggle planning mode."
            console.print(f"[red]{result}[/red]\n")
            return result
        
        # Build a descriptive status message
        status_msg = f"🔧 {tool_name}"
        if tool_name == "file_read" and "path" in tool_args:
            status_msg += f" → {tool_args['path']}"
        elif tool_name == "file_edit" and "path" in tool_args:
            status_msg += f" → {tool_args['path']}"
        elif tool_name == "search_codebase" and "search_term" in tool_args:
            status_msg += f" → '{tool_args['search_term']}'"
        elif tool_name == "fetch_url" and "url" in tool_args:
            status_msg += f" → {tool_args['url'][:50]}..."
        
        console.print(f"\n[bold cyan]{status_msg}[/bold cyan]", end="")
        
        if tool_name not in tools.tools:
            result = f"❌ Unknown tool: {tool_name}"
            console.print(f"\r[red]{result}[/red]\n")
            return result
        
        # Show brief status during execution
        console.print(" [dim](running...)[/dim]", end="")
        
        result = tools.tools[tool_name](**tool_args)
        
        # Clear the status line
        console.print(f"\r{' ' * (len(status_msg) + 20)}\r", end="")
        
        # Show completion
        console.print(f"[green]✓[/green] [cyan]{status_msg}[/cyan]")
        
        display_output = format_tool_output_for_display(tool_name, result, tool_args)
        
        console.print(LeftAlignedMarkdown(display_output))
        console.print()
        
        return result
        
    except Exception as e:
        error_msg = f"❌ Tool execution error: {str(e)}"
        console.print(f"\r[red]{error_msg}[/red]\n")
        console.print(f"[dim]{tool_content[:500]}...[/dim]\n" if len(tool_content) > 500 else f"[dim]{tool_content}[/dim]\n")
        return error_msg


def fetch_available_models(base_url: str, api_key: str) -> List[Dict[str, str]]:
    """Fetch available models from the API /models endpoint."""
    try:
        # Construct the models endpoint URL
        # Remove /v1 suffix if present and add /models
        api_base = base_url.rstrip('/').replace('/v1', '')
        models_url = f"{api_base}/models"
        
        # Make the API request
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        response = requests.get(models_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        
        # Extract model information from the data array
        if "data" in data and isinstance(data["data"], list):
            models = []
            for model in data["data"]:
                if "id" in model:
                    models.append({
                        "id": model["id"],
                        "owned_by": model.get("owned_by", "unknown"),
                        "created": model.get("created", 0)
                    })
            if models:
                return models
        
        # Return empty list if response format is unexpected
        return []
        
    except Exception as e:
        # Return empty list if API call fails
        print(f"Warning: Failed to fetch models from API ({str(e)})")
        return []


def manage_context(messages: List[Dict], max_tokens: int) -> List[Dict]:
    """Trim old messages to stay within context limit."""
    total_chars = sum(len(m.get('content', '')) for m in messages)
    estimated_tokens = total_chars // 4
    
    while estimated_tokens > max_tokens and len(messages) > 2:
        messages.pop(1)
        total_chars = sum(len(m.get('content', '')) for m in messages)
        estimated_tokens = total_chars // 4
    
    return messages


def stream_response(
    messages: List[Dict],
    base_url: str,
    api_key: str,
    model: str,
    console: Console,
    planning_mode: bool = False
) -> str:
    """Stream response from API and handle tool calls."""
    
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": 16000
    }
    
    full_response = ""
    tool_outputs = []
    parser = MIMEToolCallParser()
    display_buffer = ""
    first_content_received = False
    
    # Show initial "waiting" indicator
    console.print("[dim]⏳ Waiting for response...[/dim]", end="")
    
    response = requests.post(url, headers=headers, json=data, stream=True)
    response.raise_for_status()
    
    with Live("", console=console, refresh_per_second=10) as live:
        for line in response.iter_lines():
            if not line:
                continue
            
            line = line.decode('utf-8')
            if not line.startswith('data: '):
                continue
            
            if line == 'data: [DONE]':
                break
            
            try:
                chunk = json.loads(line[6:])
                delta = chunk.get('choices', [{}])[0].get('delta', {})
                content = delta.get('content', '')
                
                if not content:
                    continue
                
                # Clear the waiting indicator on first content
                if not first_content_received:
                    console.print("\r" + " " * 40 + "\r", end="")  # Clear the line
                    first_content_received = True
                
                full_response += content
                
                # Parse for tool calls
                results = parser.feed(content)
                
                for tool_content, text in results:
                    if tool_content:
                        # Complete tool call found
                        live.stop()
                        if display_buffer.strip():
                            console.print(LeftAlignedMarkdown(display_buffer))
                        display_buffer = ""
                        
                        tool_result = execute_tool(tool_content, console, planning_mode)
                        tool_outputs.append((tool_content, tool_result))
                        
                        # If tool execution failed, interrupt streaming to let LLM read error
                        if tool_result.startswith("❌"):
                            console.print("[yellow]⚠️  Tool error detected - interrupting stream to report error[/yellow]\n")
                            break
                        
                        live.start()
                    else:
                        display_buffer += text
                        live.update(LeftAlignedMarkdown(display_buffer))
                
            except json.JSONDecodeError:
                continue
        
        # Flush remaining content while still in Live context
        remaining = parser.flush()
        if remaining.strip():
            display_buffer += remaining
        
        # Final update to show everything
        if display_buffer.strip():
            live.update(LeftAlignedMarkdown(display_buffer))
    
    # Print any remaining content after Live context ends
    if display_buffer.strip():
        console.print(LeftAlignedMarkdown(display_buffer))
    
    # Handle tool outputs - make follow-up request
    if tool_outputs:
        for tool_call, tool_output in tool_outputs:
            messages.append({
                "role": "assistant",
                "content": tool_call
            })
            
            tool_result = {
                "status": "success" if not tool_output.startswith("❌") else "error",
                "output": tool_output
            }
            
            messages.append({
                "role": "user",
                "content": f"Tool output:\n{json.dumps(tool_result, indent=2)}"
            })
        
        console.print("\n[dim]Processing tool results...[/dim]\n")
        return stream_response(messages, base_url, api_key, model, console, planning_mode)
    
    return full_response


def get_multiline_input(console: Console) -> str:
    """Get multiline input from user."""
    console.print("[dim]Enter your message (Ctrl+D or empty line to finish):[/dim]")
    lines = []
    try:
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
    except EOFError:
        pass
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="LLM CLI Coding Assistant")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", DEFAULT_BASE_URL),
                       help="API base URL")
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY"),
                       help="API key")
    parser.add_argument("--model", default=os.getenv("MODEL_NAME", DEFAULT_MODEL),
                       help="Model name")
    parser.add_argument("--max-tokens", type=int, default=MAX_CONTEXT_TOKENS,
                       help="Maximum context tokens")
    parser.add_argument("--list-models", action="store_true",
                       help="List available models")
    parser.add_argument("-p", "--prompt", type=str,
                       help="Execute a single prompt and exit")
    
    args = parser.parse_args()
    
    if args.list_models:
        if not args.api_key:
            print("Error: API key required. Set OPENAI_API_KEY in .env or use --api-key")
            sys.exit(1)
        
        print("Fetching available models...")
        models = fetch_available_models(args.base_url, args.api_key)
        
        if models:
            print(f"\nAvailable models ({len(models)}):")
            for model in models:
                owner = model.get('owned_by', 'unknown')
                print(f"  - {model['id']:<30} (owned by: {owner})")
        else:
            print("\nNo models available or failed to fetch.")
        sys.exit(0)
    
    if not args.api_key:
        print("Error: API key required. Set OPENAI_API_KEY in .env or use --api-key")
        sys.exit(1)
    
    console = Console()
    
    # Initialize
    log_session_start()
    planning_mode = False
    current_model = args.model
    system_prompt = tools.get_system_prompt(planning_mode)
    messages = [{"role": "system", "content": system_prompt}]
    
    # Handle single prompt mode
    if args.prompt:
        log_conversation("user", args.prompt)
        messages.append({"role": "user", "content": args.prompt})
        
        console.print(f"[bold blue]Assistant:[/bold blue]\n")
        
        response = stream_response(
            messages,
            args.base_url,
            args.api_key,
            current_model,
            console,
            planning_mode
        )
        
        log_conversation("assistant", response)
        console.print()  # Final newline
        sys.exit(0)
    
    # Interactive mode
    console.print(f"[bold green]LLM CLI Coding Assistant[/bold green]")
    console.print(f"[dim]Model: {args.model}[/dim]")
    console.print(f"[dim]Project root: {GIT_ROOT}[/dim]")
    console.print("[dim]Commands: /help, /clear, /model, /plan, /multiline, /undo, /quit[/dim]\n")
    
    # Setup history
    history_file = Path.home() / ".llode_history"
    history = FileHistory(str(history_file))
    
    while True:
        try:
            user_input = pt_prompt(
                "You: ",
                history=history,
                multiline=False
            ).strip()
            
            if not user_input:
                continue
            
            # Handle commands
            if user_input.startswith('/'):
                cmd = user_input[1:].lower().split()[0]
                
                if cmd in ('quit', 'exit', 'q'):
                    console.print("[yellow]Goodbye![/yellow]")
                    break
                elif cmd == 'help':
                    console.print("""
[bold]Available commands:[/bold]
  /help      - Show this help
  /clear     - Clear conversation history
  /model     - Change model
  /plan      - Toggle planning mode (disables file editing)
  /multiline - Enter multiline input mode
  /undo      - Revert a previous commit
  /quit      - Exit the assistant
""")
                    continue
                elif cmd == 'model':
                    console.print("\n[bold]Fetching available models...[/bold]")
                    models = fetch_available_models(args.base_url, args.api_key)
                    
                    if models:
                        console.print(f"\n[bold]Available models ({len(models)}):[/bold]")
                        for i, model in enumerate(models, 1):
                            owner = model.get('owned_by', 'unknown')
                            marker = " [cyan](current)[/cyan]" if model['id'] == current_model else ""
                            console.print(f"  {i}. {model['id']}{marker}")
                        
                        console.print("\nEnter model number or name (or press Enter to cancel): ", end="")
                        choice = input().strip()
                        
                        if choice:
                            # Try as number first
                            if choice.isdigit():
                                idx = int(choice) - 1
                                if 0 <= idx < len(models):
                                    current_model = models[idx]['id']
                                    console.print(f"[green]Model changed to: {current_model}[/green]\n")
                                else:
                                    console.print("[red]Invalid model number[/red]\n")
                            # Try as model name
                            elif any(m['id'] == choice for m in models):
                                current_model = choice
                                console.print(f"[green]Model changed to: {current_model}[/green]\n")
                            else:
                                console.print("[red]Model not found. Using entered name anyway.[/red]")
                                current_model = choice
                                console.print(f"[yellow]Model changed to: {current_model}[/yellow]\n")
                    else:
                        console.print("[yellow]Could not fetch models from API. Enter model name manually:[/yellow] ", end="")
                        new_model = input().strip()
                        if new_model:
                            current_model = new_model
                            console.print(f"[green]Model changed to: {current_model}[/green]\n")
                    continue
                elif cmd == 'plan':
                    planning_mode = not planning_mode
                    system_prompt = tools.get_system_prompt(planning_mode)
                    messages[0] = {"role": "system", "content": system_prompt}
                    status = "ENABLED" if planning_mode else "DISABLED"
                    color = "yellow" if planning_mode else "green"
                    console.print(f"\n[bold {color}]Planning mode {status}[/bold {color}]")
                    if planning_mode:
                        console.print("[yellow]File editing is now disabled.[/yellow]\n")
                    else:
                        console.print("[green]File editing is now enabled.[/green]\n")
                    continue
                elif cmd == 'clear':
                    messages = [{"role": "system", "content": system_prompt}]
                    console.print("[green]Conversation history cleared[/green]\n")
                    continue
                elif cmd == 'multiline':
                    user_input = get_multiline_input(console)
                    if not user_input:
                        continue
                elif cmd == 'undo':
                    # Get recent commits (llode commits and their reverts)
                    try:
                        # Get commits with [llode] in message
                        result = subprocess.run(
                            ["git", "log", "--grep=\\[llode\\]", "--format=%h|%s|%ar", "-20"],
                            cwd=str(GIT_ROOT),
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        
                        if result.returncode != 0:
                            console.print("[red]❌ Failed to get git log[/red]\n")
                            continue
                        
                        commits = []
                        for line in result.stdout.strip().split('\n'):
                            if line:
                                parts = line.split('|', 2)
                                if len(parts) == 3:
                                    commits.append({
                                        'hash': parts[0],
                                        'message': parts[1],
                                        'time': parts[2]
                                    })
                        
                        if not commits:
                            console.print("[yellow]No llode commits found[/yellow]\n")
                            continue
                        
                        console.print("\n[bold]Recent commits:[/bold]")
                        for i, commit in enumerate(commits, 1):
                            console.print(f"  {i}. {commit['hash']} {commit['message']} [dim]({commit['time']})[/dim]")
                        
                        console.print("\nEnter number or hash to revert (or press Enter to cancel): ", end="")
                        choice = input().strip()
                        
                        if not choice:
                            console.print("[yellow]Cancelled[/yellow]\n")
                            continue
                        
                        # Resolve choice to hash
                        commit_hash = None
                        if choice.isdigit():
                            idx = int(choice) - 1
                            if 0 <= idx < len(commits):
                                commit_hash = commits[idx]['hash']
                            else:
                                console.print("[red]Invalid commit number[/red]\n")
                                continue
                        else:
                            # Try as hash
                            commit_hash = choice
                        
                        # Check for uncommitted changes
                        status_result = subprocess.run(
                            ["git", "status", "--porcelain"],
                            cwd=str(GIT_ROOT),
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        
                        if status_result.stdout.strip():
                            console.print("[yellow]⚠️  Warning: You have uncommitted changes.[/yellow]")
                            console.print("The revert will be committed automatically.")
                            console.print("Continue? (y/N): ", end="")
                            confirm = input().strip().lower()
                            if confirm != 'y':
                                console.print("[yellow]Cancelled[/yellow]\n")
                                continue
                        
                        # Perform git revert
                        console.print(f"\n[cyan]Reverting commit {commit_hash}...[/cyan]")
                        revert_result = subprocess.run(
                            ["git", "revert", "--no-edit", commit_hash],
                            cwd=str(GIT_ROOT),
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        
                        if revert_result.returncode != 0:
                            error_msg = revert_result.stderr or revert_result.stdout
                            console.print(f"[red]❌ Revert failed:[/red]\n{error_msg}\n")
                            
                            # Check if it's a merge conflict
                            if "conflict" in error_msg.lower():
                                console.print("[yellow]Resolve conflicts manually and run: git revert --continue[/yellow]\n")
                            continue
                        
                        # Get the reverted commit message for context
                        msg_result = subprocess.run(
                            ["git", "log", "-1", "--format=%s", commit_hash],
                            cwd=str(GIT_ROOT),
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        reverted_msg = msg_result.stdout.strip() if msg_result.returncode == 0 else "unknown"
                        
                        console.print(f"[green]✓ Reverted: {commit_hash} {reverted_msg}[/green]\n")
                        
                        # Add system message to conversation to inform the LLM
                        system_msg = f"System: Reverted commit {commit_hash}: {reverted_msg}\nThe codebase has been restored to the state before this commit."
                        messages.append({
                            "role": "user",
                            "content": system_msg
                        })
                        log_conversation("system", system_msg)
                        
                        console.print("[dim]LLM has been notified of the revert[/dim]\n")
                        
                    except subprocess.TimeoutExpired:
                        console.print("[red]❌ Git operation timed out[/red]\n")
                    except FileNotFoundError:
                        console.print("[red]❌ git command not found[/red]\n")
                    except Exception as e:
                        console.print(f"[red]❌ Error: {str(e)}[/red]\n")
                    continue
                else:
                    console.print(f"[red]Unknown command: /{cmd}[/red]\n")
                    continue
            
            log_conversation("user", user_input)
            messages.append({"role": "user", "content": user_input})
            messages = manage_context(messages, args.max_tokens)
            
            console.print("\n[bold blue]Assistant:[/bold blue]")
            
            response = stream_response(
                messages,
                args.base_url,
                args.api_key,
                current_model,
                console,
                planning_mode
            )
            
            log_conversation("assistant", response)
            messages.append({"role": "assistant", "content": response})
            
            console.print()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Use /quit to exit[/yellow]")
            continue
        except EOFError:
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {str(e)}[/red]\n")
            continue


if __name__ == "__main__":
    main()
