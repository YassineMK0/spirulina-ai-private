"""Centralised observability setup.

Call setup_logging() once at application startup (before any other imports
that might log).  It configures:

  - Python root logger  ->  console (INFO) + Logstash async TCP (INFO)
  - Sentry SDK          ->  FastAPI + Starlette integrations, exception capture

Environment variables
---------------------
LOGSTASH_HOST      Logstash TCP input host (default: localhost)
LOGSTASH_PORT      Logstash TCP input port (default: 5000)
SENTRY_DSN         Sentry project DSN — leave empty to disable Sentry
ENVIRONMENT        "development" | "staging" | "production" (default: development)
LOG_LEVEL          Root log level (default: INFO)
"""
from __future__ import annotations

import logging
import logging.config
import os


def setup_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # ── Console handler ────────────────────────────────────────────────────────
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console)

    # ── Logstash async handler ─────────────────────────────────────────────────
    logstash_host = os.getenv("LOGSTASH_HOST", "")
    logstash_port = int(os.getenv("LOGSTASH_PORT", "5000"))

    if logstash_host:
        try:
            from logstash_async.handler import AsynchronousLogstashHandler
            from logstash_async.formatter import LogstashFormatter

            ls_handler = AsynchronousLogstashHandler(
                host=logstash_host,
                port=logstash_port,
                database_path=None,   # in-memory queue — no SQLite file needed
            )
            ls_handler.setLevel(level)
            ls_handler.setFormatter(LogstashFormatter(
                message_type="spirulina",
                extra_prefix="fields",
                extra={
                    "app":         "spirulina-ai",
                    "environment": os.getenv("ENVIRONMENT", "development"),
                },
            ))
            root.addHandler(ls_handler)
            logging.getLogger(__name__).info(
                "Logstash handler active  host=%s port=%d", logstash_host, logstash_port
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Logstash handler failed to initialise: %s", exc
            )
    else:
        logging.getLogger(__name__).debug(
            "LOGSTASH_HOST not set — log shipping disabled"
        )

    # ── Sentry ────────────────────────────────────────────────────────────────
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.fastapi import FastApiIntegration
            from sentry_sdk.integrations.starlette import StarletteIntegration
            from sentry_sdk.integrations.logging import LoggingIntegration

            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[
                    StarletteIntegration(transaction_style="url"),
                    FastApiIntegration(transaction_style="url"),
                    # Capture WARNING+ as breadcrumbs, ERROR+ as Sentry events
                    LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
                ],
                traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
                environment=os.getenv("ENVIRONMENT", "development"),
                release=os.getenv("APP_VERSION", "spirulina-ai@2.0.0"),
            )
            logging.getLogger(__name__).info("Sentry active  dsn=%s...", sentry_dsn[:32])
        except Exception as exc:
            logging.getLogger(__name__).warning("Sentry failed to initialise: %s", exc)
    else:
        logging.getLogger(__name__).debug("SENTRY_DSN not set — Sentry disabled")

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers",
                  "apscheduler", "paho", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
