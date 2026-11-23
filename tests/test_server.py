"""The local studio server: static files, the token-guarded JSON API, its guards."""

import http.client
import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import erdify
import pytest

from erdify_studio import OVERVIEW, StudioConfig, load_config, place_project
from erdify_studio._diagrams import build_diagrams, layout_revision
from erdify_studio._server import StudioServer, start_server

MODELS = """\
from sqlmodel import Field, SQLModel


class Customer(SQLModel, table=True):
    __tablename__ = "customers"
    id: int = Field(primary_key=True)


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"
    id: int = Field(primary_key=True)
    customer_id: int = Field(foreign_key="customers.id")
"""

SHOWN = "erdify-layout.json"


@dataclass
class Studio:
    server: StudioServer
    root: Path

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        *,
        token: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        sent = {"Host": f"127.0.0.1:{self.port}"}
        if token:
            sent["X-Studio-Token"] = self.server.token
        sent.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            connection.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            for name, value in sent.items():
                connection.putheader(name, value)
            if body is not None and "Content-Length" not in sent:
                connection.putheader("Content-Length", str(len(body)))
            connection.endheaders(body)
            response = connection.getresponse()
            return response.status, dict(response.headers), response.read()
        finally:
            connection.close()

    def put_layout(self, payload: object, **kwargs: Any) -> tuple[int, dict[str, str], bytes]:
        headers = {"Content-Type": "application/json", **kwargs.pop("headers", {})}
        return self.request(
            "PUT", "/api/layout", json.dumps(payload).encode(), headers=headers, **kwargs
        )


def _project(root: Path) -> Path:
    root.mkdir()
    (root / "pyproject.toml").write_text('[tool.erdify]\ninclude = ["**/models.py"]\n')
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(MODELS)
    return root


def _loader(root: Path) -> Callable[[], tuple[erdify.Project, StudioConfig]]:
    def load() -> tuple[erdify.Project, StudioConfig]:
        project = erdify.load_project(root, strict=True)
        return project, load_config(project.settings.pyproject)

    return load


def _static(root: Path) -> Path:
    static = root / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<!doctype html><title>studio</title>")
    (static / "assets" / "app.js").write_text("console.log(1)")
    (static / "assets" / "app.css").write_text("body{}")
    return static


@pytest.fixture
def studio(tmp_path: Path) -> Iterator[Studio]:
    root = _project(tmp_path / "project")
    server = start_server(_loader(root), static_dir=_static(tmp_path), shown_path=SHOWN)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield Studio(server, root)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _json(body: bytes) -> Any:
    return json.loads(body)


def _payload(studio: Studio) -> dict[str, Any]:
    status, _, body = studio.request("GET", "/api/diagrams")
    assert status == 200
    result: dict[str, Any] = _json(body)
    return result


def _diagrams(studio: Studio) -> dict[str, dict[str, list[int]]]:
    """Every diagram's positions, as the page sends them back unchanged."""
    return {d["name"]: d["positions"] for d in _payload(studio)["diagrams"]}


def _positions(studio: Studio) -> dict[str, list[int]]:
    return _diagrams(studio)[OVERVIEW]


# --- binding and static files -----------------------------------------------------


def test_binds_localhost_only(studio: Studio) -> None:
    assert studio.server.server_address[0] == "127.0.0.1"


def test_url_carries_the_token(studio: Studio) -> None:
    assert studio.server.url == f"http://127.0.0.1:{studio.port}/?token={studio.server.token}"


def test_tokens_differ_per_server(studio: Studio, tmp_path: Path) -> None:
    other = start_server(_loader(studio.root), static_dir=tmp_path, shown_path=SHOWN)
    other.server_close()
    assert other.token != studio.server.token


def test_serves_the_index(studio: Studio) -> None:
    status, headers, body = studio.request("GET", "/", token=False)
    assert (status, headers["Content-Type"], body) == (
        200,
        "text/html; charset=utf-8",
        b"<!doctype html><title>studio</title>",
    )


def test_serves_the_index_with_the_token_query(studio: Studio) -> None:
    status, _, _ = studio.request("GET", f"/?token={studio.server.token}", token=False)
    assert status == 200


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/assets/app.js", "text/javascript; charset=utf-8"),
        ("/assets/app.css", "text/css; charset=utf-8"),
    ],
)
def test_serves_assets_with_their_type(studio: Studio, path: str, content_type: str) -> None:
    status, headers, _ = studio.request("GET", path, token=False)
    assert (status, headers["Content-Type"]) == (200, content_type)


