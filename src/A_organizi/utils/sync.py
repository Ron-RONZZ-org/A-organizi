"""Sync utilities for CalDAV calendar synchronization."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from threading import Lock, Thread
from typing import Any

try:
    import keyring
except ImportError:
    keyring = None  # type: ignore

from A import error, info

from A_organizi.data.storage import get_db

_SERVICE_NAME = "A.kalendaro"
_worker_thread: Thread | None = None
_worker_lock = Lock()


# ──────────────────────────────────────────────────────────────────────────────
# HTTP client functions
# ──────────────────────────────────────────────────────────────────────────────


def remote_http_url(url: str) -> str:
    """Convert caldav:// URL to https://.

    Args:
        url: A caldav:// or http(s):// URL.

    Returns:
        The equivalent https:// URL.
    """
    low = url.strip().lower()
    if low.startswith("caldav://"):
        return "https://" + low[9:]
    if low.startswith("caldavs://"):
        return "https://" + low[10:]
    return url.strip()


def http_fetch_text(
    url: str,
    username: str,
    password: str,
    method: str = "GET",
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Fetch URL with HTTP Basic auth.

    Args:
        url: The URL to fetch.
        username: Username for Basic auth.
        password: Password for Basic auth.
        method: HTTP method (GET, POST, etc.).
        body: Optional request body.
        headers: Additional headers.

    Returns:
        Tuple of (status_code, response_body).
    """
    import base64
    import urllib.request

    https_url = remote_http_url(url)
    req = urllib.request.Request(https_url, data=body.encode() if body else None)
    req.get_method = lambda: method

    # Basic auth header
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    req.add_header("Authorization", f"Basic {encoded}")

    # Default headers
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    req.add_header("Accept", "text/html, application/xml, */*")

    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            text = resp.read().decode("utf-8")
            return status, text
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8") if e.fp else ""
    except urllib.error.URLError as e:
        return 0, str(e.reason)


def fetch_remote_calendar_payloads(
    url: str,
    username: str,
    password: str,
) -> list[str]:
    """Fetch calendar events via CalDAV REPORT.

    Args:
        url: Calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.

    Returns:
        List of ICS event payloads (text/calendar bodies).
    """
    # CalDAV REPORT request for all events
    report_body = """<?xml version="1.0"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <c:calendar-data/>
  </d:prop>
  <c:filter>
    <c:comp-filter name="VCALENDAR">
      <c:comp-filter name="VEVENT">
      </c:comp-filter>
    </c:comp-filter>
  </c:filter>
</c:calendar-query>"""

    headers = {
        "Content-Type": 'application/xml; charset="utf-8"',
        "Depth": "1",
    }

    status, text = http_fetch_text(
        url, username, password, "REPORT", report_body, headers
    )

    if status == 207:  # Multi-status
        # Parse multi-status response to extract calendar-data elements
        payloads = _parse_multistatus(text)
        return payloads
    elif status == 404:
        return []
    else:
        raise RuntimeError(f"CalDAV fetch failed: {status}")


def _parse_multistatus(text: str) -> list[str]:
    """Parse CalDAV multistatus response.

    Args:
        text: Raw XML response.

    Returns:
        List of calendar-data contents.
    """
    import re

    payloads: list[str] = []
    pattern = r"<c:calendar-data>(.*?)</c:calendar-data>"
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    for match in matches:
        # Decode HTML entities if needed
        decoded = (
            match.replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )
        payloads.append(decoded)
    return payloads


# ──────────────────────────────────────────────────────────────────────────────
# Sync queue
# ──────────────────────────────────────────────────────────────────────────────


def queue_sync(
    con,
    calendar_uuid: str,
    operation: str,
    payload: dict[str, Any],
) -> None:
    """Enqueue a sync operation.

    Args:
        con: Database connection (from transaction()).
        calendar_uuid: Calendar UUID.
        operation: Operation type (pull, push).
        payload: Operation payload (JSON-serializable).
    """
    now = datetime.now().isoformat()
    job_id = uuid.uuid4().hex[:12]
    con.execute(
        """INSERT INTO sync_queue
           (id, calendar_uuid, operacio, payload, stato, eraro, kreita_je, modifita_je)
           VALUES (?, ?, ?, ?, 'pending', '', ?, ?)""",
        (job_id, calendar_uuid, operation, json.dumps(payload), now, now),
    )


