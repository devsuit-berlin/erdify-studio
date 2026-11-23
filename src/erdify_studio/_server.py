"""The local studio server: the built canvas plus a token-guarded JSON API.

It binds to 127.0.0.1 only. Any web page open in the same browser can still send
requests to it, so every request must name the server itself as ``Host`` (against
DNS rebinding) and, when it has one, as ``Origin``; the API also needs the random
token of the URL the browser was opened with.

Routes: ``GET /`` and ``GET /assets/*`` (the built frontend), ``GET /api/overview``
(``build_diagrams``) and ``PUT /api/layout`` (``save_overview``).

The project is loaded again for every API request, so a reload after a ``git
checkout`` or a model change shows the current models instead of treating their
positions as stale.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import erdify
from erdify import Project

from erdify_studio._config import StudioConfig
from erdify_studio._diagrams import build_diagrams, save_overview
from erdify_studio._errors import LayoutConflictError, PositionsError, StudioError

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


class StudioServer(ThreadingHTTPServer):
    """The studio's HTTP server for one project.

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
    ) -> None:
        self.load = load
        self.static_dir = static_dir.resolve()
        self.shown_path = shown_path
        self.token = secrets.token_urlsafe(32)
        self.save_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def port(self) -> int:
        """The port the server is bound to."""
        return int(self.server_address[1])

    @property
    def url(self) -> str:
        """The URL that opens the canvas, token included."""
        return f"http://127.0.0.1:{self.port}/?token={self.token}"


def start_server(
    load: ProjectLoader,
    *,
    port: int = 0,
    static_dir: Path | None = None,
    shown_path: str,
) -> StudioServer:
    """Bind a studio server on 127.0.0.1 (not serving yet).

    Args:
        load: Loads the project (``strict=True``) and its studio settings; called for
            every API request.
        port: The port; 0 picks a free one.
        static_dir: The built frontend to serve (default: ``STATIC_DIR``).
        shown_path: The layout file's path as the UI shows it.

    Raises:
        OSError: The port cannot be bound (e.g. it is in use).
    """
    return StudioServer(load, port=port, static_dir=static_dir or STATIC_DIR, shown_path=shown_path)


class _Handler(BaseHTTPRequestHandler):
    server: StudioServer

    # --- methods ------------------------------------------------------------------

    def do_GET(self) -> None:
        if not self._trusted():
            return
        path = self.path.split("?", 1)[0]
        if path == "/api/overview":
            if self._authorized():
                self._overview()
        elif path == "/api/layout":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        elif path.startswith("/api/"):
            self._error(HTTPStatus.NOT_FOUND, "not found")
        else:
            self._static(path)

    def do_PUT(self) -> None:
        if not self._trusted():
            return
        if self.path.split("?", 1)[0] != "/api/layout":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
        elif self._authorized():
            self._save()

    def _not_allowed(self) -> None:
        if self._trusted():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

    do_POST = do_DELETE = do_PATCH = _not_allowed

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

    def _overview(self) -> None:
        try:
            project, config = self.server.load()
            overview = build_diagrams(project, config, shown_path=self.server.shown_path)
        except _LOAD_ERRORS as e:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
            return
        except Exception:
            self._internal_error()
            return
        self._json(HTTPStatus.OK, overview)

    def _save(self) -> None:
        payload = self._body()
        if payload is None:
            return
        try:
            with self.server.save_lock:
                project, config = self.server.load()
                revision = save_overview(project, config, payload["positions"], payload["revision"])
        except PositionsError as e:
            self._error(HTTPStatus.BAD_REQUEST, str(e))
        except LayoutConflictError as e:
            self._error(HTTPStatus.CONFLICT, str(e))
        except _LOAD_ERRORS as e:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
        except Exception:
            self._internal_error()
        else:
            self._json(HTTPStatus.OK, {"saved": self.server.shown_path, "revision": revision})

    def _body(self) -> dict[str, Any] | None:
        """The JSON object of a save request; None after an error response."""
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
            payload = json.loads(self.rfile.read(int(length)))
        except (ValueError, RecursionError) as e:
            self._error(HTTPStatus.BAD_REQUEST, f"invalid JSON: {e}")
            return None
        if (
            not isinstance(payload, dict)
            or "positions" not in payload
            or not isinstance(payload.get("revision", 0), str | None)
            or "revision" not in payload
        ):
            self._error(
                HTTPStatus.BAD_REQUEST,
                'expected {"revision": string or null, "positions": {...}}',
            )
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
        self._json(status, {"error": message})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib name
        logger.info(f"{self.address_string()} {format % args}")
