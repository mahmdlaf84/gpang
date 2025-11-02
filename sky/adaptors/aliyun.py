"""Alibaba Cloud adaptors."""

# pylint: disable=import-outside-toplevel

from sky.adaptors import common

_IMPORT_ERROR_MESSAGE = (
    'Failed to import dependencies for Alibaba Cloud. '
    'Try pip install "skypilot[aliyun]" to install the optional extras.'
)

aliyunsdkcore = common.LazyImport('aliyunsdkcore',
                                  import_error_message=_IMPORT_ERROR_MESSAGE)
aliyunsdkecs = common.LazyImport('aliyunsdkecs',
                                 import_error_message=_IMPORT_ERROR_MESSAGE)
alibabacloud_credentials = common.LazyImport(
    'alibabacloud_credentials', import_error_message=_IMPORT_ERROR_MESSAGE)

_LAZY_MODULES = (aliyunsdkcore, aliyunsdkecs, alibabacloud_credentials)


@common.load_lazy_modules(modules=_LAZY_MODULES)
def create_client(region: str,
                  access_key_id: str,
                  access_key_secret: str):
    """Create an Alibaba Cloud ECS client."""
    from aliyunsdkcore.client import AcsClient

    return AcsClient(access_key_id, access_key_secret, region)


@common.load_lazy_modules(modules=_LAZY_MODULES)
def exceptions():
    """Return common Alibaba Cloud exceptions."""
    from aliyunsdkcore.acs_exception.exceptions import ClientException
    from aliyunsdkcore.acs_exception.exceptions import ServerException

    return (ClientException, ServerException)
