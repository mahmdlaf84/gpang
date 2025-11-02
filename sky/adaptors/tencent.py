"""Tencent Cloud adaptors."""

# pylint: disable=import-outside-toplevel

from sky.adaptors import common

_IMPORT_ERROR_MESSAGE = (
    'Failed to import dependencies for Tencent Cloud. '
    'Try pip install "skypilot[tencent]" to install the optional extras.'
)

tencentcloud = common.LazyImport('tencentcloud',
                                  import_error_message=_IMPORT_ERROR_MESSAGE)

_LAZY_MODULES = (tencentcloud,)


@common.load_lazy_modules(modules=_LAZY_MODULES)
def create_client(service: str,
                  version: str,
                  region: str,
                  secret_id: str,
                  secret_key: str):
    """Create a Tencent Cloud client."""
    from importlib import import_module
    from tencentcloud.common import credential
    from tencentcloud.common import exceptions as tencent_exceptions
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile

    cred = credential.Credential(secret_id, secret_key)
    http_profile = HttpProfile()
    client_profile = ClientProfile(httpProfile=http_profile)
    module = import_module(f'tencentcloud.{service}.{version}.{service}_client')
    client_class = getattr(module, f'{service.capitalize()}Client')
    try:
        return client_class(cred, region, client_profile)
    except tencent_exceptions.TencentCloudSDKException:
        raise


@common.load_lazy_modules(modules=_LAZY_MODULES)
def exceptions():
    """Return Tencent Cloud exception base class."""
    from tencentcloud.common import exceptions as tencent_exceptions

    return (tencent_exceptions.TencentCloudSDKException,)
