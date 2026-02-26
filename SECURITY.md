# Security Configuration Guide

This document explains how to configure credentials, bcrypt password hashing,
and environment-variable fallbacks for the Cannabis Buyer Dashboard.

---

## 1. Configuring `st.secrets` (recommended for Streamlit Cloud)

Create a `.streamlit/secrets.toml` file in the project root (never commit this
file – it is already in `.gitignore`).

```toml
[auth]
# Set to true ONLY for local development / legacy plaintext mode.
# Omit or set to false in production so that bcrypt hashes are required.
use_plaintext = false

# Admin credentials: username -> bcrypt hash
[auth.admins]
God    = "$2b$12$EXAMPLE_HASH_FOR_GOD_REPLACE_ME"
JVas   = "$2b$12$EXAMPLE_HASH_FOR_JVAS_REPLACE_ME"

# Standard user credentials: username -> bcrypt hash
[auth.users]
KHuston = "$2b$12$EXAMPLE_HASH_FOR_KHUSTON_REPLACE_ME"
ERoots  = "$2b$12$EXAMPLE_HASH_FOR_EROOTS_REPLACE_ME"
AFreed  = "$2b$12$EXAMPLE_HASH_FOR_AFREED_REPLACE_ME"

# Bcrypt hash of the trial key
trial_key_hash = "$2b$12$EXAMPLE_HASH_FOR_TRIAL_KEY_REPLACE_ME"
```

> **Important:** Replace every `EXAMPLE_HASH_*` placeholder with a real bcrypt
> hash generated with the snippet below. Never put plaintext passwords in this
> file unless `use_plaintext = true` is explicitly set (dev/legacy only).

---

## 2. Generating bcrypt hashes locally

Run the following one-liner in any Python 3 environment that has `bcrypt`
installed (`pip install bcrypt`):

```python
import bcrypt
# Replace "your_password_here" with the actual password or trial key.
print(bcrypt.hashpw(b"your_password_here", bcrypt.gensalt()).decode())
```

Or use the helper function already present in `app.py`:

```python
from app import hash_password
print(hash_password("your_password_here"))
```

Copy the printed `$2b$12$...` string into the relevant field in
`.streamlit/secrets.toml`.

---

## 3. Environment variable fallback

If Streamlit secrets are not available (e.g., running locally without a
`secrets.toml`), the app falls back to the following environment variables:

| Variable              | Description                                  |
|-----------------------|----------------------------------------------|
| `ADMIN_USERNAME`      | Username of the single fallback admin        |
| `ADMIN_PASSWORD_HASH` | Bcrypt hash of the admin password            |
| `USER_USERNAME`       | Username of the single fallback regular user |
| `USER_PASSWORD_HASH`  | Bcrypt hash of the user password             |
| `TRIAL_KEY_HASH`      | Bcrypt hash of the trial key                 |

Example (Linux / macOS):

```bash
export ADMIN_USERNAME="God"
export ADMIN_PASSWORD_HASH="$(python -c "import bcrypt; print(bcrypt.hashpw(b'YourAdminPassword', bcrypt.gensalt()).decode())")"
```

---

## 4. Secrets file hygiene

- Add `.streamlit/secrets.toml` to `.gitignore` so it is never committed.
- Rotate credentials immediately if they are accidentally exposed.
- Do **not** enable `use_plaintext = true` in production environments.

---

## 5. Upload size limit

Files larger than **50 MB** are rejected at runtime with a clear error message.
This limit is controlled by the `MAX_UPLOAD_BYTES` constant in `app.py`.

---

## 6. Login brute-force protection

After **5** consecutive failed login attempts, the login form is locked for
**10 minutes**. The counters are stored in `st.session_state` and reset on
successful login or server restart.
