# agent/memory.py

## Purpose
Provides per-user conversation memory storage. Auto-selects backend based on whether `REDIS_URL` is set in the environment.

## Two backends

### `InMemoryStore` (default when no REDIS_URL)
- Thread-safe Python dict
- Data lives only as long as the process
- Lost on every server restart
- Good for development/testing

### `RedisMemoryStore` (when REDIS_URL is set)
- Persists across server restarts
- Each user's history stored under key: `spirulina:chat:<user_id>`
- 7-day TTL (resets on every save)
- Works with local Docker Redis, Upstash, Railway, or any Redis-compatible URL

## Storage limits
- `MAX_TURNS = 10` — keeps last 10 user+assistant pairs (= 20 messages)
- Older messages are automatically dropped on `save()`

## Public interface
```python
memory_store.get(user_id)           # returns list[dict] with role/content
memory_store.save(user_id, history) # auto-caps at MAX_TURNS
memory_store.clear(user_id)         # wipes history
```

## Singleton pattern
`memory_store` is a module-level singleton built at import time by `_build_store()`:
1. Reads `REDIS_URL` from env
2. If set: tries to connect (calls `.ping()`), falls back to InMemory on failure
3. If not set: uses InMemory

## How to configure Redis at hosting time
Set the `REDIS_URL` environment variable on your hosting platform:
- Local Docker: `redis://localhost:6379`
- Upstash: `rediss://...upstash.io:6379`
- Railway/Render: URL from their dashboard

No code changes needed — the singleton auto-detects at startup.

## Dependencies
- `redis` Python package (optional — only imported when REDIS_URL is set)
- `threading.Lock` (for InMemoryStore thread safety)
