"""Node registration helpers for SkyPilot."""
from __future__ import annotations

import concurrent.futures
import dataclasses
import json
import subprocess
import textwrap
from typing import Dict, List, Optional, Sequence

from sky import sky_logging
from sky.utils.kubernetes import node_discovery

logger = sky_logging.init_logger(__name__)


@dataclasses.dataclass
class NodeFacts:
    """Metadata collected from a remote node."""

    hostname: Optional[str] = None
    internal_ip: Optional[str] = None
    network: List[Dict[str, object]] = dataclasses.field(default_factory=list)
    gpus: List[Dict[str, object]] = dataclasses.field(default_factory=list)
    warnings: List[str] = dataclasses.field(default_factory=list)
    error: Optional[str] = None
    cloud: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    instance_id: Optional[str] = None
    instance_type: Optional[str] = None
    vpc_id: Optional[str] = None
    subnet_id: Optional[str] = None
    provider_metadata: Dict[str, object] = dataclasses.field(default_factory=dict)


class NodeRegistrationError(RuntimeError):
    """Raised when node metadata cannot be collected."""


_REMOTE_FACTS_SCRIPT = textwrap.dedent(
    """
    import json
    import socket
    import subprocess
    import urllib.request
    from typing import Dict, Optional

    result = {
        "hostname": None,
        "internal_ip": None,
        "interfaces": [],
        "gpus": [],
        "warnings": [],
        "error": None,
        "cloud": None,
        "region": None,
        "zone": None,
        "instance_id": None,
        "instance_type": None,
        "vpc_id": None,
        "subnet_id": None,
        "provider_metadata": {},
    }

    def _run(cmd: str):
        try:
            return subprocess.check_output(cmd,
                                           shell=True,
                                           stderr=subprocess.STDOUT,
                                           text=True)
        except Exception as exc:  # pylint: disable=broad-except
            result["warnings"].append(f"{cmd}: {exc}")
            return None

    def _safe_fetch(url: str,
                    *,
                    headers: Optional[Dict[str, str]] = None,
                    timeout: float = 1.0) -> Optional[str]:
        try:
            request = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                data = response.read().decode('utf-8')
            return data
        except Exception:  # pylint: disable=broad-except
            return None

    def _strip_or_none(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    def _fetch_first(base: str, *paths: str) -> Optional[str]:
        for path in paths:
            payload = _safe_fetch(base + path)
            if payload:
                return payload
        return None

    def _detect_aliyun() -> Optional[Dict[str, Optional[str]]]:
        base = 'http://100.100.100.200/latest/meta-data/'
        region = _strip_or_none(_fetch_first(base, 'region-id', 'instance/region-id'))
        zone = _strip_or_none(_fetch_first(base, 'zone-id', 'instance/zone-id'))
        instance_id = _strip_or_none(
            _fetch_first(base, 'instance-id', 'instance/instance-id'))
        instance_type = _strip_or_none(
            _fetch_first(base, 'instance-type', 'instance/instance-type'))
        vpc_id = _strip_or_none(_fetch_first(base, 'vpc-id', 'instance/vpc-id'))
        vswitch_id = _strip_or_none(
            _fetch_first(base, 'vswitch-id', 'instance/vswitch-id'))
        if not any([region, zone, instance_id, instance_type, vpc_id, vswitch_id]):
            return None
        metadata: Dict[str, Optional[str]] = {}
        mac = _strip_or_none(_safe_fetch(base + 'mac'))
        if mac:
            metadata['mac'] = mac
        return {
            'cloud': 'alibaba-cloud',
            'region': region,
            'zone': zone,
            'instance_id': instance_id,
            'instance_type': instance_type,
            'vpc_id': vpc_id,
            'subnet_id': vswitch_id,
            'metadata': metadata,
        }

    def _detect_tencent() -> Optional[Dict[str, Optional[str]]]:
        base = 'http://metadata.tencentyun.com/latest/meta-data/'
        region = _strip_or_none(_safe_fetch(base + 'placement/region'))
        zone = _strip_or_none(_safe_fetch(base + 'placement/zone'))
        instance_id = _strip_or_none(_safe_fetch(base + 'instance-id'))
        instance_type = _strip_or_none(_safe_fetch(base + 'instance-type'))
        vpc_id = _strip_or_none(_safe_fetch(base + 'vpc-id'))
        subnet_id = _strip_or_none(_safe_fetch(base + 'subnet-id'))
        if not any([region, zone, instance_id, instance_type, vpc_id, subnet_id]):
            return None
        metadata: Dict[str, Optional[str]] = {}
        macs = _safe_fetch(base + 'network/interfaces/macs/')
        if macs:
            metadata['macs_path'] = 'network/interfaces/macs/'
        return {
            'cloud': 'tencent-cloud',
            'region': region,
            'zone': zone,
            'instance_id': instance_id,
            'instance_type': instance_type,
            'vpc_id': vpc_id,
            'subnet_id': subnet_id,
            'metadata': metadata,
        }

    def _detect_bytedance() -> Optional[Dict[str, Optional[str]]]:
        base = 'http://100.96.0.96/latest/meta-data/'
        region = _strip_or_none(_safe_fetch(base + 'region-id'))
        zone = _strip_or_none(_safe_fetch(base + 'zone-id'))
        instance_id = _strip_or_none(_safe_fetch(base + 'instance-id'))
        instance_type = _strip_or_none(_safe_fetch(base + 'instance-type'))
        vpc_id = _strip_or_none(_safe_fetch(base + 'vpc-id'))
        subnet_id = _strip_or_none(_safe_fetch(base + 'subnet-id'))
        if not any([region, zone, instance_id, instance_type, vpc_id, subnet_id]):
            return None
        return {
            'cloud': 'volcengine',
            'region': region,
            'zone': zone,
            'instance_id': instance_id,
            'instance_type': instance_type,
            'vpc_id': vpc_id,
            'subnet_id': subnet_id,
        }

    def _detect_digitalocean() -> Optional[Dict[str, Optional[str]]]:
        payload = _safe_fetch(
            'http://169.254.169.254/metadata/v1.json',
            headers={'Metadata-Flavor': 'DigitalOcean'})
        if not payload:
            return None
        try:
            data = json.loads(payload)
        except Exception:  # pylint: disable=broad-except
            return None
        region = _strip_or_none(str(data.get('region', '') or ''))
        instance_id = data.get('id')
        if instance_id is not None:
            instance_id = _strip_or_none(str(instance_id))
        if not any([region, instance_id]):
            return None
        metadata: Dict[str, Optional[str]] = {}
        features = data.get('features')
        if isinstance(features, list):
            metadata['features'] = features
        networks = data.get('networks')
        if isinstance(networks, dict):
            metadata['networks'] = networks
        return {
            'cloud': 'digitalocean',
            'region': region,
            'zone': _strip_or_none(str(data.get('region', '') or '')),
            'instance_id': instance_id,
            'instance_type': _strip_or_none(str(data.get('size_slug', '') or '')),
            'metadata': metadata,
        }

    def _detect_cloud() -> Optional[Dict[str, Optional[str]]]:
        for detector in (
                _detect_aliyun,
                _detect_tencent,
                _detect_bytedance,
                _detect_digitalocean):
            info = detector()
            if info:
                return info
        return None

    result["hostname"] = socket.gethostname()

    ip_output = _run('ip -j addr show')
    if ip_output:
        try:
            interfaces = json.loads(ip_output)
        except Exception as exc:  # pylint: disable=broad-except
            result["warnings"].append(f"ip -j addr show decode: {exc}")
            interfaces = []
    else:
        interfaces = []

    for interface in interfaces:
        entry = {
            "name": interface.get("ifname"),
            "mac": interface.get("address"),
            "mtu": interface.get("mtu"),
            "state": interface.get("operstate"),
            "addresses": [],
        }
        for addr in interface.get("addr_info") or []:
            family = addr.get("family")
            if family not in ("inet", "inet6"):
                continue
            entry["addresses"].append({
                "family": family,
                "address": addr.get("local"),
                "prefixlen": addr.get("prefixlen"),
            })
            if result["internal_ip"] is None and family == "inet":
                result["internal_ip"] = addr.get("local")
        result["interfaces"].append(entry)

    if result["internal_ip"] is None:
        try:
            result["internal_ip"] = socket.gethostbyname(result["hostname"])
        except Exception as exc:  # pylint: disable=broad-except
            result["warnings"].append(f"hostname lookup failed: {exc}")

    provider = _detect_cloud()
    if provider:
        for key, value in provider.items():
            if key == 'metadata' and isinstance(value, dict):
                result['provider_metadata'] = value
                continue
            if value is not None:
                result[key] = value

    gpu_output = _run('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader')
    gpus = []
    if gpu_output:
        for line in gpu_output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split(',')]
            gpu_entry = {"name": parts[0]}
            if len(parts) > 1:
                gpu_entry["memory"] = parts[1]
            gpus.append(gpu_entry)
    else:
        lspci_output = _run("lspci | grep -i 'vga\\|3d\\|display'")
        if lspci_output:
            gpus = [{"name": line.strip()} for line in lspci_output.splitlines()
                    if line.strip()]
    result["gpus"] = gpus

    print(json.dumps(result))
    """
)


