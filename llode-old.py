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
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Callable, Optional
from dotenv import load_dotenv
import requests
from difflib import unified_diff
import pathspec
from rich.console import Console
from rich.markdown import Markdown
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


def find_git_root() -> Path:
    """Find the git root directory, starting from current directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # If no git root found, use current directory
    return Path.cwd()


class ToolRegistry:
    """Registry for tool functions."""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.descriptions: Dict[str, str] = {}
    
    def register(self, name: str, description: str):
        """Decorator to register a tool function."""
        def decorator(func: Callable):
            self.tools[name] = func
            self.descriptions[name] = description
            return func
        return decorator

    def get_system_prompt(self, planning_mode: bool = False) -> str:
        """Generate system prompt from registered tools."""
        # Filter out edit_file in planning mode
        if planning_mode:
            filtered_descriptions = {k: v for k, v in self.descriptions.items() if k != "edit_file"}
        else:
            filtered_descriptions = self.descriptions
        
        tools_desc = "\n\n".join([
            f"**{name}**\n{desc}"
            for name, desc in filtered_descriptions.items()
        ])

        planning_prefix = ""
        if planning_mode:
            planning_prefix = """[PLANNING MODE ACTIVE]

You are currently in PLANNING MODE. In this mode, you CANNOT modify any files.
Your role is to:
- Analyze the codebase and requirements
- Create detailed implementation plans
- Break down complex tasks into steps
- Suggest approaches and solutions
- Use the todo list to organize work
- Read files and search the codebase for understanding

The edit_file tool is DISABLED. Focus on planning and analysis.

"""

        return f"""{planning_prefix}You are a coding assistant with access to file manipulation tools.

IMPORTANT: Use tools with this EXACT XML format:

For tools WITH parameters:
<tool_call>
<tool_name>tool_name</tool_name>
<parameters>
<param1><![CDATA[value1]]></param1>
<param2><![CDATA[value2]]></param2>
</parameters>
</tool_call>

For tools WITHOUT parameters:
<tool_call>
<tool_name>tool_name</tool_name>
</tool_call>

RULES:
1. ALL parameter values MUST be wrapped in CDATA sections
2. Use XML tags to preserve exact whitespace and newlines
3. old_str must match EXACTLY (every space, tab, newline)
4. If old_str is empty, a new file will be created
5. All file paths are relative to the project root
6. Do not access dotfiles

Example for reading a file:
<tool_call>
<tool_name>read_file</tool_name>
<parameters>
<path><![CDATA[src/main.py]]></path>
</parameters>
</tool_call>

Example for editing with XML in content:
<tool_call>
<tool_name>edit_file</tool_name>
<parameters>
<path><![CDATA[config.xml]]></path>
<old_str><![CDATA[<setting>old</setting>]]></old_str>
<new_str><![CDATA[<setting>new</setting>]]></new_str>
</parameters>
</tool_call>

DEBUGGING TOOL CALL ERRORS:
If you get "Invalid tool XML" errors:
1. Check that EVERY parameter has both <![CDATA[ and ]]>
2. Verify no extra spaces around CDATA tags
3. Ensure old_str matches the file EXACTLY (whitespace matters!)
4. For content with ]]> inside, remember the escape pattern
5. Check that all XML tags are properly closed


CRITICAL CDATA RULES (violations cause 100% failure rate):
1. EVERY parameter value MUST have BOTH <![CDATA[ AND ]]>
2. NO spaces: <![CDATA[content]]> NOT <![CDATA[ content ]]>
3. For ]]> in content, use: ]]]]><![CDATA[>
4. Empty values: <old_str><![CDATA[]]></old_str>

VERIFICATION CHECKLIST before sending tool call:
* Every <parameter> has opening <![CDATA[
* Every <parameter> has closing ]]>
* No extra spaces around CDATA markers
* No naked ]]> sequences in content
* A parameter start tag must match the parameter's end tag.

