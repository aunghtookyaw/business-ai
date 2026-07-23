#!/usr/bin/env python3
"""Operational WSGI wrapper for BigShot Business OS.

This module is the sole production server entrypoint. Application routes and
business logic remain in business_os_app.
"""

import os
import subprocess
import sys
import time
import urllib.request

import psycopg2
from flask import jsonify

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from business_os_app import app


STARTED_AT = time.monotonic()


def _uptime():
    seconds = int(time.monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    prefix = f"{days}d " if days else ""
    return f"{prefix}{hours:02d}:{minutes:02d}:{seconds:02d}"


def _postgres_status():
    try:
        import config

        connection = psycopg2.connect(
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            dbname=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            connect_timeout=2,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        finally:
            connection.close()
        return "ok"
    except Exception:
        return "unavailable"


def _nocodb_status():
    try:
        import config

        request = urllib.request.Request(config.NOCODB_URL, method="GET")
        with urllib.request.urlopen(request, timeout=2) as response:
            return "ok" if response.status < 500 else "unavailable"
    except Exception:
        return "unavailable"


def _module_status(module_name):
    try:
        __import__(module_name)
        return "ok"
    except Exception:
        return "unavailable"


def _version():
    configured = os.environ.get("BUSINESS_OS_VERSION")
    if configured:
        return configured
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            timeout=2,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


@app.get("/status")
def business_os_status():
    return jsonify(
        {
            "status": "running",
            "uptime": _uptime(),
            "postgres": _postgres_status(),
            "nocodb": _nocodb_status(),
            "formula_engine": _module_status("tools.formula_engine"),
            "receive_payment": "ok",
            "voucher_engine": _module_status("tools.voucher_engine"),
            "inventory": _module_status("tools.sotephwar_inventory"),
            "version": _version(),
        }
    )


if __name__ == "__main__":
    from waitress import serve

    serve(
        app,
        host=os.environ.get("RECEIVE_PAYMENT_HOST", "0.0.0.0"),
        port=int(os.environ.get("RECEIVE_PAYMENT_PORT", "5059")),
        threads=4,
    )
