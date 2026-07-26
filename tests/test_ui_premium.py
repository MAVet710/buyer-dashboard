from ui_premium import load_premium_shell


def test_premium_shell_exposes_shared_design_tokens():
    css = load_premium_shell("Dark")

    assert "--dl-copper" in css
    assert "--dl-surface" in css
    assert ".premium-commandbar" in css
    assert ".premium-sidebar-brand" in css
    assert ".premium-sidebar-brand__release" in css


def test_premium_shell_supports_light_and_dark_palettes():
    dark = load_premium_shell("Dark")
    light = load_premium_shell("Light")

    assert "#080A09" in dark
    assert "#F3F4F1" in light
    assert dark != light


def test_premium_shell_includes_responsive_and_accessible_behavior():
    css = load_premium_shell("Dark")

    assert "@media (max-width: 768px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "min-height: 44px" in css
