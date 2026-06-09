"""
CodeAlive API Client
Handles authentication and HTTP requests to the CodeAlive API.
"""

import os
import re
import urllib.parse
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List


# 24-character hex Mongo ObjectId. The CodeAlive REST API rejects any other
# shape for conversation_id / message_id with a 400; preflight locally so
# agents get an actionable error before the network round-trip.
_OBJECT_ID_RE = re.compile(r"^[0-9a-fA-F]{24}$")

# Pre-filter scoped candidate count, emitted by the backend only on relevance-filtered
# (query'd) data source listings. Lowercase because _make_request lowercases header
# keys (proxies/origins may change response-header casing; HTTP headers are
# case-insensitive per RFC 9110).
_TOTAL_DATA_SOURCES_HEADER = "x-codealive-total-data-sources"


def relevance_message(datasources: List[Dict[str, Any]], total_header: Optional[str]) -> str:
    """Build the hint accompanying a query'd (relevance-filtered) data source listing.

    The backend guarantees every relevance-selected item carries a non-empty
    ``relevanceReason``, so a NON-EMPTY query'd response where no item has one means
    the filter did not run (fail-open on error, disabled by config, or an older
    backend ignoring ``query``) and the FULL list was returned — the caller must be
    told, instead of mistaking the full dump for a relevant shortlist.

    An EMPTY response is never fail-open output when the total header reports
    available candidates (fail-open returns the full, hence non-empty, list): it is
    the filter's confident-empty verdict — it ran and matched nothing.

    The total header is NOT a filter-success signal: the backend emits it on every
    query'd response, including fail-open.
    """
    shown = len(datasources)
    try:
        total = int(total_header)
    except (TypeError, ValueError):
        # Header absent (TypeError on int(None)) or malformed (ValueError).
        total = None

    if shown == 0:
        if total is not None and total > 0:
            return (
                f"None of the {total} available data sources are relevant to this query. "
                "List without a query to get the full list."
            )
        return "No data sources are available."

    filtered = any(ds.get("relevanceReason") for ds in datasources)
    if not filtered:
        return (
            "Relevance filtering was unavailable for this request (it may have failed or be "
            "disabled), so the FULL unfiltered list of data sources is returned."
        )
    if total is not None and total > shown:
        return (
            f"{shown} of {total} available data sources are relevant to this query; the other "
            f"{total - shown} were omitted. List without a query to get the full list."
        )
    if total is not None:
        return f"All {total} available data sources are relevant to this query."
    return (
        "Only the data sources relevant to this query are shown; non-relevant sources were "
        "omitted. List without a query to get the full list."
    )