COMMON MISTAKES:
❌ Mismatched tags: <old_str><![CDATA[data]]</new_str>
✅ Correct: <old_str><![CDATA[data]]</old_str>

❌ Forgetting CDATA: <path>file.py</path>
✅ Correct: <path><![CDATA[]]></path>

❌ Wrong closing: <path><![CDATA></path>
✅ Correct: <path><![CDATA[]]></path>

❌ Whitespace mismatch in old_str
✅ Copy exact spacing including all tabs/newlines

❌ Missing escape for ]]> in content
✅ Use ]]]]><![CDATA[> pattern when needed

{tools_desc}
"""


# Initialize tool registry and git root
tools = ToolRegistry()
GIT_ROOT = find_git_root()
LOG_FILE = GIT_ROOT / "LLODE_LOG.md"


def log_conversation(role: str, content: str) -> None:
    """Log a conversation message to LLODE_LOG.md"""
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


def is_ignored(path: Path, spec: Optional[pathspec.PathSpec]) -> bool:
    """Check if path should be ignored based on .gitignore."""
    if spec is None:
        return False
    
    # Get relative path from git root
    try:
        rel_path = path.relative_to(GIT_ROOT)
    except ValueError:
        return True
    
    return spec.match_file(str(rel_path))


def validate_path(path_str: str) -> Path:
    """Validate and resolve a path relative to git root."""
    path_str = path_str.lstrip('/')
    path = (GIT_ROOT / path_str).resolve()
    
    try:
        rel_path = path.relative_to(GIT_ROOT)
        if is_dotfile(rel_path):
            raise ValueError(f"Access to dotfiles is not allowed: {path_str}")
    except ValueError:
        raise ValueError(f"Path {path_str} is outside the project directory")
    
    return path


def walk_files(gitignore_spec: Optional[pathspec.PathSpec]) -> List[Path]:
    """Walk directory tree and yield valid file paths."""
    files = []
    for root, dirs, filenames in os.walk(GIT_ROOT):
        root_path = Path(root)
        
        # Filter directories in-place
        dirs[:] = [d for d in dirs 
                   if not is_dotfile(root_path.relative_to(GIT_ROOT) / d) 
                   and not is_ignored(root_path / d, gitignore_spec)]
        
        # Add valid files
        for filename in filenames:
            file_path = root_path / filename
            rel_path = file_path.relative_to(GIT_ROOT)
            if not is_dotfile(rel_path) and not is_ignored(file_path, gitignore_spec):
                files.append(rel_path)
    
    return sorted(files)


@tools.register("list_files", """Lists all files in the project directory recursively.
Usage:
<tool_call>
<tool_name>list_files</tool_name>
<parameters>
</parameters>
</tool_call>

Returns a list of all files, excluding those in .gitignore and dotfiles.""")
def list_files() -> str:
    """List all files in the git root directory, respecting .gitignore."""
    files = walk_files(get_gitignore_spec())
    return "\n".join(str(f) for f in files) if files else "(no files found)"


@tools.register("read_file", """Reads the contents of a file.
Usage:
<tool_call>
<tool_name>read_file</tool_name>
<parameters>
<path>relative/path/to/file.txt</path>
</parameters>
</tool_call>

Returns the file contents.""")
def read_file(path: str) -> str:
    """Read and return the contents of a file."""
    file_path = validate_path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    return file_path.read_text()


@tools.register("edit_file", """Edits a file by replacing old_str with new_str.
Usage:
<tool_call>
<tool_name>edit_file</tool_name>
<parameters>
<path>relative/path/to/file.txt</path>
<old_str>exact text to replace
including all whitespace</old_str>
<new_str>new text content
with exact formatting</new_str>
</parameters>
</tool_call>

If old_str is empty, creates a new file with new_str content.
The old_str must match EXACTLY including all whitespace and newlines.""")
def edit_file(path: str, old_str: str, new_str: str) -> str:
    """Edit a file by replacing old_str with new_str."""
    file_path = validate_path(path)
    
    if not old_str:
        if file_path.exists():
            raise ValueError(f"File already exists: {path}. Use non-empty old_str to edit.")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(new_str)
        return f"Created new file: {path}\n{len(new_str)} bytes written"
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}. Use empty old_str to create new file.")
    
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
Usage:
<tool_call>
<tool_name>fetch_url</tool_name>
<parameters>
<url>https://example.com/page</url>
</parameters>
</tool_call>

Returns the content from the URL. Supports HTTP and HTTPS.""")
def fetch_url(url: str) -> str:
    """Fetch content from a URL."""
    try:
        # Validate URL starts with http:// or https://
        if not url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        
        # Make the request with a timeout
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LLM-CLI-Assistant/1.0)'
        })
        response.raise_for_status()
        
        # Get content type
        content_type = response.headers.get('content-type', '').lower()
        
        # Return appropriate content based on type
        if 'application/json' in content_type:
            return response.text
        elif 'text/' in content_type or 'application/xml' in content_type:
            return response.text
        else:
            # For binary or unknown content types
            return f"Content-Type: {content_type}\nContent-Length: {len(response.content)} bytes\n\n(Binary or non-text content - first 500 chars):\n{response.text[:500]}"
        
    except requests.exceptions.Timeout:
        raise TimeoutError(f"Request timed out after 30 seconds: {url}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to fetch URL: {str(e)}")


