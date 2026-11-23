"""The local studio server: the built canvas plus a token-guarded JSON API.

It binds to 127.0.0.1 only. Any web page open in the same browser can still send
requests to it, so every request must name the server itself as ``Host`` (against
DNS rebinding) and, when it has one, as ``Origin``; the API also needs the random
token of the URL the browser was opened with.

Routes: ``GET /`` and ``GET /assets/*`` (the built frontend), ``GET /api/status``
(model fingerprint, layout revision, load error), ``GET /api/diagrams``
(``build_studio``), ``PUT /api/layout`` (``save_diagrams``, then the SVG export) and
``POST /api/svg`` (``render_download``: one diagram as an SVG download).

A watcher thread re-loads the project about every second and every API request reads
its snapshot, so a model change or a ``git checkout`` shows up without restarting;
a failed load keeps the last good project (``GET /api/status`` reports the error).
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import erdify
from erdify import Project

from erdify_studio._config import StudioConfig
from erdify_studio._diagrams import layout_revision, model_fingerprint, save_diagrams
from erdify_studio._errors import LayoutConflictError, PositionsError, StudioError
from erdify_studio._export import build_studio, export_project, render_download

logger = logging.getLogger(__name__)

#: The built frontend shipped in the package.
STATIC_DIR = Path(__file__).parent / "_static"
#: Loads the project and its studio settings (``erdify.load_project`` + ``load_config``).
ProjectLoader = Callable[[], tuple[Project, StudioConfig]]
#: What loading a project or reading the layout file may raise.
_LOAD_ERRORS = (
    StudioError,
    OSError,
    erdify.ConfigError,
    erdify.ModelParseError,
    erdify.SqlDependencyError,
)
#: Largest request body accepted, in bytes.
MAX_BODY = 10 * 1024 * 1024

_TOKEN_HEADER = "X-Studio-Token"
# Explicit types: ``mimetypes`` reads the Windows registry, which may map ``.js`` to
# ``text/plain``, and browsers refuse to run such a module script.
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


@dataclass(frozen=True)
class Snapshot:
    """The project as the API serves it: the last one that loaded, and why a newer
    load failed (``error``; None when the last load succeeded)."""

    project: Project
    config: StudioConfig
    fingerprint: str
    error: str | None = None


class StudioServer(ThreadingHTTPServer):
    """The studio's HTTP server for one project.

    A watcher thread re-loads the project while the server runs (every
    ``interval()`` seconds: at least ``min_interval``, at least twice the last load's
    duration) and keeps a ``Snapshot``; every API request reads the snapshot. A load
    that fails keeps the last good project and records the error, so a half-typed
    model file never blanks the canvas.

    Attributes:
        token: The secret the API requires in ``X-Studio-Token``.
    """

    daemon_threads = True

    def __init__(
        self,
        load: ProjectLoader,
        *,
        port: int,
        static_dir: Path,
        shown_path: str,
        min_interval: float = 1.0,
    ) -> None:
        self.load = load
        self.static_dir = static_dir.resolve()
        self.shown_path = shown_path
        self.token = secrets.token_urlsafe(32)
        self.save_lock = threading.Lock()
        self.min_interval = min_interval
        self._snapshot_lock = threading.Lock()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        started = time.monotonic()
        project, config = load()  # the first load must succeed, as `check` would
        self._snapshot = Snapshot(project, config, model_fingerprint(project, config))
        self._load_seconds = time.monotonic() - started
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def port(self) -> int:
        """The port the server is bound to."""
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        """The URL that opens the canvas, token included."""
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    def snapshot(self) -> Snapshot:
        """The project the API serves."""
        with self._snapshot_lock:
            return self._snapshot

    def interval(self) -> float:
        """Seconds between two loads: ``min_interval``, or twice the last load's time."""
        return max(self.min_interval, 2 * self._load_seconds)

    def refresh(self) -> None:
        """Load the project once; on failure keep the last good one and record why."""
        started = time.monotonic()
        try:
            project, config = self.load()
            fingerprint = model_fingerprint(project, config)
        except _LOAD_ERRORS as e:
            logger.info(f"cannot load the project, showing the last good state: {e}")
            self._set(replace(self.snapshot(), error=str(e)))
        except Exception:
            logger.exception("cannot load the project, showing the last good state")
            self._set(replace(self.snapshot(), error="internal error (see the terminal)"))
        else:
            self._set(Snapshot(project, config, fingerprint))
        finally:
            self._load_seconds = time.monotonic() - started

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        """Serve, with the watcher thread running until ``shutdown``."""
        self._stop.clear()
        self._watcher = threading.Thread(
            target=self._watch, name="erdify-studio-watch", daemon=True
        )
        self._watcher.start()
        try:
            super().serve_forever(poll_interval)
        finally:
            self._stop_watcher()

    def server_close(self) -> None:
        self._stop_watcher()
        super().server_close()

    def _watch(self) -> None:
        while not self._stop.wait(self.interval()):
            self.refresh()

    def _stop_watcher(self) -> None:
        self._stop.set()
        if self._watcher is not None and self._watcher is not threading.current_thread():
            self._watcher.join()
            self._watcher = None

    def _set(self, snapshot: Snapshot) -> None:
        with self._snapshot_lock:
            self._snapshot = snapshot


