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


class NodeRegistrationError(RuntimeError):
    """Raised when node metadata cannot be collected."""


_REMOTE_FACTS_SCRIPT = textwrap.dedent(
    """
    import json
    import socket
    import subprocess

    result = {
        "hostname": None,
        "internal_ip": None,
        "interfaces": [],
        "gpus": [],
        "warnings": [],
        "error": None,
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

    return NodeFacts(
        hostname=payload.get('hostname'),
        internal_ip=payload.get('internal_ip'),
        network=payload.get('interfaces') or [],
        gpus=payload.get('gpus') or [],
        warnings=[w for w in payload.get('warnings', []) if w],
        error=payload.get('error'),
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
