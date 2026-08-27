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


def test_public_contact_copy_stays_human_and_does_not_expose_mail_vendor():
    channels = (ROOT / "frontend" / "src" / "components" / "ContactChannels.tsx").read_text(encoding="utf-8")
    marketing = (ROOT / "frontend" / "src" / "pages" / "MarketingHome.tsx").read_text(encoding="utf-8")

    assert "Need us? Pick an inbox." in channels
    assert "A real person will see it." in channels
    assert "Spacemail" not in channels
    assert "Cannabis ops without the spreadsheet circus" in marketing
    assert "Good weed deserves better operations." in marketing


def test_public_hero_copy_is_clear_and_avoids_overwritten_phrasing():
    marketing = (ROOT / "frontend" / "src" / "pages" / "MarketingHome.tsx").read_text(encoding="utf-8")

    assert "and compliance from one place." in marketing
    assert "one clear view of the work that keeps a licensed facility moving" in marketing
    assert "without losing the plot" not in marketing
    assert "five exports and a prayer" not in marketing


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


def test_workspace_agent_is_a_true_floating_window():
    agent_css = (ROOT / "frontend" / "src" / "components" / "workspace-agent.css").read_text(encoding="utf-8")
    window_css = (ROOT / "frontend" / "src" / "components" / "workspace-window.css").read_text(encoding="utf-8")
    agent = (ROOT / "frontend" / "src" / "components" / "WorkspaceAgent.tsx").read_text(encoding="utf-8")
    window = (ROOT / "frontend" / "src" / "components" / "WorkspaceWindow.tsx").read_text(encoding="utf-8")

    assert ".workspace-agent-window{" in agent_css
    assert "bottom:24px" in agent_css
    assert "<WorkspaceWindow" in agent
    assert 'className="workspace-agent-window"' in agent
    assert "onPointerDown={beginDrag}" in window
    assert "Maximize2" in window
    assert "Minimize2" in window
    assert "workspace-window-minimize" in window
    assert "workspace-window-maximize" in window
    assert "workspace-window-close" in window
    assert ".workspace-window.minimized" in window_css
    assert "backdrop-filter:blur(24px)" not in window_css
    assert "backdrop-filter:blur(24px)" not in agent_css


def test_workspace_agent_portals_to_viewport_and_remains_non_blocking():
    agent = (ROOT / "frontend" / "src" / "components" / "WorkspaceAgent.tsx").read_text(encoding="utf-8")
    window = (ROOT / "frontend" / "src" / "components" / "WorkspaceWindow.tsx").read_text(encoding="utf-8")
    window_css = (ROOT / "frontend" / "src" / "components" / "workspace-window.css").read_text(encoding="utf-8")

    assert 'import { WorkspaceWindow } from "./WorkspaceWindow"' in agent
    assert 'import { createPortal } from "react-dom"' in window
    assert "createPortal(" in window
    assert "document.body" in window
    assert 'aria-modal="false"' in window
    assert "workspace-agent-backdrop" not in agent
    assert "workspace-window-backdrop" not in window
    assert "window.innerWidth - state.width" in window
    assert "window.innerHeight - state.height" in window
    assert 'window.addEventListener("resize", clamp)' in window
    assert "min-width:44px;min-height:44px" in window_css
