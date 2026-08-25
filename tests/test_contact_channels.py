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


def test_public_contact_copy_stays_direct_and_does_not_expose_mail_vendor():
    channels = (ROOT / "frontend" / "src" / "components" / "ContactChannels.tsx").read_text(encoding="utf-8")
    marketing = (ROOT / "frontend" / "src" / "pages" / "MarketingHome.tsx").read_text(encoding="utf-8")

    assert "Need to reach us?" in channels
    assert "Contact DoobieLogic" in channels
    assert "Spacemail" not in channels
    assert "Cannabis operations, connected" in marketing
    assert "Run the operation with fewer blind spots." in marketing
    assert "spreadsheet circus" not in marketing
    assert "five exports and a prayer" not in marketing
    assert "without losing the plot" not in marketing


def test_public_marketing_copy_uses_no_em_dashes():
    public_copy_files = [
        ROOT / "frontend" / "src" / "pages" / "MarketingHome.tsx",
        ROOT / "frontend" / "src" / "components" / "ContactChannels.tsx",
    ]

    for path in public_copy_files:
        assert "—" not in path.read_text(encoding="utf-8")


def test_contact_channel_styles_include_mobile_support_control():
    css = (ROOT / "frontend" / "src" / "contact-channels.css").read_text(encoding="utf-8")
    assert ".marketing-contact-grid" in css
    assert ".app-support-button" in css
    assert "@media (max-width: 760px)" in css
    assert "#ef7427" in css


def test_workspace_agent_is_a_floating_translucent_panel():
    css = (ROOT / "frontend" / "src" / "components" / "workspace-agent.css").read_text(encoding="utf-8")

    assert "right:18px" in css
    assert "top:18px" in css
    assert "bottom:18px" in css
    assert "border-radius:22px" in css
    assert "backdrop-filter:blur(24px)" in css
    assert "rgba(4,6,7,.22)" in css
    assert "right:0;top:0;height:100dvh" not in css
