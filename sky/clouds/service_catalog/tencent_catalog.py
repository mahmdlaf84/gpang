"""Static catalog for Tencent Cloud resources."""

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
        'InstanceType': 'S5.LARGE8',
        'AcceleratorName': None,
        'AcceleratorCount': 0,
        'AcceleratorMemoryGiB': None,
        'GpuInfo': '{}',
        'vCPUs': 2,
        'MemoryGiB': 8.0,
        'Price': 0.150,
        'SpotPrice': 0.090,
        'Region': 'ap-guangzhou',
        'AvailabilityZone': None,
    },
    {
        'InstanceType': 'SA2.4XLARGE32',
        'AcceleratorName': None,
        'AcceleratorCount': 0,
        'AcceleratorMemoryGiB': None,
        'GpuInfo': '{}',
        'vCPUs': 16,
        'MemoryGiB': 32.0,
        'Price': 0.640,
        'SpotPrice': 0.384,
        'Region': 'ap-shanghai',
        'AvailabilityZone': None,
    },
    {
        'InstanceType': 'GN10XNEC8',
        'AcceleratorName': 'A100',
        'AcceleratorCount': 1,
        'AcceleratorMemoryGiB': 40.0,
        'GpuInfo': '{"Gpus": [{"Name": "NVIDIA A100", "MemoryInfo": {"SizeInMiB": 40960}}]}',
        'vCPUs': 12,
        'MemoryGiB': 96.0,
        'Price': 4.30,
        'SpotPrice': 2.58,
        'Region': 'ap-beijing',
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
            raise ValueError('Tencent Cloud catalog does not expose zones.')
    return common.validate_region_zone_impl('tencent', _get_df(), region, zone)


def get_hourly_cost(instance_type: str,
                    use_spot: bool,
                    region: Optional[str],
                    zone: Optional[str]) -> float:
    if zone is not None:
        with ux_utils.print_exception_no_traceback():
            raise ValueError('Tencent Cloud catalog does not expose zones.')
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
    return common.list_accelerators_impl('Tencent Cloud', _get_df(), gpus_only,
                                         name_filter, region_filter,
                                         quantity_filter, case_sensitive,
                                         all_regions, require_price)
