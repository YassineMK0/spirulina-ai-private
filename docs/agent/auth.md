# agent/auth.py

## Purpose
Resolves a user identity token into a `user_id` string. Currently a stub — the token is returned as-is.

## How it works
- Single public function: `resolve_user(token: str | None) -> str`
- If token is `None` or empty → returns `"anonymous"`
- Otherwise → returns the token string directly as the user_id

## Current state (stub)
The token is **not decoded or verified** — whatever string the caller sends becomes the user_id. This means:
- In `chat.html`, the user_id comes from `localStorage.getItem("spirulina_user_id")` or URL param `?uid=xxx`
- In `streamlit_app.py`, the user_id comes from the username text input
- In `api/main.py`, the user_id comes from the JSON request body field `user_id`

## What to change for real auth
Replace the function body with JWT decoding (template already provided in the docstring):
```python
import jwt
payload = jwt.decode(token, SECRET, algorithms=[ALGO])
return payload.get("sub") or payload.get("user_id") or "anonymous"
```
No other files need to change — only this function body.

## Dependencies
- None (stdlib only)