@tools.register("search_codebase", """Searches for a string in the codebase.
Usage:
<tool_call>
<tool_name>search_codebase</tool_name>
<parameters>
<search_term>text to search for</search_term>
<case_sensitive>false</case_sensitive>
</parameters>
</tool_call>

Parameters:
- search_term: The string to search for (required)
- case_sensitive: Whether to match case (default: false)

Returns matches with file path, line number, and line content.
Respects .gitignore and excludes dotfiles.""")
def search_codebase(search_term: str, case_sensitive: str = "false") -> str:
    """Search for a string in all files in the codebase."""
    if not search_term:
        raise ValueError("search_term cannot be empty")
    
    case_sensitive_bool = case_sensitive.lower() == "true"
    search_lower = search_term if case_sensitive_bool else search_term.lower()
    results = []
    
    for rel_path in walk_files(get_gitignore_spec()):
        file_path = GIT_ROOT / rel_path
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, start=1):
                    line_to_search = line if case_sensitive_bool else line.lower()
                    if search_lower in line_to_search:
                        results.append(f"{rel_path}:{line_num}:{line.rstrip()}")
                        if len(results) >= 100:
                            results.append("(max 100 results shown)")
                            return "\n".join(results)
        except (UnicodeDecodeError, PermissionError, IsADirectoryError):
            continue
    
    return "\n".join(results) if results else f"No matches found for: {search_term}"


@tools.register("todo_read", """Reads the current todo list from LLODE_TODO.json.
Usage:
<tool_call>
<tool_name>todo_read</tool_name>
</tool_call>

Returns todo items as JSON array (empty if file doesn't exist).

Use proactively and frequently to:
* Track progress and prioritize work across conversations
* Check status at conversation start, before new tasks, and after completing work
* Stay organized when uncertain about next steps

CRITICAL: Takes NO parameters - leave blank, no dummy objects or placeholder strings.
""")
def todo_read() -> str:
    """Read the current todo list from LLODE_TODO.json."""
    todo_path = GIT_ROOT / "LLODE_TODO.json"
    return todo_path.read_text() if todo_path.exists() else "[]"