def sync_worker() -> None:
    """Background worker that processes sync jobs."""
    while True:
        db = get_db()
        # Get pending job
        job = db.execute_one(
            "SELECT * FROM sync_queue WHERE stato = 'pending' ORDER BY kreita_je LIMIT 1"
        )
        if not job:
            import time
            time.sleep(5)
            continue

        job_id = job["id"]
        cal_uuid = job["calendar_uuid"]
        operacio = job["operacio"]
        payload = json.loads(job["payload"])

        # Update status to running
        db.execute(
            "UPDATE sync_queue SET stato = 'running' WHERE id = ?", (job_id,)
        )

        try:
            # Get calendar credentials
            cal = db.execute_one(
                "SELECT url, username FROM kalendaroj WHERE uuid = ?", (cal_uuid,)
            )
            if not cal:
                raise ValueError(f"Calendar not found: {cal_uuid}")

            url = cal["url"]
            username = cal["username"]
            password = get_password(cal_uuid)

            if operacio == "pull":
                # Pull events from remote
                events = fetch_remote_calendar_payloads(url, username, password)
                # TODO: Merge events into local database
                info(f"[sync] Pulled {len(events)} events from {cal_uuid}")
            elif operacio == "push":
                # Push event changes to remote CalDAV server
                sub_op = payload.get("operation", "")
                event_uuid = payload.get("event_uuid", "")
                event_data = payload.get("event_data")
                if not event_uuid:
                    raise ValueError("Push job missing event_uuid")

                if sub_op == "delete":
                    # Use stored event_data; event may already be gone from local DB
                    delete_event_from_remote(url, username, password, event_uuid)
                    info(f"[sync] Deleted {event_uuid[:8]} from {cal_uuid[:8]}")
                else:
                    # Re-read from DB to get latest data (catches subsequent edits)
                    event = db.execute_one(
                        "SELECT * FROM eventoj WHERE uuid = ?", (event_uuid,)
                    )
                    if event:
                        from A_organizi.utils.ics import events_to_ics
                        ics_payload = events_to_ics([dict(event)])
                        push_event_to_remote(url, username, password, ics_payload, event_uuid)
                        info(f"[sync] Pushed {event_uuid[:8]} ({sub_op}) to {cal_uuid[:8]}")
                    else:
                        # Event deleted before push ran — try DELETE on remote
                        delete_event_from_remote(url, username, password, event_uuid)
                        info(f"[sync] Event {event_uuid[:8]} gone locally, deleted remotely")
            else:
                raise ValueError(f"Unknown operation: {operacio}")

            # Mark completed
            db.execute(
                "UPDATE sync_queue SET stato = 'completed' WHERE id = ?", (job_id,)
            )

        except Exception as exc:
            db.execute(
                "UPDATE sync_queue SET stato = 'failed', eraro = ? WHERE id = ?",
                (str(exc), job_id),
            )


# ──────────────────────────────────────────────────────────────────────────────
# CalDAV push helpers
# ──────────────────────────────────────────────────────────────────────────────


def push_event_to_remote(
    url: str,
    username: str,
    password: str,
    ics_payload: str,
    event_uuid: str,
) -> int:
    """PUT an ICS event to the remote CalDAV server.

    Args:
        url: Base calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.
        ics_payload: Full ICS text (VCALENDAR wrapper).
        event_uuid: Event UUID used as the resource name.

    Returns:
        HTTP status code (200, 201, or 204 on success).

    Raises:
        RuntimeError: If the server returns an unexpected status.
    """
    put_url = url.rstrip("/") + f"/{event_uuid}.ics"
    headers = {
        "Content-Type": "text/calendar; charset=utf-8",
    }
    status, _ = http_fetch_text(
        put_url, username, password, "PUT", ics_payload, headers
    )
    if status not in (200, 201, 204):
        raise RuntimeError(f"CalDAV PUT failed: HTTP {status}")
    return status


def delete_event_from_remote(
    url: str,
    username: str,
    password: str,
    event_uuid: str,
) -> int:
    """DELETE an event from the remote CalDAV server.

    Args:
        url: Base calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.
        event_uuid: Event UUID used as the resource name.

    Returns:
        HTTP status code (200 or 204 on success; 404 is accepted as "already gone").

    Raises:
        RuntimeError: If the server returns an unexpected status.
    """
    delete_url = url.rstrip("/") + f"/{event_uuid}.ics"
    status, _ = http_fetch_text(
        delete_url, username, password, "DELETE"
    )
    if status not in (200, 204, 404):
        raise RuntimeError(f"CalDAV DELETE failed: HTTP {status}")
    return status


