from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.routers import metrc_harvest_actions as subject


def test_unconfigured_harvest_status_is_local_only_but_writes_stay_blocked(monkeypatch):
    context = object()
    engine = object()
    settings = object()
    metrc = SimpleNamespace(
        configured=False,
        state="MA",
        environment="sandbox",
        license_number="",
        message="Sandbox user API key is not configured.",
    )
    monkeypatch.setattr(subject, "_resolved_metrc", lambda *_args: metrc)

    status = subject.harvest_action_status(context=context, engine=engine, settings=settings)

    assert status["ready"] is False
    assert status["promoted_actions"] == []
    assert "local" in status["execution_boundary"].casefold()
    with pytest.raises(HTTPException) as exc_info:
        subject._metrc(context, engine, settings)
    assert exc_info.value.status_code == 409


def test_non_ma_or_production_context_never_promotes_harvest_writes(monkeypatch):
    context = object()
    engine = object()
    settings = object()
    metrc = SimpleNamespace(
        configured=True,
        state="MA",
        environment="production",
        license_number="LIC-PROD",
        message="Connected production mapping.",
    )
    monkeypatch.setattr(subject, "_resolved_metrc", lambda *_args: metrc)

    status = subject.harvest_action_status(context=context, engine=engine, settings=settings)

    assert status["ready"] is False
    assert status["promoted_actions"] == []
    with pytest.raises(HTTPException) as exc_info:
        subject._metrc(context, engine, settings)
    assert exc_info.value.status_code == 409


def test_verified_ma_sandbox_status_exposes_only_promoted_actions(monkeypatch):
    context = object()
    engine = object()
    settings = object()
    metrc = SimpleNamespace(
        configured=True,
        state="MA",
        environment="sandbox",
        license_number="LIC-SANDBOX",
        message="Connected.",
    )
    monkeypatch.setattr(subject, "_resolved_metrc", lambda *_args: metrc)

    status = subject.harvest_action_status(context=context, engine=engine, settings=settings)

    assert status["ready"] is True
    assert set(status["promoted_actions"]) == set(subject.PROMOTED_HARVEST_ACTIONS)
    assert subject._metrc(context, engine, settings) is metrc
