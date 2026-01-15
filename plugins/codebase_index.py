"""
Codebase indexing and semantic search plugin.

Dependencies:
- None (uses Python's built-in ast module)
- tree-sitter (optional, for multi-language support in future)

Description:
Provides semantic understanding of code structure, symbol search,
and dependency analysis. Currently supports Python with plans for
multi-language support.
"""

import sqlite3
import ast
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import json


class CodeIndexer:
    """Manages semantic code indexing using SQLite."""
    
    def __init__(self, git_root: Path):
        self.git_root = git_root
        self.index_dir = git_root / ".llode"
        self.db_path = self.index_dir / "index.db"
        self._ensure_db()
    
    def _ensure_db(self):
        """Create database and tables if they don't exist."""
        self.index_dir.mkdir(exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE,
                language TEXT,
                mtime REAL,
                lines INTEGER,
                size INTEGER
            )
        """)
        
        # Symbols table (functions, classes, variables)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY,
                file_id INTEGER,
                name TEXT,
                type TEXT,
                line_start INTEGER,
                line_end INTEGER,
                signature TEXT,
                docstring TEXT,
                parent_symbol TEXT,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """)
        
        # Imports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY,
                file_id INTEGER,
                imported_path TEXT,
                imported_symbol TEXT,
                alias TEXT,
                line_number INTEGER,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """)
        
        # References table (where symbols are used)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS references (
                id INTEGER PRIMARY KEY,
                file_id INTEGER,
                symbol_name TEXT,
                line_number INTEGER,
                context TEXT,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_imports_path ON imports(imported_path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_references_symbol ON references(symbol_name)")
        
        conn.commit()
        conn.close()
    
    def get_file_mtime(self, path: str) -> Optional[float]:
        """Get stored modification time for a file."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT mtime FROM files WHERE path = ?", (path,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def needs_indexing(self, path: Path) -> bool:
        """Check if a file needs to be (re)indexed."""
        rel_path = str(path.relative_to(self.git_root))
        db_mtime = self.get_file_mtime(rel_path)
        
        if db_mtime is None:
            return True
        
        disk_mtime = path.stat().st_mtime
        return disk_mtime > db_mtime
    
    def index_python_file(self, path: Path):
        """Index a Python file using AST."""
        rel_path = str(path.relative_to(self.git_root))
        
        try:
            content = path.read_text()
            tree = ast.parse(content, filename=str(path))
        except Exception as e:
            # Can't parse, skip
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Remove old data for this file
        cursor.execute("DELETE FROM files WHERE path = ?", (rel_path,))
        
        # Insert file record
        lines = content.count('\n') + 1
        size = len(content)
        mtime = path.stat().st_mtime
        
        cursor.execute("""
            INSERT INTO files (path, language, mtime, lines, size)
            VALUES (?, ?, ?, ?, ?)
        """, (rel_path, "python", mtime, lines, size))
        
        file_id = cursor.lastrowid
        
        # Extract symbols
        extractor = PythonSymbolExtractor()
        extractor.visit(tree)
        
        # Insert symbols
        for symbol in extractor.symbols:
            cursor.execute("""
                INSERT INTO symbols (file_id, name, type, line_start, line_end, signature, docstring, parent_symbol)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (file_id, symbol['name'], symbol['type'], symbol['line_start'], 
                  symbol['line_end'], symbol.get('signature'), symbol.get('docstring'),
                  symbol.get('parent')))
        
        # Insert imports
        for imp in extractor.imports:
            cursor.execute("""
                INSERT INTO imports (file_id, imported_path, imported_symbol, alias, line_number)
                VALUES (?, ?, ?, ?, ?)
            """, (file_id, imp.get('imported_path'), imp.get('imported_symbol'),
                  imp.get('alias'), imp['line_number']))
        
        # Insert references
        for ref in extractor.references:
            cursor.execute("""
                INSERT INTO references (file_id, symbol_name, line_number, context)
                VALUES (?, ?, ?, ?)
            """, (file_id, ref['symbol_name'], ref['line_number'], ref.get('context', '')))
        
        conn.commit()
        conn.close()
    
    def index_file(self, path: Path):
        """Index a file based on its language."""
        if path.suffix == '.py':
            self.index_python_file(path)
        # Future: add support for other languages
    
    def get_stats(self) -> Dict[str, Any]:
        """Get indexing statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM symbols")
        symbol_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT language, COUNT(*) FROM files GROUP BY language")
        by_language = dict(cursor.fetchall())
        
        cursor.execute("SELECT type, COUNT(*) FROM symbols GROUP BY type")
        by_type = dict(cursor.fetchall())
        
        conn.close()
        
        return {
            'files': file_count,
            'symbols': symbol_count,
            'by_language': by_language,
            'by_type': by_type
        }


class PythonSymbolExtractor(ast.NodeVisitor):
    """Extract symbols, imports, and references from Python AST."""
    
    def __init__(self):
        self.symbols = []
        self.imports = []
        self.references = []
        self.current_class = None
    
    def visit_FunctionDef(self, node):
        signature = self._get_signature(node)
        docstring = ast.get_docstring(node)
        
        self.symbols.append({
            'name': node.name,
            'type': 'method' if self.current_class else 'function',
            'line_start': node.lineno,
            'line_end': node.end_lineno,
            'signature': signature,
            'docstring': docstring,
            'parent': self.current_class
        })
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node):
        # Treat async functions same as regular functions
        self.visit_FunctionDef(node)
    
    def visit_ClassDef(self, node):
        docstring = ast.get_docstring(node)
        
        self.symbols.append({
            'name': node.name,
            'type': 'class',
            'line_start': node.lineno,
            'line_end': node.end_lineno,
            'docstring': docstring,
            'parent': None
        })
        
        # Visit class body with class context
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class
    
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({
                'imported_path': alias.name,
                'imported_symbol': None,
                'alias': alias.asname,
                'line_number': node.lineno
            })
    
    def visit_ImportFrom(self, node):
        module = node.module or ''
        for alias in node.names:
            self.imports.append({
                'imported_path': module,
                'imported_symbol': alias.name,
                'alias': alias.asname,
                'line_number': node.lineno
            })
    
    def visit_Name(self, node):
        # Track symbol references (when reading a name)
        if isinstance(node.ctx, ast.Load):
            self.references.append({
                'symbol_name': node.id,
                'line_number': node.lineno,
                'context': ''  # Could extract surrounding code if needed
            })
        self.generic_visit(node)
    
    def _get_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature as string."""
        args = []
        
        # Regular arguments
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)
        
        # *args
        if node.args.vararg:
            arg_str = f"*{node.args.vararg.arg}"
            if node.args.vararg.annotation:
                arg_str += f": {ast.unparse(node.args.vararg.annotation)}"
            args.append(arg_str)
        
        # **kwargs
        if node.args.kwarg:
            arg_str = f"**{node.args.kwarg.arg}"
            if node.args.kwarg.annotation:
                arg_str += f": {ast.unparse(node.args.kwarg.annotation)}"
            args.append(arg_str)
        
        signature = f"{node.name}({', '.join(args)})"
        
        # Add return type if present
        if node.returns:
            signature += f" -> {ast.unparse(node.returns)}"
        
        return signature


def register_tools(registry, git_root):
    """Register codebase indexing tools with llode."""
    
    indexer = CodeIndexer(git_root)
    
    @registry.register("index_codebase", """Builds or updates semantic index of the codebase.

Parameters:
- force_rebuild: rebuild entire index from scratch (default: false)
- path_pattern: only index files matching pattern (default: *.py)

Analyzes Python files to extract functions, classes, imports, and references.
Stores information in SQLite database for fast semantic search.
Only re-indexes files that have changed since last indexing.

Returns summary of indexing results.""")
    def index_codebase(force_rebuild: str = "false", path_pattern: str = "*.py"):
        """Build or update the codebase index."""
        from pathlib import Path
        import fnmatch
        
        # Access injected context functions
        # These are set by PluginManager.set_context() in main
        import sys
        current_module = sys.modules[__name__]
        get_gitignore_spec = getattr(current_module, 'get_gitignore_spec', None)
        walk_files = getattr(current_module, 'walk_files', None)
        
        if not get_gitignore_spec or not walk_files:
            return "Error: Plugin context not properly initialized. Required functions not available."
        
        force = force_rebuild.lower() == "true"
        
        if force:
            # Remove existing database
            if indexer.db_path.exists():
                indexer.db_path.unlink()
            indexer._ensure_db()
        
        # Get all files
        gitignore_spec = get_gitignore_spec()
        all_files = walk_files(gitignore_spec)
        
        # Filter by pattern
        matching_files = [f for f in all_files if fnmatch.fnmatch(str(f), path_pattern)]
        
        indexed = 0
        skipped = 0
        errors = []
        
        for file_path in matching_files:
            full_path = git_root / file_path
            
            try:
                if force or indexer.needs_indexing(full_path):
                    indexer.index_file(full_path)
                    indexed += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")
        
        # Get statistics
        stats = indexer.get_stats()
        
        result = [
            f"✓ Indexing complete:",
            f"  Files indexed: {indexed}",
            f"  Files skipped (up-to-date): {skipped}",
            f"  Total in database: {stats['files']} files, {stats['symbols']} symbols"
        ]
        
        if stats['by_language']:
            result.append(f"  Languages: {', '.join(f'{k}({v})' for k, v in stats['by_language'].items())}")
        
        if stats['by_type']:
            result.append(f"  Symbols: {', '.join(f'{k}({v})' for k, v in stats['by_type'].items())}")
        
        if errors:
            result.append(f"\n⚠️  Errors ({len(errors)}):")
            for error in errors[:5]:  # Show first 5 errors
                result.append(f"  {error}")
            if len(errors) > 5:
                result.append(f"  ... and {len(errors) - 5} more")
        
        return '\n'.join(result)
    
    @registry.register("find_symbol", """Finds where a symbol is defined or used.

Parameters:
- symbol_name: name to search for (required)
- search_type: definition|references|all (default: all)
- limit: maximum results to return (default: 50)

Searches the indexed codebase for symbol definitions and/or usage.
Much faster and more accurate than text search.

Returns locations with file paths, line numbers, and context.""")
    def find_symbol(symbol_name: str, search_type: str = "all", limit: str = "50"):
        """Find symbol definitions and/or references."""
        if not indexer.db_path.exists():
            return "❌ Index not found. Run index_codebase() first."
        
        max_results = int(limit)
        conn = sqlite3.connect(indexer.db_path)
        cursor = conn.cursor()
        
        results = []
        
        # Find definitions
        if search_type in ("definition", "all"):
            cursor.execute("""
                SELECT f.path, s.type, s.line_start, s.signature, s.docstring, s.parent_symbol
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE s.name = ?
                ORDER BY f.path, s.line_start
                LIMIT ?
            """, (symbol_name, max_results))
            
            definitions = cursor.fetchall()
            
            if definitions:
                results.append(f"📍 Definitions ({len(definitions)}):")
                for path, sym_type, line, signature, docstring, parent in definitions:
                    location = f"{path}:{line}"
                    if parent:
                        location += f" (in {parent})"
                    results.append(f"  {location}")
                    if signature:
                        results.append(f"    {signature}")
                    if docstring:
                        first_line = docstring.split('\n')[0][:60]
                        results.append(f"    \"{first_line}...\"")
        
        # Find references
        if search_type in ("references", "all"):
            cursor.execute("""
                SELECT f.path, r.line_number
                FROM references r
                JOIN files f ON r.file_id = f.id
                WHERE r.symbol_name = ?
                ORDER BY f.path, r.line_number
                LIMIT ?
            """, (symbol_name, max_results))
            
            references = cursor.fetchall()
            
            if references:
                # Group by file
                by_file = {}
                for path, line in references:
                    if path not in by_file:
                        by_file[path] = []
                    by_file[path].append(line)
                
                results.append(f"\n🔗 References ({len(references)}):")
                for path, lines in sorted(by_file.items()):
                    line_ranges = []
                    start = lines[0]
                    end = lines[0]
                    
                    for line in lines[1:]:
                        if line == end + 1:
                            end = line
                        else:
                            if start == end:
                                line_ranges.append(str(start))
                            else:
                                line_ranges.append(f"{start}-{end}")
                            start = end = line
                    
                    if start == end:
                        line_ranges.append(str(start))
                    else:
                        line_ranges.append(f"{start}-{end}")
                    
                    results.append(f"  {path}: lines {', '.join(line_ranges)}")
        
        conn.close()
        
        if not results:
            return f"❌ No results found for symbol: {symbol_name}"
        
        return '\n'.join(results)
    
    @registry.register("analyze_dependencies", """Analyzes import dependencies for a file.

Parameters:
- path: file path to analyze (required)
- direction: imports|imported_by|both (default: both)

Shows what modules/symbols a file imports, and optionally what files import from it.

Returns dependency information.""")
    def analyze_dependencies(path: str, direction: str = "both"):
        """Analyze file dependencies."""
        if not indexer.db_path.exists():
            return "❌ Index not found. Run index_codebase() first."
        
        # Normalize path
        try:
            from pathlib import Path
            import sys
            current_module = sys.modules[__name__]
            validate_path = getattr(current_module, 'validate_path', None)
            
            if not validate_path:
                return "Error: Plugin context not properly initialized. validate_path not available."
            
            full_path = validate_path(path)
            rel_path = str(full_path.relative_to(git_root))
        except Exception as e:
            return f"❌ Invalid path: {e}"
        
        conn = sqlite3.connect(indexer.db_path)
        cursor = conn.cursor()
        
        results = []
        
        # Get file ID
        cursor.execute("SELECT id FROM files WHERE path = ?", (rel_path,))
        file_record = cursor.fetchone()
        
        if not file_record:
            conn.close()
            return f"❌ File not in index: {path}"
        
        file_id = file_record[0]
        
        # Show imports (what this file uses)
        if direction in ("imports", "both"):
            cursor.execute("""
                SELECT imported_path, imported_symbol, alias, line_number
                FROM imports
                WHERE file_id = ?
                ORDER BY line_number
            """, (file_id,))
            
            imports = cursor.fetchall()
            
            if imports:
                results.append(f"📥 Imports ({len(imports)}):")
                for imp_path, imp_symbol, alias, line in imports:
                    if imp_symbol:
                        display = f"from {imp_path} import {imp_symbol}"
                        if alias:
                            display += f" as {alias}"
                    else:
                        display = f"import {imp_path}"
                        if alias:
                            display += f" as {alias}"
                    results.append(f"  Line {line}: {display}")
        
        # Show what imports this file
        if direction in ("imported_by", "both"):
            # This is trickier - need to find files that import from this module
            # Extract module name from path
            module_name = rel_path.replace('.py', '').replace('/', '.')
            
            cursor.execute("""
                SELECT DISTINCT f.path, i.line_number
                FROM imports i
                JOIN files f ON i.file_id = f.id
                WHERE i.imported_path LIKE ? OR i.imported_path LIKE ?
                ORDER BY f.path
            """, (f"%{module_name}%", f"%.{path.split('/')[-1].replace('.py', '')}"))
            
            imported_by = cursor.fetchall()
            
            if imported_by:
                results.append(f"\n📤 Imported by ({len(imported_by)}):")
                for imp_path, line in imported_by:
                    results.append(f"  {imp_path}:{line}")
        
        conn.close()
        
        if not results:
            return f"No dependency information found for: {path}"
        
        return '\n'.join(results)
    
    @registry.register("list_symbols", """Lists all symbols in a file or matching a pattern.

Parameters:
- path: file path to list symbols from (optional)
- symbol_pattern: pattern to match symbol names (optional, supports * wildcard)
- symbol_type: filter by type: function|class|method|all (default: all)
- limit: maximum results (default: 100)

Lists functions, classes, and methods with their signatures.

Returns symbol listing with locations.""")
    def list_symbols(path: str = "", symbol_pattern: str = "*", symbol_type: str = "all", limit: str = "100"):
        """List symbols from index."""
        if not indexer.db_path.exists():
            return "❌ Index not found. Run index_codebase() first."
        
        max_results = int(limit)
        conn = sqlite3.connect(indexer.db_path)
        cursor = conn.cursor()
        
        query_parts = ["""
            SELECT f.path, s.name, s.type, s.line_start, s.signature, s.parent_symbol
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE 1=1
        """]
        params = []
        
        # Filter by file path
        if path:
            try:
                from pathlib import Path
                import sys
                current_module = sys.modules[__name__]
                validate_path = getattr(current_module, 'validate_path', None)
                
                if validate_path:
                    full_path = validate_path(path)
                    rel_path = str(full_path.relative_to(git_root))
                    query_parts.append("AND f.path = ?")
                    params.append(rel_path)
            except:
                pass
        
        # Filter by symbol name pattern
        if symbol_pattern != "*":
            sql_pattern = symbol_pattern.replace('*', '%')
            query_parts.append("AND s.name LIKE ?")
            params.append(sql_pattern)
        
        # Filter by symbol type
        if symbol_type != "all":
            query_parts.append("AND s.type = ?")
            params.append(symbol_type)
        
        query_parts.append("ORDER BY f.path, s.line_start LIMIT ?")
        params.append(max_results)
        
        cursor.execute(' '.join(query_parts), params)
        symbols = cursor.fetchall()
        conn.close()
        
        if not symbols:
            return "No symbols found matching criteria"
        
        results = [f"📚 Symbols ({len(symbols)}):"]
        current_file = None
        
        for file_path, name, sym_type, line, signature, parent in symbols:
            if file_path != current_file:
                results.append(f"\n  {file_path}:")
                current_file = file_path
            
            location = f"    Line {line}: "
            if parent:
                location += f"{parent}."
            location += name
            
            if signature:
                location += f" → {signature}"
            else:
                location += f" ({sym_type})"
            
            results.append(location)
        
        return '\n'.join(results)