def start_server(
    load: ProjectLoader,
    *,
    port: int = 0,
    static_dir: Path | None = None,
    shown_path: str,
    min_interval: float = 1.0,
) -> StudioServer:
    """Bind a studio server on 127.0.0.1 (not serving yet).

    Args:
        load: Loads the project (``strict=True``) and its studio settings; called once
            here, then by the watcher while the server runs.
        port: The port; 0 picks a free one.
        static_dir: The built frontend to serve (default: ``STATIC_DIR``).
        shown_path: The layout file's path as the UI shows it.
        min_interval: Shortest time between two loads, in seconds.

    Raises:
        OSError: The port cannot be bound (e.g. it is in use).
        StudioError, erdify errors: The first load failed.
    """
    return StudioServer(
        load,
        port=port,
        static_dir=static_dir or STATIC_DIR,
        shown_path=shown_path,
        min_interval=min_interval,
    )


class _Handler(BaseHTTPRequestHandler):
    server: StudioServer
    #: Whether the current request's body was read (``_body`` or ``_drain``).
    _body_read = False

    # --- methods ------------------------------------------------------------------

    def do_GET(self) -> None:
        if not self._trusted():
            return
        path = self.path.split("?", 1)[0]
        if path == "/api/diagrams":
            if self._authorized():
                self._diagrams()
        elif path == "/api/status":
            if self._authorized():
                self._status()
        elif path == "/api/layout":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        elif path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "not found")
        else:
            self._static(path)

    def do_PUT(self) -> None:
        self._body_read = False
        if not self._trusted():
            return
        if self.path.split("?", 1)[0] != "/api/layout":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        elif self._authorized():
            self._save()

    def do_POST(self) -> None:
        self._body_read = False
        if not self._trusted():
            return
        if self.path.split("?", 1)[0] != "/api/svg":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        elif self._authorized():
            self._svg()

    def _not_allowed(self) -> None:
        if self._trusted():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    do_DELETE = do_PATCH = _not_allowed

    # --- guards -------------------------------------------------------------------

    def _trusted(self) -> bool:
        """The request names this server as ``Host`` and (if sent) ``Origin``."""
        own = {f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}"}
        origin = self.headers.get("Origin")
        if self.headers.get("Host") in own and (
            origin is None or origin in {f"http://{host}" for host in own}
        ):
            return True
        self._error(HTTPStatus.FORBIDDEN, "request not from the studio page")
        return False

    def _authorized(self) -> bool:
        token = self.headers.get(_TOKEN_HEADER, "")
        if secrets.compare_digest(token.encode(), self.server.token.encode()):
            return True
        self._error(HTTPStatus.FORBIDDEN, "missing or wrong token")
        return False

    # --- routes -------------------------------------------------------------------

    def _static(self, path: str) -> None:
        file = self._static_file(path)
        if file is None:
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        body = file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _TYPES.get(file.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _static_file(self, path: str) -> Path | None:
        """The file of ``path`` inside the static folder; None when there is none."""
        if path == "/":
            path = "/index.html"
        relative = unquote(path)[1:]
        parts = relative.split("/")
        if "\\" in relative or "\0" in relative or any(part in ("", ".", "..") for part in parts):
            return None
        file = self.server.static_dir.joinpath(*parts).resolve()
        if not file.is_relative_to(self.server.static_dir) or not file.is_file():
            return None
        return file

    def _status(self) -> None:
        """What changed: the model fingerprint, the layout file's revision, a load error."""
        snapshot = self.server.snapshot()
        try:
            revision = layout_revision(snapshot.config.layout)
        except OSError as e:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            return
        self._json(
            HTTPStatus.OK,
            {"model": snapshot.fingerprint, "revision": revision, "error": snapshot.error},
        )

    def _diagrams(self) -> None:
        try:
            snapshot = self.server.snapshot()
            project, config = snapshot.project, snapshot.config
            diagrams = build_studio(project, config, shown_path=self.server.shown_path)
        except _LOAD_ERRORS as e:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            return
        except Exception:
            self._internal_error()
            return
        self._json(HTTPStatus.OK, diagrams)

    def _save(self) -> None:
        payload = self._body()
        if payload is None:
            return
        if (
            not isinstance(payload.get("revision", 0), str | None)
            or not {
                "revision",
                "diagrams",
            }
            <= payload.keys()
        ):
            self._error(
                HTTPStatus.BAD_REQUEST, 'expected {"revision": string or null, "diagrams": {...}}'
            )
            return
        try:
            with self.server.save_lock:
                snapshot = self.server.snapshot()
                project, config = snapshot.project, snapshot.config
                revision = save_diagrams(project, config, payload["diagrams"], payload["revision"])
                exported = self._export(project, config)
        except PositionsError as e:
            self._error(HTTPStatus.BAD_REQUEST, str(e))
        except LayoutConflictError as e:
            self._error(HTTPStatus.CONFLICT, str(e))
        except _LOAD_ERRORS as e:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
        except Exception:
            self._internal_error()
        else:
            self._json(
                HTTPStatus.OK, {"saved": self.server.shown_path, "revision": revision, **exported}
            )

    def _svg(self) -> None:
        """One diagram as SVG with the positions the page shows, as a download."""
        payload = self._body()
        if payload is None:
            return
        if not isinstance(payload.get("diagram"), str) or "positions" not in payload:
            self._error(HTTPStatus.BAD_REQUEST, 'expected {"diagram": string, "positions": {...}}')
            return
        try:
            snapshot = self.server.snapshot()
            project, config = snapshot.project, snapshot.config
            name, svg = render_download(project, config, payload["diagram"], payload["positions"])
        except PositionsError as e:
            self._error(HTTPStatus.BAD_REQUEST, str(e))
            return
        except LayoutConflictError as e:
            self._error(HTTPStatus.CONFLICT, str(e))
            return
        except _LOAD_ERRORS as e:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            return
        except Exception:
            self._internal_error()
            return
        body = svg.encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _export(self, project: Project, config: StudioConfig) -> dict[str, int | str]:
        """Export the SVGs after a save: ``exported`` (files written or deleted) or
        ``exportError``. The layout is saved either way, so a failure is not an error
        response: the page must still take the new revision."""
        if config.export_dir is None:
            return {}
        try:
            result = export_project(project, config)
        except (StudioError, OSError) as e:
            logger.warning(f"SVG export after save failed: {e}")
            return {"exportError": str(e)}
        except Exception:
            # A bug, but the layout is saved: the page must still take the new revision.
            logger.exception("SVG export after save failed")
            return {"exportError": "internal error (see the terminal)"}
        return {"exported": len(result.written) + len(result.deleted)}

    def _body(self) -> dict[str, Any] | None:
        """The JSON object of a request body; None after an error response."""
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "expected application/json")
            return None
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            self._error(HTTPStatus.LENGTH_REQUIRED, "Content-Length required")
            return None
        if int(length) > MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"body over {MAX_BODY} bytes")
            return None
        try:
            self._body_read = True
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, RecursionError) as e:
            self._error(HTTPStatus.BAD_REQUEST, f"invalid JSON: {e}")
            return None
        if not isinstance(payload, dict):
            self._error(HTTPStatus.BAD_REQUEST, "expected a JSON object")
            return None
        return payload

    # --- responses ----------------------------------------------------------------

    def _json(self, status: HTTPStatus, data: object) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _internal_error(self) -> None:
        # A bug: keep the traceback for the report, but answer, so the page does not
        # claim the server stopped.
        logger.exception(f"internal error handling {self.command} {self.path.split('?')[0]}")
        self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal error (see the terminal)")

    def _error(self, status: HTTPStatus, message: str) -> None:
        # The body of a refused request may be unread: don't reuse the connection.
        self.close_connection = True
        self._drain()
        self._json(status, {"error": message})

    def _drain(self) -> None:
        """Read the unread body of a request we refuse, up to ``MAX_BODY``.

        Closing a socket with unread data sends a TCP reset instead of a clean close;
        the client may then lose the error response (Windows aborts the read).
        """
        if self._body_read or self.command not in ("PUT", "POST"):
            return
        self._body_read = True
        length = self.headers.get("Content-Length", "")
        if length.isdigit() and int(length) <= MAX_BODY:
            self.rfile.read(int(length))

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib name
        logger.info(f"{self.address_string()} {format % args}")
