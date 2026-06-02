"""Sync utilities for CalDAV calendar synchronization."""

from __future__ import annotations

import json
import re
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
) -> list[tuple[str, str]]:
    """Fetch calendar events via CalDAV REPORT.

    Args:
        url: Calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.

    Returns:
        List of (href, calendar_data) tuples, one per event.
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
        return _parse_multistatus(text)
    elif status == 404:
        return []
    else:
        raise RuntimeError(f"CalDAV fetch failed: {status}")


def _parse_multistatus(text: str) -> list[tuple[str, str]]:
    """Parse CalDAV multistatus response.

    Uses ElementTree for reliable XML parsing. Each ``<d:response>``
    contains a ``<d:href>`` (the resource path) and ``<c:calendar-data>``
    (the ICS body). Both are returned as paired tuples.

    Args:
        text: Raw XML multistatus response.

    Returns:
        List of (href, calendar_data) tuples, one per event response.
    """
    import xml.etree.ElementTree as ET

    ns = {
        "d": "DAV:",
        "c": "urn:ietf:params:xml:ns:caldav",
    }
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    results: list[tuple[str, str]] = []
    for response in root.findall("d:response", ns):
        href_el = response.find("d:href", ns)
        href = href_el.text if href_el is not None else ""
        data_el = response.find(".//c:calendar-data", ns)
        data = data_el.text if data_el is not None else ""
        results.append((href.strip(), data.strip()))
    return results


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


def process_sync_job(db, job: dict) -> None:
    """Execute a single sync job (pull or push).

    Updates the job status to ``running`` before processing and to
    ``completed`` or ``failed`` when done.

    Args:
        db: Database connection (``SQLiteDB`` instance).
        job: Sync queue row dict (must include ``id``, ``calendar_uuid``,
            ``operacio``, ``payload``).
    """
    job_id = job["id"]
    cal_uuid = job["calendar_uuid"]
    operacio = job["operacio"]
    payload = json.loads(job["payload"])

    # Update status to running
    db.execute("UPDATE sync_queue SET stato = 'running' WHERE id = ?", (job_id,))

    try:
        cal = db.execute_one(
            "SELECT url, username FROM kalendaroj WHERE uuid = ?", (cal_uuid,)
        )
        if not cal:
            raise ValueError(f"Calendar not found: {cal_uuid}")

        url = cal["url"]
        username = cal["username"]
        password = get_password(cal_uuid)

        if operacio == "pull":
            results = fetch_remote_calendar_payloads(url, username, password)
            stored = 0
            for href, ics_data in results:
                uid_match = re.search(r"^UID:(.+)$", ics_data, re.MULTILINE)
                if uid_match:
                    uid = uid_match.group(1).strip()
                    existing = db.execute_one(
                        "SELECT uuid FROM eventoj WHERE uuid = ? AND kalendaro_uuid = ?",
                        (uid, cal_uuid),
                    )
                    if existing:
                        db.execute(
                            "UPDATE eventoj SET remote_href = ? WHERE uuid = ?",
                            (href, uid),
                        )
                        stored += 1
            info(
                f"[sync] Pulled {len(results)} events, "
                f"updated {stored} remote_hrefs from {cal_uuid[:8]}"
            )
        elif operacio == "push":
            sub_op = payload.get("operation", "")
            event_uuid = payload.get("event_uuid", "")
            if not event_uuid:
                raise ValueError("Push job missing event_uuid")

            remote_href: str | None = payload.get("remote_href") or None
            if not remote_href:
                event_row = db.execute_one(
                    "SELECT remote_href FROM eventoj WHERE uuid = ?",
                    (event_uuid,),
                )
                if event_row and event_row.get("remote_href"):
                    remote_href = event_row["remote_href"]

            if sub_op == "delete":
                delete_event_from_remote(
                    url, username, password, event_uuid, remote_href
                )
                info(f"[sync] Deleted {event_uuid[:8]} from {cal_uuid[:8]}")
            else:
                event = db.execute_one(
                    "SELECT * FROM eventoj WHERE uuid = ?", (event_uuid,)
                )
                if event:
                    from A_organizi.utils.ics import events_to_ics
                    ics_payload = events_to_ics([dict(event)])
                    remote_href = remote_href or event.get("remote_href") or None
                    push_event_to_remote(
                        url, username, password, ics_payload, event_uuid, remote_href
                    )
                    info(f"[sync] Pushed {event_uuid[:8]} ({sub_op}) to {cal_uuid[:8]}")
                else:
                    delete_event_from_remote(
                        url, username, password, event_uuid, remote_href
                    )
                    info(f"[sync] Event {event_uuid[:8]} gone locally, deleted remotely")
        else:
            raise ValueError(f"Unknown operation: {operacio}")

        db.execute(
            "UPDATE sync_queue SET stato = 'completed' WHERE id = ?", (job_id,)
        )

    except Exception as exc:
        db.execute(
            "UPDATE sync_queue SET stato = 'failed', eraro = ? WHERE id = ?",
            (str(exc), job_id),
        )


def sync_worker() -> None:
    """Background worker that processes sync jobs.

    Runs in an infinite loop polling for pending jobs.
    """
    while True:
        db = get_db()
        job = db.execute_one(
            "SELECT * FROM sync_queue WHERE stato = 'pending' ORDER BY kreita_je LIMIT 1"
        )
        if not job:
            import time
            time.sleep(5)
            continue

        process_sync_job(db, dict(job))


# ──────────────────────────────────────────────────────────────────────────────
# CalDAV push helpers
# ──────────────────────────────────────────────────────────────────────────────


# HTTP status descriptions for error messages
_HTTP_DESCRIPTION: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized — check username and password",
    403: "Forbidden — check credentials or calendar permissions",
    404: "Not Found — check calendar URL",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    500: "Internal Server Error",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


def _http_error(status: int, operation: str) -> str:
    """Build a descriptive HTTP error message."""
    desc = _HTTP_DESCRIPTION.get(status, f"HTTP {status}")
    return f"{operation} failed: {desc}"


def _event_url(url: str, event_uuid: str, remote_href: str | None = None) -> str:
    """Build the PUT/DELETE URL for a remote event.

    Uses the server-provided ``remote_href`` when available (correct CalDAV
    resource path), otherwise falls back to fabricating ``{url}/{uuid}.ics``.

    Args:
        url: Base calendar URL.
        event_uuid: Event UUID (used for fallback).
        remote_href: Server-provided resource path (from multistatus).

    Returns:
        Full URL string.
    """
    if remote_href:
        # Ensure absolute URL — if remote_href is a path, prepend origin
        if remote_href.startswith("/"):
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}{remote_href}"
        return remote_href
    return url.rstrip("/") + f"/{event_uuid}.ics"


def push_event_to_remote(
    url: str,
    username: str,
    password: str,
    ics_payload: str,
    event_uuid: str,
    remote_href: str | None = None,
) -> int:
    """PUT an ICS event to the remote CalDAV server.

    Args:
        url: Base calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.
        ics_payload: Full ICS text (VCALENDAR wrapper).
        event_uuid: Event UUID used as the resource name.
        remote_href: Server-provided resource path (from multistatus REPORT).

    Returns:
        HTTP status code (200, 201, or 204 on success).

    Raises:
        RuntimeError: If the server returns an unexpected status.
    """
    put_url = _event_url(url, event_uuid, remote_href)
    headers = {
        "Content-Type": "text/calendar; charset=utf-8",
    }
    status, _ = http_fetch_text(
        put_url, username, password, "PUT", ics_payload, headers
    )
    if status not in (200, 201, 204):
        raise RuntimeError(_http_error(status, "CalDAV PUT"))
    return status


def delete_event_from_remote(
    url: str,
    username: str,
    password: str,
    event_uuid: str,
    remote_href: str | None = None,
) -> int:
    """DELETE an event from the remote CalDAV server.

    Args:
        url: Base calendar URL.
        username: Username for Basic auth.
        password: Password for Basic auth.
        event_uuid: Event UUID used as the resource name.
        remote_href: Server-provided resource path (from multistatus REPORT).

    Returns:
        HTTP status code (200 or 204 on success; 404 is accepted as "already gone").

    Raises:
        RuntimeError: If the server returns an unexpected status.
    """
    delete_url = _event_url(url, event_uuid, remote_href)
    status, _ = http_fetch_text(
        delete_url, username, password, "DELETE"
    )
    if status not in (200, 204, 404):
        raise RuntimeError(_http_error(status, "CalDAV DELETE"))
    return status


def start_sync_worker() -> None:
    """Start the background sync worker (thread-safe lazy init)."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            _worker_thread = Thread(target=sync_worker, daemon=True)
            _worker_thread.start()


