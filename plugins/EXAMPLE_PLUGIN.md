# Example Plugin Tutorial

This document shows how to create a simple plugin step-by-step.

## Example 1: Simple Text Statistics Plugin

This plugin adds a tool to analyze text files and provide statistics.

```python
"""
Text statistics plugin for analyzing file content.

Dependencies:
- None (uses Python standard library)

Description:
Provides tools to analyze text files including word count,
line count, character count, and readability metrics.
"""

import re
from pathlib import Path


def register_tools(registry, git_root):
    """Register text analysis tools."""
    
    # Import core utilities from llode
    import sys
    parent_module = sys.modules['__main__']
    validate_path = parent_module.validate_path
    
    @registry.register("analyze_text", """Analyzes text file statistics.
    
    Parameters:
    - path: file path to analyze (required)
    - include_details: show detailed word frequency (default: false)
    
    Returns statistics about the text file including:
    - Line count, word count, character count
    - Average words per line
    - Most common words (if include_details=true)
    """)
    def analyze_text(path: str, include_details: str = "false"):
        """Analyze text file and return statistics."""
        try:
            # Validate and read file
            file_path = validate_path(path)
            if not file_path.exists():
                return f"❌ File not found: {path}"
            
            content = file_path.read_text()
            
            # Basic statistics
            lines = content.splitlines()
            line_count = len(lines)
            char_count = len(content)
            words = re.findall(r'\b\w+\b', content.lower())
            word_count = len(words)
            
            avg_words_per_line = word_count / line_count if line_count > 0 else 0
            
            result = [
                f"📊 Text Statistics for {path}:",
                f"  Lines: {line_count:,}",
                f"  Words: {word_count:,}",
                f"  Characters: {char_count:,}",
                f"  Avg words/line: {avg_words_per_line:.1f}"
            ]
            
            # Detailed analysis
            if include_details.lower() == "true":
                from collections import Counter
                word_freq = Counter(words)
                most_common = word_freq.most_common(10)
                
                result.append("\n  Most common words:")
                for word, count in most_common:
                    result.append(f"    {word}: {count}")
            
            return '\n'.join(result)
            
        except Exception as e:
            return f"❌ Error analyzing file: {str(e)}"
```

## Example 2: Project Structure Analyzer

This plugin helps understand project organization.

```python
"""
Project structure analyzer plugin.

Dependencies:
- None

Description:
Analyzes project directory structure and provides insights
about organization, file types, and directory sizes.
"""

from pathlib import Path
from collections import defaultdict


def register_tools(registry, git_root):
    """Register project structure tools."""
    
    import sys
    parent_module = sys.modules['__main__']
    walk_files = parent_module.walk_files
    get_gitignore_spec = parent_module.get_gitignore_spec
    
    @registry.register("analyze_project_structure", """Analyzes project structure.
    
    Parameters:
    - depth: directory depth to analyze (default: 3)
    - show_sizes: include file sizes (default: true)
    
    Returns overview of project organization including:
    - Directory tree structure
    - File types distribution
    - Largest files and directories
    """)
    def analyze_project_structure(depth: str = "3", show_sizes: str = "true"):
        """Analyze project directory structure."""
        try:
            max_depth = int(depth)
            include_sizes = show_sizes.lower() == "true"
            
            gitignore_spec = get_gitignore_spec()
            files = walk_files(gitignore_spec)
            
            # Analyze file types
            extensions = defaultdict(int)
            total_size = 0
            file_sizes = []
            
            for file_path in files:
                full_path = git_root / file_path
                ext = full_path.suffix or "(no extension)"
                extensions[ext] += 1
                
                if include_sizes:
                    size = full_path.stat().st_size
                    total_size += size
                    file_sizes.append((str(file_path), size))
            
            # Build result
            result = [
                f"📁 Project Structure Analysis:",
                f"  Total files: {len(files):,}",
            ]
            
            if include_sizes:
                result.append(f"  Total size: {total_size:,} bytes ({total_size / 1024 / 1024:.1f} MB)")
            
            # File types
            result.append("\n  File types:")
            for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True)[:10]:
                result.append(f"    {ext}: {count}")
            
            # Largest files
            if include_sizes and file_sizes:
                result.append("\n  Largest files:")
                file_sizes.sort(key=lambda x: x[1], reverse=True)
                for path, size in file_sizes[:10]:
                    size_kb = size / 1024
                    result.append(f"    {path}: {size_kb:.1f} KB")
            
            return '\n'.join(result)
            
        except Exception as e:
            return f"❌ Error analyzing structure: {str(e)}"
```