def _run_remote_script(ssh_base_cmd: List[str],
                       command_timeout: float) -> str:
    last_error: Optional[str] = None
    for interpreter in ('python3', 'python'):
        remote_cmd = (
            f"{interpreter} - <<'PY'\n{_REMOTE_FACTS_SCRIPT}\nPY\n")
        try:
            proc = subprocess.run(ssh_base_cmd + [remote_cmd],
                                  capture_output=True,
                                  text=True,
                                  timeout=command_timeout,
                                  check=False)
        except subprocess.TimeoutExpired as exc:
            last_error = f'timeout after {command_timeout}s: {exc}'
            continue

        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            stdout = proc.stdout.strip()
            details = stderr or stdout or f'exit code {proc.returncode}'
            last_error = details
            continue

        stdout = proc.stdout.strip()
        if not stdout:
            last_error = 'empty response from remote script'
            continue

        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            last_error = 'empty response from remote script'
            continue
        return lines[-1]

    raise NodeRegistrationError(last_error or 'failed to execute remote script')


def _collect_node_facts(node: node_discovery.NodeSpec,
                         ssh_user: str,
                         ssh_key_path: str,
                         connect_timeout: float,
                         command_timeout: float) -> NodeFacts:
    timeout_value = max(int(connect_timeout), 1)
    ssh_base_cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'IdentitiesOnly=yes',
        '-o', 'BatchMode=yes',
        '-o', f'ConnectTimeout={timeout_value}',
        '-i', ssh_key_path,
        f'{ssh_user}@{node.public_ip}',
    ]

    output = _run_remote_script(ssh_base_cmd, command_timeout)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise NodeRegistrationError(
            f'invalid JSON payload from {node.public_ip}: {exc}: {output}')

    def _maybe_str(value: Optional[object]) -> Optional[str]:
        if value in (None, ''):
            return None
        return str(value)

    return NodeFacts(
        hostname=payload.get('hostname'),
        internal_ip=payload.get('internal_ip'),
        network=payload.get('interfaces') or [],
        gpus=payload.get('gpus') or [],
        warnings=[w for w in payload.get('warnings', []) if w],
        error=payload.get('error'),
        cloud=_maybe_str(payload.get('cloud')),
        region=_maybe_str(payload.get('region')),
        zone=_maybe_str(payload.get('zone')),
        instance_id=_maybe_str(payload.get('instance_id')),
        instance_type=_maybe_str(payload.get('instance_type')),
        vpc_id=_maybe_str(payload.get('vpc_id')),
        subnet_id=_maybe_str(payload.get('subnet_id')),
        provider_metadata=payload.get('provider_metadata') or {},
    )


