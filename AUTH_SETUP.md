# 🔐 Streamlit Auth Setup (bcrypt)

## Correct secrets format

```toml
[auth.users]
Jwin = "$2b$12$your_real_hash_here"
```

## Generate hash

Run:

```
streamlit run hash_test.py
```

Enter your password and copy the hash.

## Common mistakes

- Using fake/example hashes
- Not restarting Streamlit after updating secrets
- Not encoding password in check

## Your issue

If you used:

```toml
Jwin = "hash"
```

It will NOT work.

It must be under `[auth.users]`