@tools.register("todo_write", """Writes/updates the todo list to LLODE_TODO.json.
Usage:
<tool_call>
<tool_name>todo_write</tool_name>
<parameters>
<content>[
  {"task": "Example task", "status": "pending", "priority": "high"},
  {"task": "Another task", "status": "completed", "priority": "medium"}
]</content>
</parameters>
</tool_call>

Content must be valid JSON array with:
- task: Description of work
- status: "pending" | "in_progress" | "completed"
- priority: "high" | "medium" | "low"

WHEN TO USE: Complex multi-step tasks (3+ steps), user-provided task lists, non-trivial planning needs.
WHEN TO SKIP: Single straightforward tasks, trivial operations (under 3 steps), purely informational requests.

CRITICAL: Mark in_progress BEFORE starting work. Only mark completed when FULLY done (not if blocked/errored).
""")
def todo_write(content: str) -> str:
    """Write/update the todo list to LLODE_TODO.json."""
    json.loads(content)  # Validate JSON
    (GIT_ROOT / "LLODE_TODO.json").write_text(content)
    return "Todo list updated successfully"


class ToolCallParser:
    """Parser for XML-style tool calls that handles nested tags."""
    
    def __init__(self):
        self.buffer = ""
        self.in_tool = False
        self.depth = 0
    
    def feed(self, text: str) -> List[tuple[str, str]]:
        """
        Feed text to parser and return completed tool calls.
        Returns list of (tool_call_xml, preceding_text) tuples.
        """
        results = []
        self.buffer += text
        
        while True:
            if not self.in_tool:
                # Look for start of tool call
                match = re.search(r'<tool_call>', self.buffer)
                if match:
                    preceding = self.buffer[:match.start()]
                    self.buffer = self.buffer[match.start():]
                    self.in_tool = True
                    self.depth = 1
                    self.tool_start = match.start()
                    if preceding:
                        results.append((None, preceding))
                else:
                    # No tool call found, keep buffer small for split tags
                    if len(self.buffer) > 20:
                        results.append((None, self.buffer[:-20]))
                        self.buffer = self.buffer[-20:]
                    break
            else:
                # Look for nested <tool_call> or closing </tool_call>
                open_match = re.search(r'<tool_call>', self.buffer)
                close_match = re.search(r'</tool_call>', self.buffer)
                
                if open_match and (not close_match or open_match.start() < close_match.start()):
                    # Found nested opening tag
                    self.buffer = self.buffer[open_match.end():]
                    self.depth += 1
                elif close_match:
                    # Found closing tag
                    self.depth -= 1
                    if self.depth == 0:
                        # Complete tool call - extract from <tool_call> to </tool_call>
                        tool_call_end = close_match.end()
                        complete_call = self.buffer[:tool_call_end]
                        self.buffer = self.buffer[tool_call_end:]
                        results.append((complete_call, ""))
                        self.in_tool = False
                    else:
                        # Still nested, continue
                        self.buffer = self.buffer[close_match.end():]
                else:
                    # No complete tag found yet, wait for more data
                    if len(self.buffer) > 100:
                        # Keep last 100 chars in case tag is split
                        self.buffer = self.buffer[-100:]
                    break
        
        return results
    
    def get_remaining(self) -> str:
        """Get any remaining text in buffer."""
        remaining = self.buffer
        self.buffer = ""
        self.in_tool = False
        return remaining


def parse_tool_call(tool_xml: str) -> tuple[str, Dict[str, str]]:
    """
    Parse XML-style tool call with proper CDATA handling.
    Returns (tool_name, parameters_dict)
    """
    try:
        # First try standard parsing
        root = ET.fromstring(tool_xml)
    except ET.ParseError:
        try:
            # If that fails, try wrapping in a root element to handle multiple root nodes
            root = ET.fromstring(f"<root>{tool_xml}</root>").find('.')
            if root is None:
                raise ValueError("No tool call found in XML")
        except ET.ParseError as e:
            raise ValueError(f"Invalid tool XML: {str(e)}")

    tool_name = root.find('tool_name')
    if tool_name is None or tool_name.text is None:
        raise ValueError("Tool call missing <tool_name>")

    params = {}
    params_elem = root.find('parameters')
    if params_elem is not None:
        for param in params_elem:
            if param.text is not None:
                # Handle CDATA if present
                if param.text.startswith('<![CDATA[') and param.text.endswith(']]>'):
                    params[param.tag] = param.text[9:-3]
                else:
                    params[param.tag] = param.text
            else:
                params[param.tag] = ""

    return tool_name.text.strip(), params


