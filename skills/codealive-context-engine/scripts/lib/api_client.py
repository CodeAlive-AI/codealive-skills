"""
CodeAlive API Client
Handles authentication and HTTP requests to the CodeAlive API.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List


class CodeAliveClient:
    """Client for interacting with the CodeAlive API."""

    @staticmethod
    def _get_key_from_keychain() -> Optional[str]:
        """Try to read the API key from OS credential store."""
        import platform
        system = platform.system()
        try:
            if system == "Darwin":
                import subprocess
                result = subprocess.run(
                    ["security", "find-generic-password", "-a", os.getenv("USER", ""), "-s", "codealive-api-key", "-w"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            elif system == "Linux":
                import subprocess
                result = subprocess.run(
                    ["secret-tool", "lookup", "service", "codealive-api-key"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            elif system == "Windows":
                return CodeAliveClient._read_windows_credential("codealive-api-key")
        except (FileNotFoundError, Exception):
            pass
        return None

    @staticmethod
    def _read_windows_credential(target_name: str) -> Optional[str]:
        """Read a generic credential from Windows Credential Manager via ctypes."""
        import ctypes
        import ctypes.wintypes

        CRED_TYPE_GENERIC = 1

        class CREDENTIAL(ctypes.Structure):
            """Windows CREDENTIALW structure — layout handled by ctypes automatically."""
            _fields_ = [
                ("Flags", ctypes.wintypes.DWORD),
                ("Type", ctypes.wintypes.DWORD),
                ("TargetName", ctypes.wintypes.LPWSTR),
                ("Comment", ctypes.wintypes.LPWSTR),
                ("LastWritten", ctypes.wintypes.FILETIME),
                ("CredentialBlobSize", ctypes.wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                ("Persist", ctypes.wintypes.DWORD),
                ("AttributeCount", ctypes.wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", ctypes.wintypes.LPWSTR),
                ("UserName", ctypes.wintypes.LPWSTR),
            ]

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.CredReadW.restype = ctypes.wintypes.BOOL
        advapi32.CredReadW.argtypes = [
            ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
            ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIAL))
        ]
        advapi32.CredFree.restype = None
        advapi32.CredFree.argtypes = [ctypes.c_void_p]

        cred_ptr = ctypes.POINTER(CREDENTIAL)()
        if not advapi32.CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr)):
            return None

        try:
            cred = cred_ptr.contents
            if cred.CredentialBlobSize > 0 and cred.CredentialBlob:
                raw = cred.CredentialBlob[:cred.CredentialBlobSize]
                return bytes(raw).decode("utf-16-le")
            return None
        finally:
            advapi32.CredFree(cred_ptr)

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        """
        Initialize the CodeAlive API client.

        Args:
            api_key: CodeAlive API key. Resolution order:
                     1. Explicit api_key parameter
                     2. CODEALIVE_API_KEY environment variable
                     3. macOS Keychain (service: codealive-api-key)
            base_url: Base URL for the API. Defaults to https://app.codealive.ai
        """
        self.api_key = api_key or os.getenv("CODEALIVE_API_KEY") or self._get_key_from_keychain()
        if not self.api_key:
            # Resolve skill directory for setup.py path
            skill_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            setup_path = os.path.join(skill_dir, "setup.py")
            raise ValueError(
                "CodeAlive API key not configured.\n"
                "\n"
                "Run the interactive setup:\n"
                f"  python {setup_path}\n"
                "\n"
                "Or set the key manually:\n"
                "  export CODEALIVE_API_KEY=\"your_key\"\n"
                "\n"
                "Get your API key at: https://app.codealive.ai/settings/api-keys"
            )

        self.base_url = base_url or os.getenv("CODEALIVE_BASE_URL", "https://app.codealive.ai")
        self.timeout = 60

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to the CodeAlive API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: URL query parameters
            body: Request body for POST requests

        Returns:
            Parsed JSON response
        """
        url = f"{self.base_url}{endpoint}"

        # Add query parameters
        if params:
            query_string = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}?{query_string}"

        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = None
        if body:
            data = json.dumps(body).encode("utf-8")

        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        # Make request
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = response.read().decode("utf-8")
                return json.loads(response_data) if response_data else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            try:
                error_data = json.loads(error_body)
                error_msg = error_data.get("message") or error_data.get("error") or error_body
            except json.JSONDecodeError:
                error_msg = error_body

            # Provide actionable messages for common HTTP errors
            if e.code == 401:
                detail = f": {error_msg}" if error_msg.strip() else ""
                raise Exception(
                    f"Authentication failed (401){detail}. "
                    f"Your API key may be invalid or expired. "
                    f"Get a new key at: {self.base_url}/settings/api-keys"
                )
            elif e.code == 403:
                raise Exception(
                    f"Access denied (403): {error_msg}. "
                    f"Your API key may lack permissions for this operation."
                )
            elif e.code == 404:
                raise Exception(f"Not found (404): {error_msg}")
            elif e.code == 429:
                raise Exception(
                    f"Rate limit exceeded (429). Please wait before retrying."
                )
            elif e.code >= 500:
                raise Exception(
                    f"Server error ({e.code}): {error_msg}. "
                    f"The CodeAlive service may be temporarily unavailable."
                )
            else:
                raise Exception(f"API request failed ({e.code}): {error_msg}")
        except urllib.error.URLError as e:
            raise Exception(
                f"Cannot connect to {self.base_url}: {e.reason}. "
                f"Check your network connection and CODEALIVE_BASE_URL setting."
            )

    def get_datasources(self, alive_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get available data sources (repositories and workspaces).

        Args:
            alive_only: If True, only return data sources ready for use. If False, return all.

        Returns:
            List of data source objects with id, name, description, type, etc.
        """
        endpoint = "/api/datasources/alive" if alive_only else "/api/datasources/all"
        return self._make_request("GET", endpoint)

    def search(
        self,
        query: str,
        data_sources: List[str],
        mode: str = "auto",
        include_content: bool = False
    ) -> Dict[str, Any]:
        """
        Search for code using natural language queries.

        Args:
            query: Natural language description of what to find
            data_sources: List of repository or workspace names to search
            mode: Search mode - "auto" (default), "fast", or "deep"
            include_content: Whether to include full file content in results

        Returns:
            Search results with file paths, line numbers, and code snippets
        """
        params = {
            "Query": query,
            "Mode": mode,
            "IncludeContent": str(include_content).lower(),
            "Names": data_sources
        }
        return self._make_request("GET", "/api/search", params=params)

    def chat(
        self,
        question: str,
        data_sources: Optional[List[str]] = None,
        conversation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ask questions about the codebase to an AI consultant.

        Args:
            question: Question about the codebase
            data_sources: List of repository or workspace names to analyze
            conversation_id: ID to continue a previous conversation

        Returns:
            Response with answer and conversation_id for follow-up questions
        """
        body: Dict[str, Any] = {
            "messages": [{"role": "user", "content": question}],
            "stream": True
        }

        if conversation_id:
            body["conversationId"] = conversation_id
        elif data_sources:
            body["names"] = data_sources
        else:
            raise ValueError("Either conversation_id or data_sources must be provided")

        # Note: This is a simplified version. The real implementation would handle streaming.
        # For now, we'll make a non-streaming request.
        body["stream"] = False
        response = self._make_request("POST", "/api/chat/completions", body=body)

        return {
            "answer": response.get("choices", [{}])[0].get("message", {}).get("content", ""),
            "conversation_id": response.get("id"),
            "full_response": response
        }


def main():
    """CLI interface for testing the client."""
    if len(sys.argv) < 2:
        print("Usage: python api_client.py <command> [args...]")
        print("Commands:")
        print("  datasources [--all]")
        print("  search <query> <data_source1> [data_source2...] [--mode auto|fast|deep] [--include-content]")
        print("  chat <question> <data_source1> [data_source2...] [--conversation-id ID]")
        sys.exit(1)

    client = CodeAliveClient()
    command = sys.argv[1]

    try:
        if command == "datasources":
            alive_only = "--all" not in sys.argv
            result = client.get_datasources(alive_only=alive_only)
            print(json.dumps(result, indent=2))

        elif command == "search":
            if len(sys.argv) < 4:
                print("Usage: search <query> <data_source1> [data_source2...] [--mode MODE] [--include-content]")
                sys.exit(1)

            query = sys.argv[2]
            mode = "auto"
            include_content = False
            data_sources = []

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--mode" and i + 1 < len(sys.argv):
                    mode = sys.argv[i + 1]
                    i += 2
                elif arg == "--include-content":
                    include_content = True
                    i += 1
                else:
                    data_sources.append(arg)
                    i += 1

            result = client.search(query, data_sources, mode, include_content)
            print(json.dumps(result, indent=2))

        elif command == "chat":
            if len(sys.argv) < 4:
                print("Usage: chat <question> <data_source1> [data_source2...] [--conversation-id ID]")
                sys.exit(1)

            question = sys.argv[2]
            conversation_id = None
            data_sources = []

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--conversation-id" and i + 1 < len(sys.argv):
                    conversation_id = sys.argv[i + 1]
                    i += 2
                else:
                    data_sources.append(arg)
                    i += 1

            result = client.chat(question, data_sources if data_sources else None, conversation_id)
            print(result["answer"])
            if result.get("conversation_id"):
                print(f"\nConversation ID: {result['conversation_id']}")

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
