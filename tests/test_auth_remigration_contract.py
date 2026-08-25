from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_login_restores_streamlit_story_form_trial_and_help_copy():
    auth = source("frontend/src/components/AuthGate.tsx")
    for marker in (
        "DoobieLogic",
        "Operations Intelligence",
        "Keep shelves stocked, production moving, and chaos off the schedule.",
        "DoobieLogic connects buying, inventory, compliance, production, Co-Man, and fulfillment",
        "Buy smarter. Stock cleaner.",
        "Count inventory from the floor",
        "Plan Co-Man without guesswork",
        "Reports leadership will actually read",
        "Welcome back",
        "Sign in. The inventory still refuses to count itself.",
        "Cloud workspace connected",
        "Username",
        "Password",
        "Kicking the tires? Enter a trial key",
        "Activate 24-hour trial",
        "Each company gets its own secured workspace",
    ):
        assert marker in auth
    assert '/api/v1/trial/activate' in auth
    assert 'buyer-dash-trial-token' in auth
    assert 'PasswordGate><LegalGate>' in auth


def test_username_login_uses_durable_username_instead_of_fabricated_email_alias():
    auth = source("frontend/src/components/AuthGate.tsx")
    api = source("frontend/src/lib/api.ts")
    account = source("backend/app/routers/account.py")

    assert '/api/v1/account/username-login' in auth
    assert 'apiPublicPost<UsernameSession>' in auth
    assert 'supabase!.auth.setSession' in auth
    assert '@users.doobielogic.io' not in auth
    assert 'export async function apiPublicPost' in api
    assert '@router.post("/username-login")' in account
    assert 'AppUser.normalized_username == normalized_username' in account
    assert '/auth/v1/token?grant_type=password' in account
    assert 'auth_session["auth_user_id"] != app_user_id' in account


def test_password_gate_keeps_first_login_change_requirement_with_doobielogic_branding():
    password = source("frontend/src/components/PasswordGate.tsx")
    for marker in (
        "DoobieLogic",
        "First login security",
        "Create your private password",
        "temporary password",
        "at least 12 characters",
        "Confirm new password",
        "Set password & continue",
        "/api/v1/account/password-changed",
    ):
        assert marker in password
    assert "<strong>Buyer Dash</strong>" not in password


def test_legal_gate_and_trial_sandbox_boundary_remain_mandatory():
    legal = source("frontend/src/components/LegalGate.tsx")
    for marker in (
        "Welcome to DoobieLogic",
        "Terms of Service",
        "Privacy Policy",
        "/api/v1/legal/current",
        "/api/v1/legal/accept",
        "Accept and continue",
    ):
        assert marker in legal
    trial = source("backend/app/routers/trial.py")
    for marker in ("dev-sandbox", "trial", "activate"):
        assert marker in trial


def test_auth_visual_layer_matches_streamlit_mobile_first_layout():
    css = source("frontend/src/auth-streamlit.css")
    main = source("frontend/src/main.tsx")
    for marker in (
        "grid-template-columns:minmax(0,1.15fr) minmax(330px,.85fr)",
        "border-radius:24px",
        "min-height:540px",
        "grid-template-columns:repeat(2,minmax(0,1fr))",
        "@media(max-width:820px)",
        "@media(max-width:430px)",
    ):
        assert marker in css
    assert '"./auth-streamlit.css"' in main