def format_tool_output_for_display(tool_name: str, result: str, tool_args: Dict[str, str]) -> str:
    """Format tool output for concise display in CLI."""
    
    if tool_name == "read_file":
        lines = result.splitlines()
        total_lines = len(lines)
        
        if total_lines <= 40:
            # Show all lines with line numbers
            numbered_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines)]
            content = "\n".join(numbered_lines)
            return f"```\n{content}\n```\n({total_lines} lines)"
        else:
            # Show first 20 and last 20 lines
            head_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines[:20])]
            foot_lines = [f"{i+1:4d} | {line}" for i, line in enumerate(lines[-20:], start=total_lines-20)]
            
            content = "\n".join(head_lines)
            content += f"\n     | ... ({total_lines - 40} more lines) ...\n"
            content += "\n".join(foot_lines)
            
            return f"```\n{content}\n```\n({total_lines} lines total)"
    
    elif tool_name == "edit_file":
        # Parse the unified diff and format it nicely
        lines = result.splitlines()
        
        if result.startswith("Created new file:"):
            return result
        
        # Count changes
        additions = sum(1 for line in lines if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in lines if line.startswith('-') and not line.startswith('---'))
        
        # Format diff with syntax highlighting hint
        return f"```diff\n{result}\n```\n(+{additions} -{deletions})"
    
    elif tool_name == "list_files":
        lines = result.splitlines()
        total_files = len(lines)
        
        if result == "(no files found)":
            return result
        
        if total_files <= 40:
            return f"```\n{result}\n```\n({total_files} files)"
        else:
            # Show first 20 and last 20 files
            head = "\n".join(lines[:20])
            foot = "\n".join(lines[-20:])
            
            return f"```\n{head}\n... ({total_files - 40} more files) ...\n{foot}\n```\n({total_files} files total)"
    
    elif tool_name == "search_codebase":
        lines = result.splitlines()
        total_matches = len(lines)
        
        if total_matches <= 40:
            return f"```\n{result}\n```\n({total_matches} matches)"
        else:
            # Show first 20 and last 20 matches
            head = "\n".join(lines[:20])
            foot = "\n".join(lines[-20:])
            
            return f"```\n{head}\n... ({total_matches - 40} more matches) ...\n{foot}\n```\n({total_matches} matches total)"
    
    # Default: return as-is for other tools
    return result


def execute_tool(tool_xml: str, console: Console, planning_mode: bool = False) -> str:
    """Execute a tool call and return the result."""
    try:
        tool_name, tool_args = parse_tool_call(tool_xml)
        
        # Block edit_file in planning mode
        if planning_mode and tool_name == "edit_file":
            result = "❌ edit_file is disabled in planning mode. Use /plan to toggle planning mode."
            console.print(f"[red]{result}[/red]\n")
            return result
        
        console.print(f"\n[bold cyan]🔧 Executing tool: {tool_name}[/bold cyan]")
        
        if tool_name not in tools.tools:
            result = f"❌ Unknown tool: {tool_name}"
            console.print(f"[red]{result}[/red]\n")
            return result
        
        # Execute the tool
        result = tools.tools[tool_name](**tool_args)
        
        # Format output for display (concise version)
        display_output = format_tool_output_for_display(tool_name, result, tool_args)
        
        # Display formatted result
        console.print(Markdown(display_output))
        console.print()
        
        # Return full result for LLM context
        return result
        
    except Exception as e:
        error_msg = f"❌ Tool execution error: {str(e)}"
        console.print(f"[red]{error_msg}[/red]\n")
        console.print(f"[red]{tool_xml}[/red]\n")
        return error_msg

    
def estimate_tokens(text: str) -> int:
    """Rough estimate of token count."""
    return len(text) // 4


