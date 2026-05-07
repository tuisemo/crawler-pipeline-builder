"""TLS helpers for detail extraction downloads."""

from __future__ import annotations

import os
from urllib3.exceptions import InsecureRequestWarning


def ssl_verify_enabled() -> bool:
    return str(os.environ.get("DETAIL_EXTRACTOR_SSL_VERIFY", "1")).strip().lower() not in {"0", "false", "no"}


def insecure_request_warning():
    return InsecureRequestWarning
