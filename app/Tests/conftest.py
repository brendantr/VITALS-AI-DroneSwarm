from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


DEFAULT_POSTGIS_URL = "postgresql://renderer:renderer@0.0.0.0:5432/gis"
DEFAULT_CONNECT_TIMEOUT_S = 3


def get_postgis_url() -> str:
    return os.getenv("VITALS_POSTGIS_URL", DEFAULT_POSTGIS_URL)


def _connect_timeout_seconds() -> int:
    raw_value = os.getenv("VITALS_POSTGIS_CONNECT_TIMEOUT", str(DEFAULT_CONNECT_TIMEOUT_S))
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return DEFAULT_CONNECT_TIMEOUT_S


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {"pool_pre_ping": True}
    drivername = make_url(url).drivername
    if drivername.startswith("postgresql"):
        kwargs["connect_args"] = {"connect_timeout": _connect_timeout_seconds()}
    return kwargs


def create_postgis_engine(url: str | None = None):
    resolved_url = url or get_postgis_url()
    return create_engine(resolved_url, **_engine_kwargs(resolved_url))


def postgis_is_reachable(url: str | None = None) -> bool:
    engine = create_postgis_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def require_reachable_postgis(url: str | None = None) -> str:
    resolved_url = url or get_postgis_url()
    if not postgis_is_reachable(resolved_url):
        pytest.skip(f"PostGIS OSM service is unreachable at {resolved_url}")
    return resolved_url


@pytest.fixture(scope="session")
def postgis_url() -> str:
    return get_postgis_url()


@pytest.fixture(scope="module")
def require_postgis(postgis_url: str) -> str:
    return require_reachable_postgis(postgis_url)


@pytest.fixture(scope="module")
def postgis_engine(require_postgis: str):
    engine = create_postgis_engine(require_postgis)
    try:
        yield engine
    finally:
        engine.dispose()
