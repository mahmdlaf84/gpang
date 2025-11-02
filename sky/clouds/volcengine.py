"""Volcengine (ByteDance Cloud) implementation."""

from __future__ import annotations

import os
import typing
from typing import Dict, Iterator, List, Optional, Tuple, Union

from sky import clouds
from sky import exceptions
from sky.clouds import service_catalog
from sky.utils import registry
from sky.utils import resources_utils

from sky.adaptors import volcengine

if typing.TYPE_CHECKING:  # pragma: no cover
    from sky import resources as resources_lib

_CREDENTIAL_ENV_VARS = (
    'VOLC_ACCESS_KEY_ID',
    'VOLC_ACCESS_KEY_SECRET',
)


@registry.CLOUD_REGISTRY.register(aliases=['volc', 'volcengine'])
class Volcengine(clouds.Cloud):
    """Volcengine Cloud."""

    _REPR = 'Volcengine'
    _MAX_CLUSTER_NAME_LEN_LIMIT = 80
    _CLOUD_UNSUPPORTED_FEATURES = {
        clouds.CloudImplementationFeatures.MULTI_NODE:
            'Multi-node provisioning is not yet implemented for Volcengine.',
        clouds.CloudImplementationFeatures.SPOT_INSTANCE:
            'Spot bidding is not implemented.',
        clouds.CloudImplementationFeatures.CUSTOM_DISK_TIER:
            'Custom disk tiers are not supported.',
        clouds.CloudImplementationFeatures.OPEN_PORTS:
            'Security group automation is not implemented.',
        clouds.CloudImplementationFeatures.STOP:
            'Stopping instances is not supported.',
    }

    PROVISIONER_VERSION = clouds.ProvisionerVersion.SKYPILOT
    STATUS_VERSION = clouds.StatusVersion.SKYPILOT

    @classmethod
    def _unsupported_features_for_resources(
        cls, resources: 'resources_lib.Resources'
    ) -> Dict[clouds.CloudImplementationFeatures, str]:
        del resources
        return dict(cls._CLOUD_UNSUPPORTED_FEATURES)

    @classmethod
    def max_cluster_name_length(cls) -> Optional[int]:
        return cls._MAX_CLUSTER_NAME_LEN_LIMIT

    @classmethod
    def regions_with_offering(cls, instance_type: str,
                              accelerators: Optional[Dict[str, int]],
                              use_spot: bool, region: Optional[str],
                              zone: Optional[str]) -> List[clouds.Region]:
        del accelerators, zone
        if use_spot:
            return []
        regions = service_catalog.get_region_zones_for_instance_type(
            instance_type, use_spot, 'volcengine')
        if region is not None:
            regions = [r for r in regions if r.name == region]
        return regions

    @classmethod
    def get_vcpus_mem_from_instance_type(
        cls,
        instance_type: str,
    ) -> Tuple[Optional[float], Optional[float]]:
        return service_catalog.get_vcpus_mem_from_instance_type(
            instance_type, clouds='volcengine')

    @classmethod
    def zones_provision_loop(
        cls,
        *,
        region: str,
        num_nodes: int,
        instance_type: str,
        accelerators: Optional[Dict[str, int]] = None,
        use_spot: bool = False,
    ) -> Iterator[None]:
        del num_nodes
        regions = cls.regions_with_offering(instance_type, accelerators,
                                            use_spot, region, None)
        for reg in regions:
            yield reg.zones

    def instance_type_to_hourly_cost(self,
                                     instance_type: str,
                                     use_spot: bool,
                                     region: Optional[str] = None,
                                     zone: Optional[str] = None) -> float:
        return service_catalog.get_hourly_cost(instance_type,
                                               use_spot=use_spot,
                                               region=region,
                                               zone=zone,
                                               clouds='volcengine')

    def accelerators_to_hourly_cost(self,
                                    accelerators: Dict[str, int],
                                    use_spot: bool,
                                    region: Optional[str] = None,
                                    zone: Optional[str] = None) -> float:
        del accelerators, use_spot, region, zone
        return 0.0

    def get_egress_cost(self, num_gigabytes: float) -> float:
        return 0.12 * num_gigabytes

    @classmethod
    def get_default_instance_type(
        cls,
        cpus: Optional[str] = None,
        memory: Optional[str] = None,
        disk_tier: Optional[resources_utils.DiskTier] = None,
    ) -> Optional[str]:
        return service_catalog.get_default_instance_type(cpus=cpus,
                                                         memory=memory,
                                                         disk_tier=disk_tier,
                                                         clouds='volcengine')

    @classmethod
    def get_accelerators_from_instance_type(
        cls,
        instance_type: str,
    ) -> Optional[Dict[str, Union[int, float]]]:
        return service_catalog.get_accelerators_from_instance_type(
            instance_type, clouds='volcengine')

    @classmethod
    def get_zone_shell_cmd(cls) -> Optional[str]:
        return None

    def make_deploy_resources_variables(
            self,
            resources: 'resources_lib.Resources',
            cluster_name: resources_utils.ClusterName,
            region: 'clouds.Region',
            zones: Optional[List['clouds.Zone']],
            num_nodes: int,
            dryrun: bool = False) -> Dict[str, Optional[str]]:
        del zones, cluster_name, dryrun, num_nodes
        instance_type = resources.instance_type
        if instance_type is None:
            raise exceptions.NotSupportedError(
                'Volcengine requires an explicit instance_type.')
        acc_dict = self.get_accelerators_from_instance_type(instance_type)
        custom_resources = resources_utils.make_ray_custom_resources_str(acc_dict)
        image_id = None
        if resources.image_id is not None:
            image_id = resources.image_id.get(region.name)
        return {
            'instance_type': instance_type,
            'custom_resources': custom_resources,
            'region': region.name,
            'image_id': image_id,
            'use_spot': resources.use_spot,
        }

    @classmethod
    def _check_credentials(cls) -> Tuple[bool, Optional[str]]:
        missing = [env for env in _CREDENTIAL_ENV_VARS if not os.environ.get(env)]
        if missing:
            return (False,
                    'Volcengine credentials not configured. Set environment '
                    f'variables {", ".join(missing)}.')
        region = os.environ.get('VOLC_REGION', 'cn-beijing')
        ak = os.environ['VOLC_ACCESS_KEY_ID']
        sk = os.environ['VOLC_ACCESS_KEY_SECRET']
        try:
            client = volcengine.create_client('ecs', region)
            client.set_ak(ak)
            client.set_sk(sk)
            client.json('DescribeRegions', {})
        except Exception as exc:  # pylint: disable=broad-except
            return False, repr(exc)
        return True, None

    @classmethod
    def check_credentials(cls) -> Tuple[bool, Optional[str]]:
        return cls._check_credentials()

