"""HTTP transport helpers for the CodeAlive API."""

from __future__ import annotations

import http.client
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _proxy_is_configured_for(url: str) -> bool:
    """Return whether the environment would proxy a request to ``url``."""
    proxies = urllib.request.getproxies()
    if not proxies:
        return False

    parsed = urllib.parse.urlsplit(url)
    if not parsed.hostname:
        return False

    # Do not retry when the request already matches NO_PROXY. In that case the
    # first request was direct and repeating it would not change the route.
    if urllib.request.proxy_bypass(parsed.hostname):
        return False

    scheme = parsed.scheme.lower()
    return bool(proxies.get(scheme) or proxies.get("all"))


def _is_remote_disconnect(error: BaseException) -> bool:
    if isinstance(error, http.client.RemoteDisconnected):
        return True
    reason = getattr(error, "reason", None)
    return isinstance(reason, http.client.RemoteDisconnected)


def _copy_request_without_proxy(request: urllib.request.Request) -> urllib.request.Request:
    """Rebuild a Request after ProxyHandler has attached proxy state to it."""
    direct_request = urllib.request.Request(
        request.full_url,
        data=request.data,
        headers=dict(request.header_items()),
        origin_req_host=request.origin_req_host,
        unverifiable=request.unverifiable,
        method=request.get_method(),
    )
    for key, value in request.unredirected_hdrs.items():
        direct_request.add_unredirected_header(key, value)
    return direct_request


def open_url_with_direct_fallback(request: urllib.request.Request, timeout: float) -> Any:
    """Open a request and retry directly when a proxy drops the connection.

    ``urllib`` correctly honors HTTP(S)_PROXY and NO_PROXY, but some HTTPS
    proxies close the tunnel without returning an HTTP response. In that case
    Python reports ``RemoteDisconnected``. A single direct retry handles this
    failure mode while keeping the configured proxy as the preferred route.
    """
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except (urllib.error.URLError, http.client.RemoteDisconnected) as proxy_error:
        if not _is_remote_disconnect(proxy_error) or not _proxy_is_configured_for(request.full_url):
            raise

        direct_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        direct_request = _copy_request_without_proxy(request)
        try:
            return direct_opener.open(direct_request, timeout=timeout)
        except urllib.error.HTTPError:
            # A direct HTTP response is a valid transport result. Let callers
            # preserve their existing handling for 401/403/4xx responses.
            raise
        except (urllib.error.URLError, http.client.RemoteDisconnected) as direct_error:
            reason = getattr(direct_error, "reason", direct_error)
            raise urllib.error.URLError(
                "Proxy closed the connection without a response; "
                f"direct connection also failed: {reason}"
            ) from direct_error
