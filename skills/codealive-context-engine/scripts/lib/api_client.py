"""
CodeAlive API Client
Handles authentication and HTTP requests to the CodeAlive API.
"""

import os
import urllib.parse
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional, Dict, Any, List


CLIENT_VERSION = "skills-v3"

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
        return_headers: bool = False,
        extra_headers: Optional[Dict[str, str]] = None,
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
        if extra_headers:
            headers.update(extra_headers)

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

    def tool(
        self,
        name: str,
        payload: Optional[Dict[str, Any]] = None,
        output_format: str = "agentic",
    ) -> Any:
        """Call a CodeAlive Tool API v3 tool.

        Skills default to backend-rendered agentic output. Use output_format="json"
        for scripts that need the canonical obj envelope.
        """
        clean_payload = {
            key: value
            for key, value in (payload or {}).items()
            if value is not None and value != [] and value != ""
        }
        clean_payload["output_format"] = output_format
        envelope = self._make_request(
            "POST",
            f"/api/tools/{name}",
            body=clean_payload,
            extra_headers={
                "X-CodeAlive-Integration": "skills",
                "X-CodeAlive-Tool": name,
                "X-CodeAlive-Client": CLIENT_VERSION,
            },
        )
        if output_format == "agentic":
            return envelope.get("rendered", "")
        if output_format == "json":
            return envelope.get("obj", {})
        return envelope

    def get_datasources(
        self,
        ready_only: bool = True,
        query: Optional[str] = None,
        output_format: str = "agentic",
    ) -> Any:
        """
        Get available data sources (repositories and workspaces).

        Args:
            ready_only: If True, only return data sources ready for use. If False, return all.
            query: Optional natural-language task/intent (e.g. "add OAuth to checkout"). When
                provided, the backend runs an agentic relevance filter and returns ONLY the data
                sources relevant to that intent, each with a `relevanceReason` explaining why.

        Returns:
            Without query: list of data source objects with id, name, description, type, etc.
            With query: dict {"dataSources": [...], "message": "..."} where `message` says whether
            sources were omitted as non-relevant (and how many of the total) or that relevance
            filtering was unavailable and the FULL list is returned.
        """
        return self.tool(
            "get_data_sources",
            {"ready_only": ready_only, "query": query},
            output_format=output_format,
        )

    def search(
        self,
        query: str,
        data_sources: List[str],
        mode: str = "auto",
        description_detail: str = "short",
        output_format: str = "agentic",
    ) -> Any:
        """Compatibility wrapper for the v3 semantic_search tool."""
        return self.semantic_search(
            query=query,
            data_sources=data_sources,
            output_format=output_format,
        )

    def semantic_search(
        self,
        query: str,
        data_sources: List[str],
        paths: Optional[List[str]] = None,
        extensions: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        exclude_markdown: bool = False,
        output_format: str = "agentic",
    ) -> Any:
        """Search indexed artifacts semantically using Tool API v3."""
        return self.tool(
            "semantic_search",
            {
                "question": query,
                "data_sources": data_sources,
                "paths": paths,
                "extensions": extensions,
                "max_results": max_results,
                "exclude_markdown": exclude_markdown,
            },
            output_format=output_format,
        )

    def grep_search(
        self,
        query: str,
        data_sources: List[str],
        paths: Optional[List[str]] = None,
        extensions: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        regex: bool = False,
        exclude_markdown: bool = False,
        output_format: str = "agentic",
    ) -> Any:
        """Search indexed artifacts by exact text or regex using Tool API v3."""
        return self.tool(
            "grep_search",
            {
                "query": query,
                "data_sources": data_sources,
                "paths": paths,
                "extensions": extensions,
                "max_results": max_results,
                "exclude_markdown": exclude_markdown,
                "regex": regex,
            },
            output_format=output_format,
        )

    def fetch_artifacts(
        self,
        identifiers: List[str],
        data_source: Optional[str] = None,
        output_format: str = "agentic",
    ) -> Any:
        """
        Retrieve full content for code artifacts by their identifiers.

        Use after search() to get the complete source code for results you need to inspect.
        The identifier values come from search results.

        Identifier format: {owner/repo}::{path}::{symbol} (for symbols/chunks)
                           {owner/repo}::{path} (for files)

        Args:
            identifiers: List of artifact identifiers from search results (max 20)
            data_source: Optional data-source Name or Id to disambiguate an identifier that
                exists in more than one data source. Copy the `dataSource.name`/`dataSource.id`
                from a search result. Omit for normal lookups; an ambiguous identifier without
                it returns a 409 listing the candidate data sources.

        Returns:
            Dict with 'artifacts' list. Each artifact has identifier, content,
            contentByteSize, startLine. For function-like artifacts the response
            also contains a `relationships` preview (up to 3 outgoing/incoming
            calls per direction). Use ``get_artifact_relationships()`` to retrieve
            the full list and other relationship profiles.
        """
        return self.tool(
            "fetch_artifacts",
            {"identifiers": identifiers, "data_source": data_source},
            output_format=output_format,
        )

    def get_artifact_relationships(
        self,
        identifier: str,
        profile: str = "callsOnly",
        max_count_per_type: int = 50,
        data_source: Optional[str] = None,
        output_format: str = "agentic",
    ) -> Any:
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
            data_source: Optional data-source Name or Id to disambiguate a source identifier
                that exists in more than one data source. Omit for normal lookups; an ambiguous
                identifier without it returns a 409 listing the candidate data sources.

        Returns:
            Dict with sourceIdentifier, profile, found, and a list of
            ``relationships`` groups. Each group has relationType, totalCount,
            returnedCount, truncated, and an ``items`` list of related artifacts
            (identifier, filePath, startLine, shortSummary).
        """
        profile_map = {
            "callsOnly": "calls_only",
            "inheritanceOnly": "inheritance_only",
            "allRelevant": "all_relevant",
            "referencesOnly": "references_only",
        }
        api_profile = profile_map.get(profile)
        if api_profile is None:
            supported = ", ".join(profile_map.keys())
            raise ValueError(
                f'Unsupported profile "{profile}". Use one of: {supported}'
            )

        return self.tool(
            "get_artifact_relationships",
            {
                "identifier": identifier,
                "profile": api_profile,
                "max_count_per_type": max_count_per_type,
                "data_source": data_source,
            },
            output_format=output_format,
        )

    def get_repository_ontology(
        self,
        data_source: Optional[str] = None,
        output_format: str = "agentic",
    ) -> Any:
        return self.tool(
            "get_repository_ontology",
            {"data_source": data_source},
            output_format=output_format,
        )

    def get_file_tree(
        self,
        data_source: Optional[str] = None,
        path: Optional[str] = None,
        max_depth: Optional[int] = None,
        max_nodes: Optional[int] = None,
        output_depth: Optional[int] = None,
        output_format: str = "agentic",
    ) -> Any:
        return self.tool(
            "get_file_tree",
            {
                "data_source": data_source,
                "path": path,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "output_depth": output_depth,
            },
            output_format=output_format,
        )

    def read_file(
        self,
        path: str,
        data_source: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        output_format: str = "agentic",
    ) -> Any:
        return self.tool(
            "read_file",
            {
                "path": path,
                "data_source": data_source,
                "start_line": start_line,
                "end_line": end_line,
            },
            output_format=output_format,
        )

    def get_artifact_query_schema(
        self,
        entity: Optional[str] = None,
        include_examples: bool = True,
        output_format: str = "agentic",
    ) -> Any:
        return self.tool(
            "get_artifact_query_schema",
            {"entity": entity, "include_examples": include_examples},
            output_format=output_format,
        )

    def query_artifact_metadata(
        self,
        statement: str,
        data_sources: Optional[List[str]] = None,
        output_format: str = "agentic",
    ) -> Any:
        return self.tool(
            "query_artifact_metadata",
            {"statement": statement, "data_sources": data_sources},
            output_format=output_format,
        )

    def chat(
        self,
        question: str,
        data_sources: Optional[List[str]] = None,
        output_format: str = "agentic",
    ) -> Any:
        """Ask stateless CodeAlive chat through Tool API v3."""
        return self.tool(
            "chat",
            {"question": question, "data_sources": data_sources},
            output_format=output_format,
        )


def main():
    """CLI interface for testing the client."""
    if len(sys.argv) < 2:
        print("Usage: python api_client.py <command> [args...]")
        print("Commands:")
        print("  datasources [--all] [--query TASK]")
        print("  search <query> <data_source1> [data_source2...]")
        print("  semantic-search <query> <data_source1> [data_source2...] [--path PATH] [--ext EXT] [--max-results N]")
        print("  grep-search <query> <data_source1> [data_source2...] [--regex] [--path PATH] [--ext EXT] [--max-results N]")
        print("  fetch <identifier1> [identifier2...] [--data-source NAME_OR_ID]")
        print("  relationships <identifier> [--profile callsOnly|inheritanceOnly|allRelevant|referencesOnly] [--max-count N] [--data-source NAME_OR_ID]")
        print("  ontology [data_source]")
        print("  tree [data_source]")
        print("  read-file <path> [data_source]")
        print("  schema")
        print("  metadata <statement> [data_source1] [data_source2...]")
        print("  chat <question> <data_source1> [data_source2...]")
        sys.exit(1)

    client = CodeAliveClient()
    command = sys.argv[1]

    try:
        if command == "datasources":
            ready_only = "--all" not in sys.argv
            query = None
            if "--query" in sys.argv:
                query_index = sys.argv.index("--query")
                if query_index + 1 >= len(sys.argv):
                    print("Usage: datasources [--all] [--query TASK]")
                    sys.exit(1)
                query = sys.argv[query_index + 1]
            result = client.get_datasources(ready_only=ready_only, query=query, output_format="json")
            print(json.dumps(result, indent=2))

        elif command == "search":
            if len(sys.argv) < 4:
                print("Usage: search <query> <data_source1> [data_source2...]")
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
                print("Usage: fetch <identifier1> [identifier2...] [--data-source NAME_OR_ID]")
                sys.exit(1)

            identifiers = []
            data_source = None
            i = 2
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg == "--data-source":
                    # Match the flag first, then require a value — otherwise a trailing
                    # "--data-source" with no value would be silently appended as an identifier.
                    if i + 1 >= len(sys.argv):
                        print("Error: --data-source requires a value.", file=sys.stderr)
                        sys.exit(1)
                    data_source = sys.argv[i + 1]
                    i += 2
                else:
                    identifiers.append(arg)
                    i += 1

            result = client.fetch_artifacts(identifiers, data_source=data_source)
            print(json.dumps(result, indent=2))

        elif command == "relationships":
            if len(sys.argv) < 3:
                print("Usage: relationships <identifier> [--profile PROFILE] [--max-count N]")
                sys.exit(1)

            identifier = sys.argv[2]
            profile = "callsOnly"
            max_count = 50
            data_source = None

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                # Value-bearing flags match on the name first, then require a value, so a trailing
                # flag with no value reports "requires a value" instead of being silently skipped.
                if arg == "--profile":
                    if i + 1 >= len(sys.argv):
                        print("Error: --profile requires a value.", file=sys.stderr)
                        sys.exit(1)
                    profile = sys.argv[i + 1]
                    i += 2
                elif arg == "--max-count":
                    if i + 1 >= len(sys.argv):
                        print("Error: --max-count requires a value.", file=sys.stderr)
                        sys.exit(1)
                    max_count = int(sys.argv[i + 1])
                    i += 2
                elif arg == "--data-source":
                    if i + 1 >= len(sys.argv):
                        print("Error: --data-source requires a value.", file=sys.stderr)
                        sys.exit(1)
                    data_source = sys.argv[i + 1]
                    i += 2
                else:
                    i += 1

            result = client.get_artifact_relationships(
                identifier, profile, max_count, data_source=data_source
            )
            print(json.dumps(result, indent=2))

        elif command == "ontology":
            data_source = sys.argv[2] if len(sys.argv) > 2 else None
            print(client.get_repository_ontology(data_source=data_source))

        elif command == "tree":
            data_source = sys.argv[2] if len(sys.argv) > 2 else None
            print(client.get_file_tree(data_source=data_source))

        elif command == "read-file":
            if len(sys.argv) < 3:
                print("Usage: read-file <path> [data_source]")
                sys.exit(1)
            data_source = sys.argv[3] if len(sys.argv) > 3 else None
            print(client.read_file(sys.argv[2], data_source=data_source))

        elif command == "schema":
            print(client.get_artifact_query_schema())

        elif command == "metadata":
            if len(sys.argv) < 3:
                print("Usage: metadata <statement> [data_source1] [data_source2...]")
                sys.exit(1)
            print(client.query_artifact_metadata(sys.argv[2], sys.argv[3:] or None))

        elif command == "chat":
            if len(sys.argv) < 4:
                print("Usage: chat <question> <data_source1> [data_source2...]")
                sys.exit(1)

            question = sys.argv[2]
            data_sources = []

            i = 3
            while i < len(sys.argv):
                arg = sys.argv[i]
                if arg in {"--conversation-id", "--continue"}:
                    print("Error: chat is stateless in v3; include prior context in the question instead.", file=sys.stderr)
                    sys.exit(1)
                else:
                    data_sources.append(arg)
                    i += 1

            print(client.chat(question, data_sources if data_sources else None))

        else:
            print(f"Unknown command: {command}")
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
