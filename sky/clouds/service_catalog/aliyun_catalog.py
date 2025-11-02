"""Static catalog for Alibaba Cloud resources."""

from __future__ import annotations

import typing
from typing import Dict, List, Optional, Tuple, Union

from sky.clouds.service_catalog import common
from sky.utils import ux_utils

if typing.TYPE_CHECKING:  # pragma: no cover
    from sky.clouds import cloud
    import pandas as pd

_DATA = [
    {
        'InstanceType': 'ecs.g6.xlarge',
        'AcceleratorName': None,
        'AcceleratorCount': 0,
        'AcceleratorMemoryGiB': None,
        'GpuInfo': '{}',
        'vCPUs': 4,
        'MemoryGiB': 16.0,
        'Price': 0.192,
        'SpotPrice': 0.115,
        'Region': 'cn-beijing',
        'AvailabilityZone': None,
    },
    {
        'InstanceType': 'ecs.g6.2xlarge',
        'AcceleratorName': None,
        'AcceleratorCount': 0,
        'AcceleratorMemoryGiB': None,
        'GpuInfo': '{}',
        'vCPUs': 8,
        'MemoryGiB': 32.0,
        'Price': 0.384,
        'SpotPrice': 0.230,
        'Region': 'ap-southeast-1',
        'AvailabilityZone': None,
    },
    {
        'InstanceType': 'ecs.gn6v-c10g1.2xlarge',
        'AcceleratorName': 'V100',
        'AcceleratorCount': 1,
        'AcceleratorMemoryGiB': 16.0,
        'GpuInfo': '{"Gpus": [{"Name": "NVIDIA Tesla V100", "MemoryInfo": {"SizeInMiB": 16384}}]}',
        'vCPUs': 8,
        'MemoryGiB': 61.0,
        'Price': 3.04,
        'SpotPrice': 1.82,
        'Region': 'cn-hangzhou',
        'AvailabilityZone': None,
    },
]

_DF: Optional['pd.DataFrame'] = None


def _get_df() -> 'pd.DataFrame':
    global _DF  # pylint: disable=global-statement
    if _DF is None:
        _DF = common.pd.DataFrame(_DATA)
    return _DF


def instance_type_exists(instance_type: str) -> bool:
    return common.instance_type_exists_impl(_get_df(), instance_type)


def validate_region_zone(region: Optional[str],
                         zone: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if zone is not None:
        with ux_utils.print_exception_no_traceback():
            raise ValueError('Alibaba Cloud instance catalog does not expose zones.')
    return common.validate_region_zone_impl('aliyun', _get_df(), region, zone)


def get_hourly_cost(instance_type: str,
                    use_spot: bool,
                    region: Optional[str],
                    zone: Optional[str]) -> float:
    if zone is not None:
        with ux_utils.print_exception_no_traceback():
            raise ValueError('Alibaba Cloud catalog does not expose zones.')
    return common.get_hourly_cost_impl(_get_df(), instance_type, use_spot, region, zone)


def get_vcpus_mem_from_instance_type(instance_type: str
                                     ) -> Tuple[Optional[float], Optional[float]]:
    return common.get_vcpus_mem_from_instance_type_impl(_get_df(), instance_type)


def get_default_instance_type(cpus: Optional[str] = None,
                              memory: Optional[str] = None,
                              disk_tier: Optional[str] = None) -> Optional[str]:
    del disk_tier
    return common.get_instance_type_for_cpus_mem_impl(_get_df(), cpus, memory)


def get_accelerators_from_instance_type(
        instance_type: str) -> Optional[Dict[str, Union[int, float]]]:
    return common.get_accelerators_from_instance_type_impl(_get_df(), instance_type)


def get_instance_type_for_accelerator(
        acc_name: str,
        acc_count: int,
        cpus: Optional[str] = None,
        memory: Optional[str] = None,
        use_spot: bool = False,
        region: Optional[str] = None,
        zone: Optional[str] = None) -> Tuple[Optional[List[str]], List[str]]:
    return common.get_instance_type_for_accelerator_impl(
        df=_get_df(),
        acc_name=acc_name,
        acc_count=acc_count,
        cpus=cpus,
        memory=memory,
        use_spot=use_spot,
        region=region,
        zone=zone)


def get_region_zones_for_instance_type(instance_type: str,
                                       use_spot: bool) -> List['cloud.Region']:
    df = _get_df()
    filtered = df[df['InstanceType'] == instance_type]
    return common.get_region_zones(filtered, use_spot)


def list_accelerators(
        gpus_only: bool,
        name_filter: Optional[str],
        region_filter: Optional[str],
        quantity_filter: Optional[int],
        case_sensitive: bool = True,
        all_regions: bool = False,
        require_price: bool = True) -> Dict[str, List[common.InstanceTypeInfo]]:
    return common.list_accelerators_impl('Alibaba Cloud', _get_df(), gpus_only,
                                         name_filter, region_filter,
                                         quantity_filter, case_sensitive,
                                         all_regions, require_price)
