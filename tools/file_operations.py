"""
File operations tool module.

Dependencies:
- None (uses Python standard library)

Description:
Provides comprehensive file manipulation tools including listing, reading,
editing, searching, moving, deleting, and multi-file search and replace.
"""

import re
from fnmatch import fnmatch
from typing import List
from difflib import unified_diff


def register_tools(registry, git_root):
    """Register file operation tools."""
    
    # Import core utilities from llode
    import sys
    parent_module = sys.modules['__main__']
    validate_path = parent_module.validate_path
    get_gitignore_spec = parent_module.get_gitignore_spec
    walk_files = parent_module.walk_files
    
    @registry.register("file_list", """Lists all files in the project directory recursively.

Returns a list of all files, excluding those in .gitignore and dotfiles.""")
    def file_list() -> str:
        """List all files in the git root directory, respecting .gitignore."""
        files = walk_files(get_gitignore_spec())
        return "\n".join(str(f) for f in files) if files else "(no files found)"
    
    @registry.register("file_read", """Reads the contents of a file.

Parameters:
- path: relative path to the file
- start_line: optional starting line number (1-indexed, inclusive)
- end_line: optional ending line number (1-indexed, inclusive)

Returns the file contents or specified line range.

EXAMPLES:
- Read entire file: file_read(path="src/main.py")
- Read lines 10-50: file_read(path="src/main.py", start_line="10", end_line="50")
- Read from line 100 to end: file_read(path="src/main.py", start_line="100")""")
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
    
    @registry.register("file_edit", """Edits a file by replacing old_str with new_str, OR creates/overwrites a file.

Parameters:
- path: relative path to the file (required)
- new_str: replacement string or new file content (required)
- old_str: exact string to replace (optional)

BEHAVIOR:
- If old_str is NOT provided: Creates a new file or OVERWRITES existing file with new_str
- If old_str is provided: Searches for exact match and replaces with new_str

The old_str must match EXACTLY including all whitespace and newlines when provided.

EXAMPLES:
- Edit existing file:
  file_edit(path="config.py", old_str="def hello():\\n    print(\\"Hello\\")", new_str="def hello(name=\\"World\\"):\\n    print(f\\"Hello, {name}!\\")")

- Create/overwrite file (omit old_str):
  file_edit(path="new_file.py", new_str="#!/usr/bin/env python3\\nprint(\\"New file!\\")")""")
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
    
    @registry.register("search_codebase", """Searches for a string in the codebase.

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
                full_path = git_root / file_path
                content = full_path.read_text()
                lines = content.splitlines()
                
                for line_num, line in enumerate(lines, 1):
                    compare_line = line if case_sensitive_bool else line.lower()
                    if search_pattern in compare_line:
                        results.append(f"{file_path}:{line_num}: {line.strip()}")
            except (UnicodeDecodeError, PermissionError):
                continue
        
        return "\n".join(results) if results else f"No matches found for: {search_term}"
    
    @registry.register("file_move", """Moves or renames a file.

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
    
    @registry.register("file_delete", """Deletes a file.

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
    
    @registry.register("search_replace", """Search and replace text across multiple files.

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
                full_path = git_root / file_path
                content = full_path.read_text()
                
                # Perform replacement
                if case_sensitive_bool:
                    new_content = content.replace(search_term, replace_term)
                else:
                    # Case-insensitive replacement
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