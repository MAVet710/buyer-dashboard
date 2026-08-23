from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_user_management_preserves_streamlit_account_workflow():
    source = (ROOT / "frontend" / "src" / "pages" / "AdminPage.tsx").read_text(encoding="utf-8")
    source = source.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    for label in [
        "User Management",
        "Create and manage durable app accounts stored in PostgreSQL. Passwords are bcrypt-hashed before saving.",
        "Username",
        "Display Name",
        "Email",
        "Role",
        "Active",
        "Organization ID",
        "Must Change Password",
        "Last Login",
        "Created",
        "Platform Organizations & Facilities",
        "Add Organization",
        "Add Facility",
        "Organization name",
        "Organization slug",
        "Facility name",
        "Facility code",
        "Timezone",
        "Create User",
        "Manage Existing",
        "Email (optional)",
        "Facility access",
        "Temporary password",
        "Confirm temporary password",
        "Require password change",
        "Account Details & Access",
        "Account active",
        "Require password change at next login",
        "Save all account changes",
        "Reset Password",
        "New temporary password",
        "Confirm new password",
        "Reset password",
    ]:
        assert label in source
    assert "/api/v1/admin/users/create" in source
    assert "Authentication migration tools (additive)" in source


def test_admin_create_user_backs_streamlit_temporary_password_flow_with_supabase_auth():
    source = (ROOT / "backend" / "app" / "routers" / "admin_user_create.py").read_text(encoding="utf-8")
    main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    for contract in [
        'class UserCreate(BaseModel)',
        'password: str = Field(min_length=12',
        'must_change_password: bool = True',
        '@router.post("/users/create", status_code=201)',
        'email_confirm',
        '@users.doobielogic.io',
        'bcrypt.hashpw',
        'user_created_with_temporary_password',
        '_sync_auth_identity',
    ]:
        assert contract in source
    assert "admin_user_create_router" in main
