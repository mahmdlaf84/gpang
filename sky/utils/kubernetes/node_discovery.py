"""Node discovery utilities for remote Kubernetes clusters."""
from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sky import sky_logging

logger = sky_logging.init_logger(__name__)


@dataclasses.dataclass
class NodeSpec:
    """Specification for a node to be joined to the Kubernetes cluster."""

    public_ip: str
    internal_ip: Optional[str] = None
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    is_head: bool = False

    def to_json(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {'public_ip': self.public_ip}
        if self.internal_ip:
            data['internal_ip'] = self.internal_ip
        if self.metadata:
            data['metadata'] = self.metadata
        if self.is_head:
            data['is_head'] = True
        return data


class DiscoveryError(RuntimeError):
    """Raised when node discovery fails."""


def _normalize_payload(payload: Any) -> List[NodeSpec]:
    """Normalizes raw payload returned by a discovery provider."""
    if payload is None:
        return []

    if isinstance(payload, dict):
        # Allow either {"nodes": [...] } or {"public_ip": ...}
        if 'nodes' in payload and isinstance(payload['nodes'], Sequence):
            return _normalize_payload(payload['nodes'])
        # Some providers may return role-indexed mapping such as
        # {"head": {...}, "workers": [...]}
        nodes: List[NodeSpec] = []
        for key, value in payload.items():
            if value is None:
                continue
            entries = _normalize_payload(value)
            if key.lower() == 'head':
                for entry in entries:
                    entry.is_head = True
            nodes.extend(entries)
        if nodes:
            return nodes
        payload = [payload]

    nodes: List[NodeSpec] = []
    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return []
        nodes.append(NodeSpec(public_ip=payload))
        return nodes

    if isinstance(payload, Sequence):
        for entry in payload:
            nodes.extend(_normalize_payload(entry))
        return nodes

    if not isinstance(payload, dict):
        raise DiscoveryError(f'Unsupported discovery payload entry: {payload!r}')

    public_ip = str(payload.get('public_ip') or payload.get('ip') or '').strip()
    if not public_ip:
        raise DiscoveryError('Discovery payload is missing "public_ip" field.')

    internal_ip = payload.get('internal_ip') or payload.get('private_ip')
    if isinstance(internal_ip, (int, float)):
        internal_ip = str(internal_ip)
    elif internal_ip is not None:
        internal_ip = str(internal_ip).strip()

    metadata: Dict[str, Any]
    metadata_field = payload.get('metadata')
    if isinstance(metadata_field, dict):
        metadata = dict(metadata_field)
    else:
        metadata = {}
    # Allow top-level region/labels.
    if 'region' in payload and 'region' not in metadata:
        metadata['region'] = payload['region']
    if 'labels' in payload and isinstance(payload['labels'], dict):
        metadata.setdefault('labels', {}).update(payload['labels'])

    is_head = bool(payload.get('is_head') or
                   (isinstance(payload.get('role'), str) and
                    payload['role'].lower() == 'head'))

    nodes.append(
        NodeSpec(public_ip=public_ip,
                 internal_ip=internal_ip,
                 metadata=metadata,
                 is_head=is_head))
    return nodes


def _read_from_path(path: str) -> Any:
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        raise DiscoveryError(f'Discovery file not found: {path}')
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback to newline separated IPs.
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        return lines


def _read_from_http(url: str, timeout: float) -> Any:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        content_type = response.headers.get('Content-Type', '')
        payload = response.read().decode('utf-8')
    if 'json' in content_type:
        return json.loads(payload)
    # Fallback to newline separated IPs.
    lines = [line.strip() for line in payload.splitlines() if line.strip()]
    return lines


def _load_once(spec: str, timeout: float) -> List[NodeSpec]:
    parsed = urllib.parse.urlparse(spec)
    payload: Any
    if parsed.scheme in ('http', 'https'):
        payload = _read_from_http(spec, timeout)
    elif parsed.scheme == 'file':
        payload = _read_from_path(parsed.path)
    elif parsed.scheme == 'exec':
        command = urllib.parse.unquote(parsed.netloc + parsed.path)
        if not command:
            raise DiscoveryError('exec:// requires a command to execute.')
        payload = _run_shell_command(command)
    elif parsed.scheme:
        # Support shorthand exec://command where path may be empty and netloc holds command.
        if parsed.scheme == 'exec+shell':
            if not parsed.path and not parsed.netloc:
                raise DiscoveryError('exec+shell:// requires a command.')
            command = urllib.parse.unquote(parsed.netloc + parsed.path)
            payload = _run_shell_command(command)
        else:
            raise DiscoveryError(f'Unsupported discovery scheme: {parsed.scheme}')
    else:
        # Treat as filesystem path.
        payload = _read_from_path(spec)

    nodes = _normalize_payload(payload)
    # Deduplicate while preserving order.
    seen = set()
    unique_nodes: List[NodeSpec] = []
    for node in nodes:
        if node.public_ip in seen:
            continue
        seen.add(node.public_ip)
        unique_nodes.append(node)
    return unique_nodes


def _run_shell_command(command: str) -> Any:
    proc = subprocess.run(command,
                          check=True,
                          shell=True,  # noqa: S602
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          text=True)
    stdout = proc.stdout.strip()
    if not stdout:
        return []
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return [line.strip() for line in stdout.splitlines() if line.strip()]


def discover_nodes(spec: str,
                   min_nodes: Optional[int] = None,
                   refresh_interval: float = 5.0,
                   timeout: float = 300.0) -> List[NodeSpec]:
    """Discovers nodes using the provided spec.

    Args:
        spec: Discovery specification (e.g. file:///path/to/nodes.json,
            https://example.com/nodes, exec://script.sh).
        min_nodes: Minimum number of nodes required before returning.
        refresh_interval: Interval in seconds between discovery attempts.
        timeout: Maximum time in seconds to wait for discovery.

    Raises:
        DiscoveryError: If discovery fails or times out.
    """
    if not spec:
        raise DiscoveryError('Discovery spec must be provided.')
    deadline = time.time() + timeout if timeout > 0 else None
    attempt = 0
    while True:
        attempt += 1
        try:
            nodes = _load_once(spec, timeout=max(timeout, 5.0))
        except (DiscoveryError, OSError, subprocess.CalledProcessError,
                urllib.error.URLError) as exc:
            logger.warning('Node discovery attempt %d failed: %s', attempt, exc)
            nodes = []
        if nodes and min_nodes is not None and len(nodes) < min_nodes:
            logger.info('Discovered %d node(s); waiting for at least %d nodes.',
                        len(nodes), min_nodes)
        if nodes and (min_nodes is None or len(nodes) >= min_nodes):
            logger.info('Discovered %d node(s).', len(nodes))
            return nodes
        if deadline is not None and time.time() > deadline:
            raise DiscoveryError('Timed out waiting for node discovery.')
        logger.debug('Retrying node discovery in %.1f seconds.',
                     refresh_interval)
        time.sleep(refresh_interval)


def merge_static_ips(ip_list: Optional[Sequence[str]],
                     nodes: List[NodeSpec]) -> List[NodeSpec]:
    """Merges static IP list ordering with discovered nodes."""
    if not ip_list:
        return nodes
    ip_set = {ip.strip() for ip in ip_list if ip}
    ordered_nodes: List[NodeSpec] = []
    for ip in ip_list:
        ip = ip.strip()
        if not ip:
            continue
        match = next((node for node in nodes if node.public_ip == ip), None)
        if match is None:
            match = NodeSpec(public_ip=ip)
        ordered_nodes.append(match)
    # Append any remaining nodes from discovery that were not in the static list.
    for node in nodes:
        if node.public_ip not in ip_set:
            ordered_nodes.append(node)
    return ordered_nodes


def choose_head(nodes: List[NodeSpec]) -> List[NodeSpec]:
    """Ensures the head node is the first entry in the list."""
    if not nodes:
        return nodes
    for index, node in enumerate(nodes):
        if node.is_head:
            if index != 0:
                nodes.insert(0, nodes.pop(index))
            break
    else:
        # Default to the first node as head.
        nodes[0].is_head = True
    return nodes


def infer_overlay_mode(nodes: Iterable[NodeSpec],
                       requested: str = 'auto') -> str:
    """Determines the overlay networking mode to use."""
    if requested != 'auto':
        return requested
    regions = {
        str(node.metadata.get('region'))
        for node in nodes
        if node.metadata.get('region') not in (None, '')
    }
    if len(regions) > 1:
        logger.info('Multiple regions detected in discovery (%s); '
                    'choosing wireguard-native overlay.', ', '.join(regions))
        return 'wireguard-native'
    # Default overlay for single region deployments.
    return 'vxlan'
