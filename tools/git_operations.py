"""
Git operations plugin.

Provides git integration tools for staging, committing, and viewing changes.

Dependencies:
- git command-line tool

Description:
Adds git workflow commands to LLODE for version control integration.
All commits are automatically prefixed with [llode] for tracking.
"""

import subprocess
from pathlib import Path


def register_tools(registry, git_root):
    """Register git operation tools."""
    
    # Access core validation function
    import sys
    parent_module = sys.modules['__main__']
    validate_path = parent_module.validate_path
    
    @registry.register("git_add", """Adds files to git staging area.

Parameters:
- paths: file paths to add (can be a single path or multiple comma-separated paths)

Adds the specified files to git staging area, ready for commit.

WORKFLOW: After ANY successful file modification (file_edit, file_move, file_delete, search_replace):
1. Use git_add to stage the changed files
2. Use git_commit with a descriptive message

Example workflow:
- file_edit() → git_add() → git_commit()
- file_move() → git_add() → git_commit()
- search_replace() → git_add() → git_commit()

This ensures all changes are tracked and can be reverted if needed.""")
    def git_add(paths: str) -> str:
        """Add files to git staging area."""
        # Parse paths (can be comma-separated)
        path_list = [p.strip() for p in paths.split(',')]
        
        # Validate all paths first
        validated_paths = []
        for path in path_list:
            try:
                file_path = validate_path(path)
                validated_paths.append(str(file_path.relative_to(git_root)))
            except Exception as e:
                return f"❌ Invalid path '{path}': {str(e)}"
        
        try:
            # Run git add
            result = subprocess.run(
                ["git", "add"] + validated_paths,
                cwd=str(git_root),
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

    @registry.register("git_commit", """Creates a git commit with staged changes.

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
                cwd=str(git_root),
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
                cwd=str(git_root),
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

    @registry.register("git_diff", """Shows git diff of changes.

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
                    rel_path = str(validated_path.relative_to(git_root))
                    cmd.append("--")
                    cmd.append(rel_path)
                except Exception as e:
                    return f"❌ Invalid file path: {str(e)}"
            
            # Run git diff
            result = subprocess.run(
                cmd,
                cwd=str(git_root),
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