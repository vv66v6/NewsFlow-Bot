"""create_app construction: route wiring, opt-in CORS, and the api_host
default. No server is started — assertions walk the FastAPI app object."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # needs the api extra

from newsflow.api import create_app  # noqa: E402
from newsflow.config import Settings  # noqa: E402


def _patch_settings(monkeypatch, **overrides):
    settings = Settings(telegram_token="dummy", **overrides)
    monkeypatch.setattr("newsflow.api.get_settings", lambda: settings)
    return settings


def test_routes_include_admin_and_subscriptions(monkeypatch):
    _patch_settings(monkeypatch)
    app = create_app()
    # starlette 1.x hides included routes behind lazy router objects — the
    # OpenAPI schema is the stable public surface to assert against.
    paths = set(app.openapi()["paths"])
    assert "/api/admin/reload" in paths
    assert "/api/subscriptions" in paths
    assert "/api/subscriptions/{sub_id}/pause" in paths
    assert "/api/subscriptions/opml" in paths
    assert "/health" in paths


def test_cors_is_off_by_default_and_opt_in(monkeypatch):
    from fastapi.middleware.cors import CORSMiddleware

    _patch_settings(monkeypatch)
    app = create_app()
    assert all(m.cls is not CORSMiddleware for m in app.user_middleware)

    _patch_settings(monkeypatch, api_cors_origins=["https://dash.example.com"])
    app = create_app()
    assert any(m.cls is CORSMiddleware for m in app.user_middleware)


def test_api_host_defaults_to_loopback():
    assert Settings(telegram_token="dummy").api_host == "127.0.0.1"


def test_cors_origins_accepts_comma_form():
    settings = Settings(telegram_token="dummy", api_cors_origins="https://a.com, https://b.com")
    assert settings.api_cors_origins == ["https://a.com", "https://b.com"]


# ===== readiness status codes =====


class _GoodDB:
    async def execute(self, *args, **kwargs):
        return None


class _BadDB:
    async def execute(self, *args, **kwargs):
        raise RuntimeError("db down")


async def test_ready_returns_200_when_healthy(monkeypatch):
    from newsflow.api.routes.health import readiness_check

    monkeypatch.setattr(
        "newsflow.api.routes.health.get_settings", lambda: Settings(telegram_token="x")
    )
    resp = await readiness_check(db=_GoodDB())
    assert resp.status_code == 200


async def test_ready_returns_503_when_db_down(monkeypatch):
    """Orchestrators and load balancers act on the status code, not the
    body — a 200 with ready:false kept routing traffic to a dead app."""
    import json

    from newsflow.api.routes.health import readiness_check

    monkeypatch.setattr(
        "newsflow.api.routes.health.get_settings", lambda: Settings(telegram_token="x")
    )
    resp = await readiness_check(db=_BadDB())
    assert resp.status_code == 503
    body = json.loads(resp.body)
    assert body["ready"] is False
    assert body["checks"]["database"] is False
