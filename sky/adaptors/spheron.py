"""Spheron Network adaptors."""

# pylint: disable=import-outside-toplevel

from __future__ import annotations

from typing import Optional

from sky.adaptors import common

_IMPORT_ERROR_MESSAGE = (
    'Failed to import dependencies for Spheron Network. '
    'Try pip install "skypilot[spheron]" to install the optional extras.'
)

requests = common.LazyImport('requests',
                             import_error_message=_IMPORT_ERROR_MESSAGE)

_LAZY_MODULES = (requests,)


@common.load_lazy_modules(modules=_LAZY_MODULES)
def create_session(api_token: str):
    """Create a requests session authenticated for Spheron APIs."""
    import requests as _requests

    session = _requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {api_token}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    })
    return session


@common.load_lazy_modules(modules=_LAZY_MODULES)
def get_account_metadata(session) -> Optional[dict]:
    """Fetch basic account metadata to validate credentials."""
    response = session.get(
        'https://api-v2.spheron.network/v2/profile',
        timeout=5,
    )
    if response.status_code == 401:
        return None
    response.raise_for_status()
    return response.json()