## Example 3: Integration with External Tools

This plugin shows how to call external commands.

```python
"""
Code quality checker plugin using external tools.

Dependencies:
- pylint (optional, for Python linting)
- flake8 (optional, for Python style checking)

Description:
Runs code quality tools and reports issues.
"""

import subprocess
import shutil


def register_tools(registry, git_root):
    """Register code quality tools."""
    
    import sys
    parent_module = sys.modules['__main__']
    validate_path = parent_module.validate_path
    
    @registry.register("check_python_style", """Checks Python code style.
    
    Parameters:
    - path: Python file to check (required)
    - tool: pylint|flake8|both (default: both)
    
    Runs style checkers and reports issues found.
    Requires pylint and/or flake8 to be installed.
    """)
    def check_python_style(path: str, tool: str = "both"):
        """Check Python file with style checkers."""
        try:
            file_path = validate_path(path)
            if not file_path.exists():
                return f"❌ File not found: {path}"
            
            if not file_path.suffix == '.py':
                return f"❌ Not a Python file: {path}"
            
            results = []
            
            # Check pylint
            if tool in ("pylint", "both"):
                if shutil.which("pylint"):
                    result = subprocess.run(
                        ["pylint", str(file_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    results.append(f"## Pylint Results:\n```\n{result.stdout}\n```")
                else:
                    results.append("⚠️  pylint not installed")
            
            # Check flake8
            if tool in ("flake8", "both"):
                if shutil.which("flake8"):
                    result = subprocess.run(
                        ["flake8", str(file_path)],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.stdout:
                        results.append(f"## Flake8 Results:\n```\n{result.stdout}\n```")
                    else:
                        results.append("✓ Flake8: No issues found")
                else:
                    results.append("⚠️  flake8 not installed")
            
            return '\n\n'.join(results) if results else "❌ No tools available"
            
        except subprocess.TimeoutExpired:
            return "❌ Style check timed out"
        except Exception as e:
            return f"❌ Error checking style: {str(e)}"
```

## Testing Your Plugin

1. **Create the plugin file**: Save your plugin as `plugins/my_plugin.py`

2. **Start llode**: It will automatically discover and load your plugin
   ```
   Loading plugins...
     ✓ my_plugin
   Loaded 1 plugin(s)
   ```

3. **Check plugin status**: Use `/plugins` command
   ```
   You: /plugins
   
   Plugin Status:
   Loaded plugins:
     • my_plugin: Description from plugin docstring
   ```

4. **Use your tools**: The LLM can now use your tools
   ```
   You: Analyze the text statistics for README.md
   
   [LLM calls analyze_text tool]
   ```

## Best Practices

1. **Error Handling**: Always wrap operations in try/except
2. **Validation**: Validate file paths using `validate_path()`
3. **Timeouts**: Set timeouts for subprocess calls
4. **Documentation**: Write clear tool descriptions for the LLM
5. **Dependencies**: Document required packages in plugin docstring
6. **Return Strings**: Always return strings (what the LLM will see)
7. **User Feedback**: Use emoji and formatting for better readability

## Common Patterns

### Pattern 1: Accessing Files
```python
import sys
parent_module = sys.modules['__main__']
validate_path = parent_module.validate_path

file_path = validate_path(path)  # Returns Path object
content = file_path.read_text()
```

### Pattern 2: Walking Files
```python
walk_files = parent_module.walk_files
get_gitignore_spec = parent_module.get_gitignore_spec

gitignore_spec = get_gitignore_spec()
all_files = walk_files(gitignore_spec)
```

### Pattern 3: Calling External Tools
```python
import subprocess
import shutil

if shutil.which("tool_name"):
    result = subprocess.run(
        ["tool_name", "arg1", "arg2"],
        capture_output=True,
        text=True,
        timeout=30
    )
    output = result.stdout
```

### Pattern 4: Database Operations
```python
import sqlite3
from pathlib import Path

db_path = git_root / ".llode" / "my_plugin.db"
db_path.parent.mkdir(exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
# ... perform queries ...
conn.close()
```