def manage_context(messages: List[Dict], system_prompt: str) -> List[Dict]:
    """Manage context window to stay under token limit."""
    total_tokens = estimate_tokens(system_prompt)

    # Count tokens from newest to oldest
    kept_messages = []
    for msg in reversed(messages):
        # Skip tool call messages when counting tokens (they're paired with outputs)
        if msg.get('content', '').strip().startswith('<tool_call>'):
            continue

        msg_tokens = estimate_tokens(str(msg))
        if total_tokens + msg_tokens > MAX_CONTEXT_TOKENS:
            break
        kept_messages.insert(0, msg)
        total_tokens += msg_tokens

    return kept_messages


def stream_chat(messages: List[Dict], base_url: str, api_key: str, model: str, console: Console, planning_mode: bool = False) -> str:
    """Stream chat completion and execute tools during streaming."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # We'll maintain the full response with tool outputs
    full_response = ""
    tool_outputs = []

    # First pass - get the initial response
    data = {
        "model": model,
        "messages": messages,
        "stream": True
    }

    response = requests.post(url, headers=headers, json=data, stream=True)
    response.raise_for_status()

    in_tool_call = False
    tool_buffer = ""
    tool_depth = 0
    current_line = ""

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
                chunk = requests.compat.json.loads(line[6:])
                delta = chunk.get('choices', [{}])[0].get('delta', {})
                content = delta.get('content', '')

                if not content:
                    continue

                full_response += content

                # Process character by character for tool detection
                for char in content:
                    current_line += char

                    if not in_tool_call and '<tool_call>' in current_line:
                        in_tool_call = True
                        tool_depth = 1
                        idx = current_line.find('<tool_call>')
                        before_tool = current_line[:idx]
                        if before_tool:
                            live.update(Markdown(before_tool))
                        tool_buffer = '<tool_call>'
                        current_line = current_line[idx + len('<tool_call>'):]
                        continue

                    if in_tool_call:
                        tool_buffer += char

                        if tool_buffer.endswith('<tool_call>'):
                            tool_depth += 1
                        elif tool_buffer.endswith('</tool_call>'):
                            tool_depth -= 1

                            if tool_depth == 0:
                                in_tool_call = False
                                live.stop()

                                # Execute tool and get output
                                tool_output = execute_tool(tool_buffer, console, planning_mode)
                                tool_outputs.append((tool_buffer, tool_output))

                                # Add tool output to response
                                full_response += f"\n{tool_output}\n"

                                live.start()
                                tool_buffer = ""
                                current_line = ""
                                continue

                if not in_tool_call and current_line.strip():
                    if current_line.endswith(('\n', '.', '!', '?', ':', ';')):
                        live.update(Markdown(current_line))

            except Exception as e:
                console.print(f"[red]Error processing chunk: {e}[/red]")
                continue

    # If we had tool calls, we need to make a follow-up request with the tool outputs
    if tool_outputs:
        # Add all tool outputs to the conversation
        for tool_call, tool_output in tool_outputs:
            messages.append({
                "role": "assistant",
                "content": tool_call
            })
            
            # Wrap tool output in JSON format
            tool_result = {
                "status": "success" if not tool_output.startswith("❌") else "error",
                "output": tool_output
            }
            
            messages.append({
                "role": "user",
                "content": f"Tool output:\n{json.dumps(tool_result, indent=2)}"
            })

        # Make a second request with the tool outputs
        try:
            second_response = stream_chat(
                messages,
                base_url,
                api_key,
                model,
                console,
                planning_mode
            )
            full_response += "\n" + second_response
        except Exception as e:
            console.print(f"[red]Error in follow-up request: {e}[/red]")

    if current_line.strip() and not in_tool_call:
        console.print(Markdown(current_line))

    console.print()
    return full_response

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


def get_multiline_input(console: Console) -> str:
    """Get multiline input from user."""
    console.print("[dim]Enter your message (Ctrl+D or empty line to finish):[/dim]")
    lines = []
    try:
        while True:
            line = input()
            if not line:  # Empty line ends input
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
    
    args = parser.parse_args()
    
    if args.list_models:
        if not args.api_key:
            print("Error: API key required to fetch models. Set OPENAI_API_KEY in .env or use --api-key")
            sys.exit(1)
        
        print("Fetching available models from API...")
        models = fetch_available_models(args.base_url, args.api_key)
        
        if models:
            print(f"\nAvailable models ({len(models)}):")
            for model in models:
                owner = model.get('owned_by', 'unknown')
                print(f"  - {model['id']:<30} (owned by: {owner})")
        else:
            print("\nNo models available or failed to fetch from API.")
            print("Using default models:")
            print("  - claude-sonnet-4-5")
            print("  - claude-sonnet-3-5")
            print("  - claude-opus-4")
        return
    
    if not args.api_key:
        print("Error: API key required. Set OPENAI_API_KEY in .env or use --api-key")
        sys.exit(1)
    
    console = Console()
    
    console.print(f"[bold green]LLM CLI Coding Assistant[/bold green]")
    console.print(f"Git root: [cyan]{GIT_ROOT}[/cyan]")
    console.print(f"Model: [cyan]{args.model}[/cyan]")
    console.print(f"Type [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit\n")
    
    # Log session start
    log_session_start()
    
    planning_mode = False
    system_prompt = tools.get_system_prompt(planning_mode)
    messages = []
    current_model = args.model
    input_history = FileHistory(GIT_ROOT / '.llode_prompts')
    
    while True:
        try:
            user_input = pt_prompt("You: ", history=input_history).strip()
            
            if not user_input:
                continue
            
            # Handle slash commands
            if user_input.startswith('/'):
                cmd = user_input[1:].lower()
                
                if cmd == 'quit' or cmd == 'exit':
                    break
                elif cmd == 'help':
                    console.print("\n[bold]Available commands:[/bold]")
                    console.print("  /help - Show this help")
                    console.print("  /model - Change model")
                    console.print("  /plan - Toggle planning mode (disables file editing)")
                    console.print("  /clear - Clear conversation history")
                    console.print("  /multiline - Enter multiline input")
                    console.print("  /quit - Exit the program\n")
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
                    status = "ENABLED" if planning_mode else "DISABLED"
                    color = "yellow" if planning_mode else "green"
                    console.print(f"\n[bold {color}]Planning mode {status}[/bold {color}]")
                    if planning_mode:
                        console.print("[yellow]File editing is now disabled. Focus on planning and analysis.[/yellow]\n")
                    else:
                        console.print("[green]File editing is now enabled.[/green]\n")
                    continue
                elif cmd == 'clear':
                    messages = []
                    console.print("[green]Conversation history cleared[/green]\n")
                    continue
                elif cmd == 'multiline':
                    user_input = get_multiline_input(console)
                    if not user_input:
                        continue
                else:
                    console.print(f"[red]Unknown command: /{cmd}[/red]\n")
                    continue
            
            # Log user message
            log_conversation("user", user_input)
            
            # Add user message
            messages.append({"role": "user", "content": user_input})
            
            # Manage context
            messages = manage_context(messages, system_prompt)
            
            # Prepare messages with system prompt
            api_messages = [{"role": "system", "content": system_prompt}] + messages
            
            # Stream response
            try:
                assistant_response = stream_chat(
                    api_messages,
                    args.base_url,
                    args.api_key,
                    current_model,
                    console,
                    planning_mode
                )
                
                # Log assistant response
                log_conversation("assistant", assistant_response)
                
                # Add assistant response to history
                messages.append({"role": "assistant", "content": assistant_response})
                
            except requests.exceptions.RequestException as e:
                console.print(f"[bold red]API Error: {str(e)}[/bold red]\n")
                messages.pop()  # Remove user message on error
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted. Type /quit to exit.[/yellow]\n")
            continue
        except EOFError:
            break
    
    console.print("\n[green]Goodbye![/green]")


if __name__ == "__main__":
    main()

