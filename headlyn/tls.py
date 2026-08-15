"""Runtime TLS configuration for environments with an incomplete system CA store."""

from __future__ import annotations

import os
from pathlib import Path


def configure_ca_bundle() -> str | None:
    """Use certifi's CA bundle without overriding explicit user configuration."""
    try:
        import certifi
    except ImportError:
        return None

    bundle = Path(certifi.where())
    if not bundle.is_file():
        return None

    configured_bundle = (
        os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or str(bundle)
    )
    os.environ.setdefault("SSL_CERT_FILE", configured_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", configured_bundle)
    os.environ.setdefault("CURL_CA_BUNDLE", configured_bundle)
    return configured_bundle