def start_sync_worker() -> None:
    """Start the background sync worker (thread-safe lazy init)."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = Thread(target=sync_worker, daemon=True)
            _worker_thread.start()


# ──────────────────────────────────────────────────────────────────────────────
# Sync queue queries
# ──────────────────────────────────────────────────────────────────────────────


def list_sync_queue(
    con,
    stato: str | None = None,
    calendar_uuid: str | None = None,
) -> list[dict[str, str]]:
    """List sync queue entries, optionally filtered.

    Args:
        con: Database connection (from transaction() or service.db).
        stato: Optional status filter (pending, running, completed, failed).
        calendar_uuid: Optional calendar UUID filter.

    Returns:
        List of sync_queue row dicts, newest first.
    """
    query = "SELECT * FROM sync_queue WHERE 1=1"
    params: list[str] = []
    if stato:
        query += " AND stato = ?"
        params.append(stato)
    if calendar_uuid:
        query += " AND calendar_uuid = ?"
        params.append(calendar_uuid)
    query += " ORDER BY kreita_je DESC"
    return con.execute(query, tuple(params))


# ──────────────────────────────────────────────────────────────────────────────
# Password management
# ──────────────────────────────────────────────────────────────────────────────


def set_password(calendar_uuid: str, password: str) -> None:
    """Store password in system keyring.

    Args:
        calendar_uuid: Calendar UUID.
        password: Password to store.

    Raises:
        RuntimeError: If keyring is unavailable and install was declined.
    """
    global keyring
    if keyring is None:
        from A.utils.deps import ensure_dependency

        try:
            ensure_dependency("keyring", "keyring")
            import keyring as kr
            keyring = kr
        except ImportError as exc:
            raise RuntimeError("keyring library not installed") from exc
    keyring.set_password(_SERVICE_NAME, calendar_uuid, password)


def get_password(calendar_uuid: str) -> str | None:
    """Retrieve password from system keyring.

    Args:
        calendar_uuid: Calendar UUID.

    Returns:
        Password string, or None if not found.
    """
    if keyring is None:
        return None
    return keyring.get_password(_SERVICE_NAME, calendar_uuid)


def delete_password(calendar_uuid: str) -> None:
    """Delete password from system keyring.

    Args:
        calendar_uuid: Calendar UUID.
    """
    if keyring is None:
        return
    keyring.delete_password(_SERVICE_NAME, calendar_uuid)


def probe_calendar_config(
    url: str,
    username: str,
    password: str,
) -> dict[str, str]:
    """Probe remote calendar configuration.

    Validates:
    - URL is accessible
    - Credentials work
    - Fetches initial event count

    Args:
        url: Calendar URL (caldav:// or https://).
        username: Username for Basic auth.
        password: Password for Basic auth.

    Returns:
        Dict with 'count' (event count) and 'description'.

    Raises:
        ValueError: If calendar is unreachable or credentials fail.
    """
    if not username.strip():
        raise ValueError("Username is required for remote calendar.")
    if not password.strip():
        raise ValueError("Password is required for remote calendar.")

    https_url = remote_http_url(url)
    status, _ = http_fetch_text(https_url, username, password)

    if status == 401 or status == 403:
        raise ValueError("Invalid username or password.")
    if status == 404:
        raise ValueError("Calendar not found at URL.")
    if status not in (200, 207):
        raise ValueError(f"Cannot access calendar (HTTP {status}).")

    # Try to get event count via CalDAV REPORT
    try:
        payloads = fetch_remote_calendar_payloads(https_url, username, password)
        count = len(payloads)
    except Exception:
        count = 0

    return {
        "count": str(count),
        "description": f"{count} evento(j) trovita(j)",
    }


__all__ = [
    "remote_http_url",
    "http_fetch_text",
    "fetch_remote_calendar_payloads",
    "probe_calendar_config",
    "queue_sync",
    "list_sync_queue",
    "push_event_to_remote",
    "delete_event_from_remote",
    "sync_worker",
    "start_sync_worker",
    "set_password",
    "get_password",
    "delete_password",
]