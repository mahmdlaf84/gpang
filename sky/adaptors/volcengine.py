"""Volcengine (ByteDance Cloud) adaptors."""

# pylint: disable=import-outside-toplevel

from sky.adaptors import common

_IMPORT_ERROR_MESSAGE = (
    'Failed to import dependencies for Volcengine. '
    'Try pip install "skypilot[volcengine]" to install the optional extras.'
)

volcengine = common.LazyImport('volcengine',
                               import_error_message=_IMPORT_ERROR_MESSAGE)

_LAZY_MODULES = (volcengine,)


@common.load_lazy_modules(modules=_LAZY_MODULES)
def create_client(service: str, region: str):
    """Create a Volcengine service client."""
    from volcengine import Client

    return Client(service, region=region)


@common.load_lazy_modules(modules=_LAZY_MODULES)
def exceptions():
    """Return Volcengine exception type."""
    from volcengine.base import exception as volc_exceptions

    return (volc_exceptions.ClientException,)