@pytest.mark.parametrize(
    "path",
    [
        "/../pyproject.toml",
        "/assets/..%2f..%2fproject%2fpyproject.toml",
        "/%2e%2e/project/pyproject.toml",
        "/assets\\..\\..\\project\\pyproject.toml",
        "//etc/passwd",
        "/assets/missing.js",
        "/assets",
        "/%00",
        "/assets/app.js%00.html",
    ],
)
def test_paths_outside_static_or_missing_are_404(studio: Studio, path: str) -> None:
    status, _, _ = studio.request("GET", path, token=False)
    assert status == 404


# --- guards -----------------------------------------------------------------------


@pytest.mark.parametrize("token", [None, "wrong"])
@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/api/diagrams"), ("PUT", "/api/layout"), ("POST", "/api/svg")]
)
def test_api_requires_the_token(studio: Studio, token: str | None, method: str, path: str) -> None:
    headers = {"X-Studio-Token": token} if token else {}
    status, _, body = studio.request(method, path, b"{}", headers=headers, token=False)
    assert (status, _json(body)) == (403, {"error": "missing or wrong token"})


@pytest.mark.parametrize("host", ["evil.example:{port}", "127.0.0.1:1", "evil.example"])
def test_rejects_a_foreign_host(studio: Studio, host: str) -> None:
    status, _, _ = studio.request(
        "GET", "/api/diagrams", headers={"Host": host.format(port=studio.port)}
    )
    assert status == 403


def test_rejects_a_foreign_host_for_static_files(studio: Studio) -> None:
    status, _, _ = studio.request("GET", "/", headers={"Host": "evil.example"}, token=False)
    assert status == 403


def test_accepts_localhost(studio: Studio) -> None:
    status, _, _ = studio.request(
        "GET", "/api/diagrams", headers={"Host": f"localhost:{studio.port}"}
    )
    assert status == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "http://127.0.0.1:1", "null"])
def test_rejects_a_foreign_origin(studio: Studio, origin: str) -> None:
    status, _, _ = studio.request("GET", "/api/diagrams", headers={"Origin": origin})
    assert status == 403


def test_accepts_the_own_origin(studio: Studio) -> None:
    status, _, _ = studio.request(
        "GET", "/api/diagrams", headers={"Origin": f"http://127.0.0.1:{studio.port}"}
    )
    assert status == 200


# --- API --------------------------------------------------------------------------


def test_get_diagrams(studio: Studio) -> None:
    project = erdify.load_project(studio.root, strict=True)
    expected = build_diagrams(project, load_config(project.settings.pyproject), shown_path=SHOWN)
    status, headers, body = studio.request("GET", "/api/diagrams")
    assert (status, headers["Cache-Control"], headers["Content-Type"], _json(body)) == (
        200,
        "no-store",
        "application/json",
        json.loads(json.dumps(expected)),
    )


def test_put_layout_saves(studio: Studio) -> None:
    status, _, body = studio.put_layout({"revision": None, "diagrams": _diagrams(studio)})
    path = studio.root / SHOWN
    assert (status, _json(body)) == (200, {"saved": SHOWN, "revision": layout_revision(path)})


def test_put_layout_bad_positions_is_400(studio: Studio) -> None:
    diagrams: dict[str, Any] = _diagrams(studio)
    diagrams[OVERVIEW] = {**diagrams[OVERVIEW], "customers": [True, 1]}
    status, _, body = studio.put_layout({"revision": None, "diagrams": diagrams})
    assert (status, "error" in _json(body)) == (400, True)
    assert not (studio.root / SHOWN).exists()


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"diagrams": {}}',
        b'{"revision": 1, "diagrams": {}}',
        b'{"revision": null, "positions": {}}',
    ],
    ids=["not-json", "not-object", "no-revision", "revision-not-string", "no-diagrams"],
)
def test_put_a_malformed_body_is_400(studio: Studio, body: bytes) -> None:
    status, _, _ = studio.request(
        "PUT", "/api/layout", body, headers={"Content-Type": "application/json"}
    )
    assert status == 400


def test_put_too_large_is_413(studio: Studio) -> None:
    status, _, _ = studio.request(
        "PUT",
        "/api/layout",
        b"",
        headers={"Content-Type": "application/json", "Content-Length": str(11 * 1024 * 1024)},
    )
    assert status == 413


