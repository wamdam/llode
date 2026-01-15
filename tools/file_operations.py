"""
File operations tool module.

Dependencies:
- None (uses Python standard library)

Description:
Provides advanced file manipulation tools including move, delete,
and multi-file search and replace operations.
"""

import re
from fnmatch import fnmatch
from typing import List


def register_tools(registry, git_root):
    """Register file operation tools."""
    
    # Import core utilities from llode
    import sys
    parent_module = sys.modules['__main__']
    validate_path = parent_module.validate_path
    get_gitignore_spec = parent_module.get_gitignore_spec
    walk_files = parent_module.walk_files
    
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