# ──────────────────────────────────────────────────────────────────────────────
# Sync queue queries & retry
# ──────────────────────────────────────────────────────────────────────────────


def reprovi_sync_job(
    db,
    job_id: str | None = None,
    calendar_uuid: str | None = None,
) -> int:
    """Retry failed or stuck-pending sync jobs synchronously.

    Finds unprocessed jobs (``failed`` or ``pending``) matching the
    criteria and processes them immediately inline, rather than relying
    on the background worker (which may not be running).

    Args:
        db: Database connection (``SQLiteDB`` instance).
        job_id: Specific job ID to retry. If None, retries ALL unprocessed jobs.
        calendar_uuid: Optional calendar filter (ignored if ``job_id`` set).

    Returns:
        Number of jobs retried.
    """
    params: list[str] = []
    if job_id:
        query = "SELECT * FROM sync_queue WHERE id = ? AND stato IN ('failed', 'pending')"
        params.append(job_id)
    elif calendar_uuid:
        query = "SELECT * FROM sync_queue WHERE calendar_uuid = ? AND stato IN ('failed', 'pending')"
        params.append(calendar_uuid)
    else:
        query = "SELECT * FROM sync_queue WHERE stato IN ('failed', 'pending')"

    jobs = db.execute(query, tuple(params))
    for job in jobs:
        process_sync_job(db, dict(job))
    return len(jobs)


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
        raise ValueError(_http_error(status, "Calendar access"))

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
    "reprovi_sync_job",
    "process_sync_job",
    "push_event_to_remote",
    "delete_event_from_remote",
    "sync_worker",
    "start_sync_worker",
    "set_password",
    "get_password",
    "delete_password",
]