def format_codealive_error(status: int, body: Any) -> str:
    """Format a CodeAlive REST API error body into a single human/agent-readable line.

    Reads RFC 9457 (``type``, ``title``, ``detail``, ``errors[field][]``,
    ``instance``, ``requestId``) and the legacy {``message``,
    ``validationErrors``} alias preserved by the server's
    ProblemDetailsCustomizer. Tolerates bytes, str, or anything stringifiable;
    never raises.
    """
    if isinstance(body, bytes):
        body_str = body.decode("utf-8", "replace")
    elif body is None:
        body_str = ""
    else:
        body_str = str(body)

    try:
        d = json.loads(body_str) if body_str else None
    except (ValueError, TypeError):
        d = None

    if not isinstance(d, dict):
        return f"HTTP {status}: {body_str}" if body_str else f"HTTP {status}"

    title = d.get("title") or d.get("message") or f"HTTP {status}"
    detail = d.get("detail") or ""
    parts = [title]
    if detail and detail != title:
        parts.append(f"({detail})")

    structured = d.get("errors") if isinstance(d.get("errors"), dict) else None
    legacy_flat = d.get("validationErrors") or []
    if structured:
        rendered = [
            f"{field}: {msg}"
            for field, msgs in structured.items()
            for msg in (msgs or [])
        ]
    else:
        rendered = [str(x) for x in legacy_flat]
    if rendered:
        parts.append("Details: " + "; ".join(rendered))

    rid = d.get("requestId") or d.get("traceId")
    if rid:
        parts.append(f"requestId={rid}")

    typ = d.get("type")
    if typ and typ != "about:blank":
        parts.append(f"type={typ}")

    return " ".join(parts)


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
                # WSL fallback: read from Windows Credential Manager
                wsl_key = CodeAliveClient._read_wsl_credential("codealive-api-key")
                if wsl_key:
                    return wsl_key
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

    @staticmethod
    def _is_wsl() -> bool:
        """Detect if running inside Windows Subsystem for Linux."""
        try:
            with open("/proc/version", "r") as f:
                return "microsoft" in f.read().lower()
        except OSError:
            return False

    @staticmethod
    def _read_wsl_credential(target_name: str) -> Optional[str]:
        """Read a credential from Windows Credential Manager via powershell.exe (WSL only)."""
        if not CodeAliveClient._is_wsl():
            return None
        import subprocess
        # Use PowerShell with inline C# to call CredReadW — no extra modules needed.
        ps_script = f"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class CredReader {{
    [DllImport("advapi32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    static extern bool CredRead(string target, int type, int flags, out IntPtr cred);
    [DllImport("advapi32.dll")]
    static extern void CredFree(IntPtr cred);
    [StructLayout(LayoutKind.Sequential)]
    struct CREDENTIAL {{
        public int Flags; public int Type;
        [MarshalAs(UnmanagedType.LPWStr)] public string TargetName;
        [MarshalAs(UnmanagedType.LPWStr)] public string Comment;
        public long LastWritten; public int CredentialBlobSize;
        public IntPtr CredentialBlob; public int Persist;
        public int AttributeCount; public IntPtr Attributes;
        [MarshalAs(UnmanagedType.LPWStr)] public string TargetAlias;
        [MarshalAs(UnmanagedType.LPWStr)] public string UserName;
    }}
    public static string Read(string target) {{
        IntPtr ptr;
        if (!CredRead(target, 1, 0, out ptr)) return null;
        try {{
            var c = Marshal.PtrToStructure<CREDENTIAL>(ptr);
            if (c.CredentialBlobSize > 0)
                return Marshal.PtrToStringUni(c.CredentialBlob, c.CredentialBlobSize / 2);
            return null;
        }} finally {{ CredFree(ptr); }}
    }}
}}
'@
[CredReader]::Read('{target_name}')
"""
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, Exception):
            pass
        return None

    @staticmethod
    def _normalize_base_url(base_url: Optional[str]) -> str:
        """Normalize a CodeAlive base URL to the deployment origin."""
        raw = (base_url or "https://app.codealive.ai").strip()
        if not raw:
            raw = "https://app.codealive.ai"

        if "://" not in raw:
            normalized = raw.rstrip("/")
            if normalized.endswith("/api"):
                normalized = normalized[:-4]
            return normalized

        parts = urllib.parse.urlsplit(raw)
        path = parts.path.rstrip("/")
        if path.endswith("/api"):
            path = path[:-4]

        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment)).rstrip("/")

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
            resolved_base_url = self._normalize_base_url(base_url or os.getenv("CODEALIVE_BASE_URL", "https://app.codealive.ai"))
            skill_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            setup_path = os.path.join(skill_dir, "setup.py")
            raise ValueError(
                "CodeAlive API key not configured.\n"
                "\n"
                "Option 1 (recommended): Run the interactive setup:\n"
                f"  python {setup_path}\n"
                "\n"
                "Option 2 (not recommended — key visible in chat history):\n"
                "  Ask the user to paste their API key, then run:\n"
                f"  python {setup_path} --key THE_KEY\n"
                "\n"
                f"Get API key at: {resolved_base_url}/settings/api-keys"
            )

        self.base_url = self._normalize_base_url(base_url or os.getenv("CODEALIVE_BASE_URL", "https://app.codealive.ai"))
        self.timeout = 60

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        return_headers: bool = False
    ) -> Any:
        """
        Make an HTTP request to the CodeAlive API.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: URL query parameters
            body: Request body for POST requests
            return_headers: If True, return (parsed JSON, response headers dict) instead.

        Returns:
            Parsed JSON response, or (parsed JSON, headers) when return_headers is True
        """
        url = f"{self.base_url}{endpoint}"

        # Add query parameters
        if params:
            query_string = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}?{query_string}"

        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, application/problem+json",
        }

        data = None
        if body:
            data = json.dumps(body).encode("utf-8")

        request = urllib.request.Request(url, data=data, headers=headers, method=method)

        # Make request
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_data = response.read().decode("utf-8")
                parsed = json.loads(response_data) if response_data else {}
                if return_headers:
                    # Lowercase keys: header casing is not guaranteed end-to-end
                    # (RFC 9110 §5.1), and a plain dict lookup is case-sensitive.
                    return parsed, {k.lower(): v for k, v in response.headers.items()}
                return parsed
        except urllib.error.HTTPError as e:
            error_body = e.read()
            error_msg = format_codealive_error(e.code, error_body)

            # Provide actionable messages for common HTTP errors. The helper
            # already aggregates RFC 9457 fields + legacy validationErrors,
            # so each branch just adds an outer category prefix.
            if e.code == 400:
                raise Exception(f"Bad request (400): {error_msg}")
            elif e.code == 401:
                raise Exception(
                    f"Authentication failed (401): {error_msg}. "
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
                    f"Rate limit exceeded (429): {error_msg}. "
                    f"Please wait before retrying."
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

    def get_datasources(
        self, alive_only: bool = True, query: Optional[str] = None
    ) -> Any:
        """
        Get available data sources (repositories and workspaces).

        Args:
            alive_only: If True, only return data sources ready for use. If False, return all.
            query: Optional natural-language task/intent (e.g. "add OAuth to checkout"). When
                provided, the backend runs an agentic relevance filter and returns ONLY the data
                sources relevant to that intent, each with a `relevanceReason` explaining why.

        Returns:
            Without query: list of data source objects with id, name, description, type, etc.
            With query: dict {"dataSources": [...], "message": "..."} where `message` says whether
            sources were omitted as non-relevant (and how many of the total) or that relevance
            filtering was unavailable and the FULL list is returned.
        """
        endpoint = "/api/datasources/ready" if alive_only else "/api/datasources/all"
        if not query or not query.strip():
            return self._make_request("GET", endpoint)

        datasources, headers = self._make_request(
            "GET", endpoint, params={"query": query}, return_headers=True
        )
        return {
            "dataSources": datasources,
            "message": relevance_message(datasources, headers.get(_TOTAL_DATA_SOURCES_HEADER)),
        }

    def search(
        self,
        query: str,
        data_sources: List[str],
        mode: str = "auto",
        description_detail: str = "short"
    ) -> Dict[str, Any]:
        """
        Search for code using natural language queries.

        Args:
            query: Natural language description of what to find
            data_sources: List of repository or workspace names to search
            mode: Search mode - "auto" (default), "fast", or "deep"
            description_detail: Detail level for descriptions - "short" (default) or "full"

        Returns:
            Search results with file paths, line numbers, descriptions, and identifiers
        """
        detail_map = {"short": "Short", "full": "Full"}
        params = {
            "Query": query,
            "Mode": mode,
            "IncludeContent": "false",
            "DescriptionDetail": detail_map.get(description_detail.lower(), "Short"),
            "Names": data_sources
        }
        return self._make_request("GET", "/api/search", params=params)

    def semantic_search(
        self,
        query: str,
        data_sources: List[str],
        paths: Optional[List[str]] = None,
        extensions: Optional[List[str]] = None,
        max_results: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Search indexed artifacts semantically using the canonical API."""
        params: Dict[str, Any] = {
            "Query": query,
            "Names": data_sources,
        }
        if paths:
            params["Paths"] = paths
        if extensions:
            params["Extensions"] = extensions
        if max_results is not None:
            params["MaxResults"] = max_results

        return self._make_request("GET", "/api/search/semantic", params=params)

    def grep_search(
        self,
        query: str,
        data_sources: List[str],
        paths: Optional[List[str]] = None,
        extensions: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        regex: bool = False,
    ) -> Dict[str, Any]:
        """Search indexed artifacts by exact text or regex using the canonical API."""
        params: Dict[str, Any] = {
            "Query": query,
            "Names": data_sources,
            "Regex": str(regex).lower(),
        }
        if paths:
            params["Paths"] = paths
        if extensions:
            params["Extensions"] = extensions
        if max_results is not None:
            params["MaxResults"] = max_results

        return self._make_request("GET", "/api/search/grep", params=params)

    def fetch_artifacts(
        self,
        identifiers: List[str],
    ) -> Dict[str, Any]:
        """
        Retrieve full content for code artifacts by their identifiers.

        Use after search() to get the complete source code for results you need to inspect.
        The identifier values come from search results.

        Identifier format: {owner/repo}::{path}::{symbol} (for symbols/chunks)
                           {owner/repo}::{path} (for files)

        Args:
            identifiers: List of artifact identifiers from search results (max 20)

        Returns:
            Dict with 'artifacts' list. Each artifact has identifier, content,
            contentByteSize, startLine. For function-like artifacts the response
            also contains a `relationships` preview (up to 3 outgoing/incoming
            calls per direction). Use ``get_artifact_relationships()`` to retrieve
            the full list and other relationship profiles.
        """
        body: Dict[str, Any] = {"identifiers": identifiers}
        return self._make_request("POST", "/api/search/artifacts", body=body)

    def get_artifact_relationships(
        self,
        identifier: str,
        profile: str = "callsOnly",
        max_count_per_type: int = 50,
    ) -> Dict[str, Any]:
        """
        Retrieve relationship groups for a single artifact by profile.

        Use this to drill down into an artifact's call graph, inheritance
        hierarchy, or symbol references after locating it via search() or
        fetch_artifacts().

        Args:
            identifier: Fully qualified artifact identifier (from search/fetch results).
            profile: Relationship profile to expand. One of:
                     - "callsOnly" (default): outgoing and incoming calls
                     - "inheritanceOnly": ancestors and descendants
                     - "allRelevant": calls + inheritance (4 groups)
                     - "referencesOnly": symbol references
            max_count_per_type: Max related artifacts per relationship type
                                (1–1000, default 50).

        Returns:
            Dict with sourceIdentifier, profile, found, and a list of
            ``relationships`` groups. Each group has relationType, totalCount,
            returnedCount, truncated, and an ``items`` list of related artifacts
            (identifier, filePath, startLine, shortSummary).
        """
        profile_map = {
            "callsOnly": "CallsOnly",
            "inheritanceOnly": "InheritanceOnly",
            "allRelevant": "AllRelevant",
            "referencesOnly": "ReferencesOnly",
        }
        api_profile = profile_map.get(profile)
        if api_profile is None:
            supported = ", ".join(profile_map.keys())
            raise ValueError(
                f'Unsupported profile "{profile}". Use one of: {supported}'
            )

        body: Dict[str, Any] = {
            "identifier": identifier,
            "profile": api_profile,
            "maxCountPerType": max_count_per_type,
        }
        return self._make_request(
            "POST", "/api/search/artifact-relationships", body=body
        )

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
                             (24-character hex Mongo ObjectId)

        Returns:
            Response with ``answer``, ``conversation_id``, ``message_id``,
            and ``full_response``.
        """
        # Preflight: reject GUIDs / random strings before the network round-trip.
        # Pre-Phase-3 servers used to return Guid.NewGuid() as response.id and
        # rejected it on the next turn — this catches that footgun locally.
        if conversation_id and not _OBJECT_ID_RE.match(conversation_id):
            raise ValueError(
                f"conversation_id {conversation_id!r} is not a 24-character hex "
                f"Mongo ObjectId; pass the value from a previous "
                f"response.conversation_id"
            )

        body: Dict[str, Any] = {
            "messages": [{"role": "user", "content": question}],
            "stream": False,
        }

        if conversation_id:
            body["conversationId"] = conversation_id
        elif data_sources:
            body["names"] = data_sources
        else:
            raise ValueError("Either conversation_id or data_sources must be provided")

        response = self._make_request("POST", "/api/chat/completions", body=body)

        # Prefer the documented Phase-3 shape ({content, conversationId, messageId});
        # fall back to the legacy OpenAI-style envelope so this client keeps working
        # against pre-Phase-3 servers during incremental rollout.
        answer = response.get("content")
        if not answer:
            answer = (response.get("choices") or [{}])[0].get("message", {}).get("content", "")

        return {
            "answer": answer,
            "conversation_id": response.get("conversationId") or response.get("id"),
            "message_id": response.get("messageId"),
            "full_response": response,
        }


def main():
    """CLI interface for testing the client."""
    if len(sys.argv) < 2:
        print("Usage: python api_client.py <command> [args...]")
        print("Commands:")
        print("  datasources [--all] [--query TASK]")
        print("  search <query> <data_source1> [data_source2...] [--mode auto|fast|deep] [--description-detail short|full]")
        print("  semantic-search <query> <data_source1> [data_source2...] [--path PATH] [--ext EXT] [--max-results N]")
        print("  grep-search <query> <data_source1> [data_source2...] [--regex] [--path PATH] [--ext EXT] [--max-results N]")
        print("  fetch <identifier1> [identifier2...]")
        print("  relationships <identifier> [--profile callsOnly|inheritanceOnly|allRelevant|referencesOnly] [--max-count N]")
        print("  chat <question> <data_source1> [data_source2...] [--conversation-id ID]")
        sys.exit(1)

    client = CodeAliveClient()
    command = sys.argv[1]

    try:
        if command == "datasources":
            alive_only = "--all" not in sys.argv
            query = None
            if "--query" in sys.argv:
                query_index = sys.argv.index("--query")
                if query_index + 1 >= len(sys.argv):
                    print("Usage: datasources [--all] [--query TASK]")
                    sys.exit(1)
                query = sys.argv[query_index + 1]
            result = client.get_datasources(alive_only=alive_only, query=query)
            print(json.dumps(result, indent=2))

        elif command == "search":
            if len(sys.argv) < 4:
                print("Usage: search <query> <data_source1> [data_source2...] [--mode MODE] [--description-detail short|full]")
                sys.exit(1)

            query = sys.argv[2]
            mode = "auto"
            description_detail = "short"
            data_sources = []

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--mode" and i + 1 < len(sys.argv):
                    mode = sys.argv[i + 1]
                    i += 2
                elif arg == "--description-detail" and i + 1 < len(sys.argv):
                    description_detail = sys.argv[i + 1]
                    i += 2
                else:
                    data_sources.append(arg)
                    i += 1

            result = client.search(query, data_sources, mode, description_detail)
            print(json.dumps(result, indent=2))

        elif command == "semantic-search":
            if len(sys.argv) < 4:
                print("Usage: semantic-search <query> <data_source1> [data_source2...] [--path PATH] [--ext EXT] [--max-results N]")
                sys.exit(1)

            query = sys.argv[2]
            data_sources = []
            paths = []
            extensions = []
            max_results = None

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--path" and i + 1 < len(sys.argv):
                    paths.append(sys.argv[i + 1])
                    i += 2
                elif arg == "--ext" and i + 1 < len(sys.argv):
                    extensions.append(sys.argv[i + 1])
                    i += 2
                elif arg == "--max-results" and i + 1 < len(sys.argv):
                    max_results = int(sys.argv[i + 1])
                    i += 2
                else:
                    data_sources.append(arg)
                    i += 1

            result = client.semantic_search(
                query,
                data_sources,
                paths=paths or None,
                extensions=extensions or None,
                max_results=max_results,
            )
            print(json.dumps(result, indent=2))

        elif command == "grep-search":
            if len(sys.argv) < 4:
                print("Usage: grep-search <query> <data_source1> [data_source2...] [--regex] [--path PATH] [--ext EXT] [--max-results N]")
                sys.exit(1)

            query = sys.argv[2]
            data_sources = []
            paths = []
            extensions = []
            max_results = None
            regex = False

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--regex":
                    regex = True
                    i += 1
                elif arg == "--path" and i + 1 < len(sys.argv):
                    paths.append(sys.argv[i + 1])
                    i += 2
                elif arg == "--ext" and i + 1 < len(sys.argv):
                    extensions.append(sys.argv[i + 1])
                    i += 2
                elif arg == "--max-results" and i + 1 < len(sys.argv):
                    max_results = int(sys.argv[i + 1])
                    i += 2
                else:
                    data_sources.append(arg)
                    i += 1

            result = client.grep_search(
                query,
                data_sources,
                paths=paths or None,
                extensions=extensions or None,
                max_results=max_results,
                regex=regex,
            )
            print(json.dumps(result, indent=2))

        elif command == "fetch":
            if len(sys.argv) < 3:
                print("Usage: fetch <identifier1> [identifier2...]")
                sys.exit(1)

            identifiers = sys.argv[2:]

            result = client.fetch_artifacts(identifiers)
            print(json.dumps(result, indent=2))

        elif command == "relationships":
            if len(sys.argv) < 3:
                print("Usage: relationships <identifier> [--profile PROFILE] [--max-count N]")
                sys.exit(1)

            identifier = sys.argv[2]
            profile = "callsOnly"
            max_count = 50

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--profile" and i + 1 < len(sys.argv):
                    profile = sys.argv[i + 1]
                    i += 2
                elif arg == "--max-count" and i + 1 < len(sys.argv):
                    max_count = int(sys.argv[i + 1])
                    i += 2
                else:
                    i += 1

            result = client.get_artifact_relationships(identifier, profile, max_count)
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