def collect_node_facts(
        nodes: Sequence[node_discovery.NodeSpec],
        ssh_user: str,
        ssh_key_path: str,
        connect_timeout: float = 10.0,
        command_timeout: float = 20.0,
        max_workers: Optional[int] = None) -> Dict[str, NodeFacts]:
    """Collects facts for each node in ``nodes``."""

    if not nodes:
        return {}

    worker_limit = len(nodes)
    if max_workers is not None:
        worker_limit = max(1, min(worker_limit, max_workers))
    else:
        worker_limit = max(1, min(worker_limit, 32))

    results: Dict[str, NodeFacts] = {}

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=worker_limit) as executor:
        future_to_node = {
            executor.submit(_collect_node_facts, node, ssh_user,
                            ssh_key_path, connect_timeout, command_timeout):
            node
            for node in nodes
        }

        for future in concurrent.futures.as_completed(future_to_node):
            node = future_to_node[future]
            try:
                facts = future.result()
            except NodeRegistrationError as exc:
                logger.warning('Failed to gather metadata for %s: %s',
                               node.public_ip, exc)
                facts = NodeFacts(error=str(exc))
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception('Unexpected error gathering metadata for %s',
                                 node.public_ip)
                facts = NodeFacts(error=str(exc))

            if facts.internal_ip is None:
                facts.internal_ip = node.internal_ip
            results[node.public_ip] = facts

    return results
