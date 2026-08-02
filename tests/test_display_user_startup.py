from __future__ import annotations

import re
from pathlib import Path


APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_display_user_is_initialized_before_first_use() -> None:
    assignment = '_display_user = _current_authenticated_identity()[0] or "Trial User"'
    assignment_position = APP_SOURCE.index(assignment)
    references = [match.start() for match in re.finditer(r"\b_display_user\b", APP_SOURCE)]

    assert references
    assert assignment_position == references[0]
    assert assignment_position < APP_SOURCE.index("\nrender_commandbar(")


def test_display_user_uses_authenticated_identity_with_trial_fallback() -> None:
    assert '_display_user = _current_authenticated_identity()[0] or "Trial User"' in APP_SOURCE
