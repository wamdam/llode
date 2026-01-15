"""
Document conversion plugin.

Provides tools for converting between document formats and markdown.

Dependencies:
- pandoc (for docx, odt, rtf, html, epub, etc.)
- pdftotext from poppler-utils (for PDF files)

Description:
Converts documents to/from markdown format for easy editing.
Supports PDF, DOCX, ODT, RTF, HTML, EPUB, and more.
"""

import subprocess
import shutil
from pathlib import Path


def check_pandoc_installed():
    """Check if pandoc is installed."""
    return shutil.which("pandoc") is not None


def register_tools(registry, git_root):
    """Register document conversion tools."""
    
    # Access core validation function
    import sys
    parent_module = sys.modules['__main__']
    validate_path = parent_module.validate_path
    
    @registry.register("convert_to_markdown", """Converts a document to markdown format using pandoc or pdftotext.

Parameters:
- path: relative path to the document file

Converts documents to markdown:
- PDF files: Uses pdftotext (from poppler-utils) to extract text
- Other formats (docx, odt, rtf, html, epub, etc.): Uses pandoc

Creates a new file with .md extension (e.g., document.pdf -> document.pdf.md).
Returns the path to the generated markdown file.

Requires pandoc for non-PDF files, and pdftotext for PDF files.

WORKFLOW for non-plaintext documents (docx, odt, rtf, html, epub, pdf):
1. Use convert_to_markdown(path="document.docx") to create document.docx.md
2. Use file_read or file_edit on the .md version
3. Optionally use convert_from_markdown to convert back to original format

The system will automatically suggest conversion when you try to read binary files.""")
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
                f"⚠️  Markdown file already exists: {output_path.relative_to(git_root)}\n"
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
                
                rel_output = output_path.relative_to(git_root)
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
                
                rel_output = output_path.relative_to(git_root)
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

    @registry.register("convert_from_markdown", """Converts a markdown file back to another format using pandoc.

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
            
            rel_output = output_path.relative_to(git_root)
            return (
                f"✓ Successfully converted from markdown:\n"
                f"  Input:  {path} ({markdown_size:,} bytes)\n"
                f"  Output: {rel_output} ({output_size:,} bytes)\n"
            )
            
        except subprocess.TimeoutExpired:
            return "❌ Error: Pandoc conversion timed out after 30 seconds"
        except Exception as e:
            return f"❌ Error during conversion: {str(e)}"