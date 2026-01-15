"""
Web tools plugin.

Provides HTTP/HTTPS fetching capabilities.

Dependencies:
- requests

Description:
Fetches content from URLs for integrating external documentation or resources.
"""

import requests


def register_tools(registry, git_root):
    """Register web-related tools."""
    
    @registry.register("fetch_url", """Fetches content from a URL.

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