def test_put_without_length_is_411(studio: Studio) -> None:
    status, _, _ = studio.request(
        "PUT", "/api/layout", headers={"Content-Type": "application/json"}
    )
    assert status == 411


def test_put_wrong_content_type_is_415(studio: Studio) -> None:
    status, _, _ = studio.put_layout(
        {"revision": None, "diagrams": {}}, headers={"Content-Type": "text/plain"}
    )
    assert status == 415


def test_put_conflict_is_409(studio: Studio) -> None:
    project = erdify.load_project(studio.root, strict=True)
    place_project(project, load_config(project.settings.pyproject))
    status, _, body = studio.put_layout({"revision": None, "diagrams": _diagrams(studio)})
    assert (status, "changed" in _json(body)["error"]) == (409, True)


def test_broken_layout_after_start_is_500_on_get(studio: Studio) -> None:
    (studio.root / SHOWN).write_text("<<<<<<< HEAD\n")
    status, _, body = studio.request("GET", "/api/diagrams")
    assert (status, "error" in _json(body)) == (500, True)


def test_broken_layout_is_never_overwritten(studio: Studio) -> None:
    path = studio.root / SHOWN
    diagrams = _diagrams(studio)
    path.write_text("<<<<<<< HEAD\n")
    status, _, _ = studio.put_layout({"revision": layout_revision(path), "diagrams": diagrams})
    assert (status, path.read_text()) == (500, "<<<<<<< HEAD\n")


def test_unknown_api_route_is_404(studio: Studio) -> None:
    status, _, _ = studio.request("GET", "/api/nothing")
    assert status == 404


@pytest.mark.parametrize(("method", "path"), [("POST", "/api/layout"), ("PUT", "/")])
def test_other_methods_are_405(studio: Studio, method: str, path: str) -> None:
    status, _, _ = studio.request(method, path, b"{}")
    assert status == 405


# --- the models are read per request ---------------------------------------------

ORDER = """

class Order(SQLModel, table=True):
    __tablename__ = "orders"
    id: int = Field(primary_key=True)
"""


def test_a_reload_shows_changed_models(studio: Studio) -> None:
    (studio.root / "shop" / "models.py").write_text(MODELS + ORDER)
    assert "orders" in _positions(studio)


def test_saving_from_a_page_with_old_models_is_409(studio: Studio) -> None:
    diagrams = _diagrams(studio)
    (studio.root / "shop" / "models.py").write_text(MODELS + ORDER)
    status, _, body = studio.put_layout({"revision": None, "diagrams": diagrams})
    assert (status, "models changed" in _json(body)["error"]) == (409, True)
    assert not (studio.root / SHOWN).exists()


def test_a_parse_error_after_start_is_500(studio: Studio) -> None:
    (studio.root / "shop" / "models.py").write_text("class Broken(:\n")
    status, _, body = studio.request("GET", "/api/diagrams")
    assert (status, "error" in _json(body)) == (500, True)


def _crash(*args: object, **kwargs: object) -> None:
    raise RuntimeError("boom")


