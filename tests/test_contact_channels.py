from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_and_app_contact_channels_use_doobielogic_aliases():
    brand = (ROOT / "frontend" / "src" / "lib" / "brand.ts").read_text(encoding="utf-8")
    channels = (ROOT / "frontend" / "src" / "components" / "ContactChannels.tsx").read_text(encoding="utf-8")
    main = (ROOT / "frontend" / "src" / "main.tsx").read_text(encoding="utf-8")

    for email in ["info@doobielogic.io", "help@doobielogic.io", "support@doobielogic.io"]:
        assert email in brand
    assert "MarketingContactChannels" in channels
    assert "AppSupportButton" in channels
    assert "mailto:${email}" in channels
    assert "mailto:${SUPPORT_EMAIL}" in channels
    assert "<MarketingContactChannels />" in main
    assert "<AppSupportButton />" in main


def test_contact_channel_styles_include_mobile_support_control():
    css = (ROOT / "frontend" / "src" / "contact-channels.css").read_text(encoding="utf-8")
    assert ".marketing-contact-grid" in css
    assert ".app-support-button" in css
    assert "@media (max-width: 760px)" in css
    assert "#ef7427" in css