@pytest.mark.parametrize("target", ["build_studio", "save_diagrams"])
def test_an_unexpected_error_is_500_not_a_dropped_connection(
    studio: Studio, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    monkeypatch.setattr(f"erdify_studio._server.{target}", _crash)
    if target == "build_studio":
        status, _, body = studio.request("GET", "/api/diagrams")
    else:
        status, _, body = studio.put_layout({"revision": None, "diagrams": {}})
    assert (status, _json(body)) == (500, {"error": "internal error (see the terminal)"})


def test_the_old_overview_route_is_gone(studio: Studio) -> None:
    status, _, _ = studio.request("GET", "/api/overview")
    assert status == 404


# --- SVG export on save ------------------------------------------------------------


@pytest.fixture
def exporting(tmp_path: Path) -> Iterator[Studio]:
    root = _project(tmp_path / "project")
    (root / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\n[tool.erdify-studio]\nexport_dir = "erd"\n'
    )
    server = start_server(_loader(root), static_dir=_static(tmp_path), shown_path=SHOWN)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    try:
        yield Studio(server, root)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_save_writes_the_svgs(exporting: Studio) -> None:
    status, _, body = exporting.put_layout({"revision": None, "diagrams": _diagrams(exporting)})
    result = _json(body)
    assert (status, result["exported"], "exportError" in result) == (200, 2, False)
    assert (exporting.root / "erd" / "overview.svg").is_file()
    assert _payload(exporting)["pending"]["svgs"] == 0


def test_a_failed_export_still_saves_the_layout(exporting: Studio) -> None:
    models = exporting.root / "shop" / "models.py"
    models.write_text(
        models.read_text()
        + '\n\nclass A(SQLModel, table=True):\n    __tablename__ = "a"\n'
        + '    __table_args__ = {"schema": "Sales"}\n    id: int = Field(primary_key=True)\n'
        + '\n\nclass B(SQLModel, table=True):\n    __tablename__ = "b"\n'
        + '    __table_args__ = {"schema": "sales"}\n    id: int = Field(primary_key=True)\n'
    )
    (exporting.root / "pyproject.toml").write_text(
        '[tool.erdify]\ninclude = ["**/models.py"]\n[tool.erdify-studio]\n'
        'export_dir = "erd"\ngroup_by = "schema"\n'
    )
    status, _, body = exporting.put_layout({"revision": None, "diagrams": _diagrams(exporting)})
    result = _json(body)
    path = exporting.root / SHOWN
    assert status == 200
    assert "'Sales'" in result["exportError"] and "exported" not in result
    assert result["revision"] == layout_revision(path)


# --- download one diagram as SVG ---------------------------------------------------


def _post_svg(studio: Studio, payload: object, **kwargs: Any) -> tuple[int, dict[str, str], bytes]:
    headers = {"Content-Type": "application/json", **kwargs.pop("headers", {})}
    return studio.request(
        "POST", "/api/svg", json.dumps(payload).encode(), headers=headers, **kwargs
    )


def test_post_svg_returns_the_diagram(studio: Studio) -> None:
    positions = _diagrams(studio)[OVERVIEW]
    status, headers, body = _post_svg(studio, {"diagram": OVERVIEW, "positions": positions})
    assert (status, headers["Content-Type"], headers["Cache-Control"]) == (
        200,
        "image/svg+xml; charset=utf-8",
        "no-store",
    )
    assert headers["Content-Disposition"] == 'attachment; filename="overview.svg"'
    assert body.startswith(b'<svg xmlns="http://www.w3.org/2000/svg"')
    assert not (studio.root / SHOWN).exists()  # nothing written


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"diagram": "gone", "positions": {}}, 409),
        ({"diagram": OVERVIEW, "positions": {"customers": [0, 0]}}, 409),
        ({"diagram": OVERVIEW, "positions": []}, 400),
        ({"positions": {}}, 400),
        ({"diagram": 1, "positions": {}}, 400),
    ],
)
def test_post_svg_errors(studio: Studio, payload: object, status: int) -> None:
    assert _post_svg(studio, payload)[0] == status


def test_post_svg_with_unreadable_models_is_500(studio: Studio) -> None:
    (studio.root / "shop" / "models.py").write_text("class Broken(:\n")
    status, _, body = _post_svg(studio, {"diagram": OVERVIEW, "positions": {}})
    assert (status, "error" in _json(body)) == (500, True)


def test_post_svg_bug_is_500(studio: Studio, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("erdify_studio._server.render_download", _crash)
    status, _, body = _post_svg(studio, {"diagram": OVERVIEW, "positions": {}})
    assert (status, _json(body)) == (500, {"error": "internal error (see the terminal)"})


@pytest.mark.parametrize("method", ["DELETE", "PATCH"])
def test_delete_and_patch_are_405(studio: Studio, method: str) -> None:
    status, _, _ = studio.request(method, "/api/layout", b"{}")
    assert status == 405


def test_post_svg_with_a_malformed_body_is_400(studio: Studio) -> None:
    status, _, _ = studio.request(
        "POST", "/api/svg", b"not json", headers={"Content-Type": "application/json"}
    )
    assert status == 400


@pytest.mark.parametrize(("method", "path"), [("PUT", "/api/layout"), ("POST", "/api/svg")])
def test_writes_from_a_foreign_host_are_refused(studio: Studio, method: str, path: str) -> None:
    status, _, _ = studio.request(method, path, b"{}", headers={"Host": "evil.example"})
    assert status == 403


def test_get_of_the_layout_route_is_405(studio: Studio) -> None:
    assert studio.request("GET", "/api/layout")[0] == 405
