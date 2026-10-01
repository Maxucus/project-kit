"""Project-scoped configuration; no writes to user/global agent settings."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from . import native
from ..files import contained_path, merge_owned, write_atomic, MergeConflict
from ..models import AgentId, Bundle, Check
from ..sources import digest_data, digest_tree


@dataclass(frozen=True)
class AdapterPlan:
    files: dict[str, bytes]
    expected_packages: dict[str, str]
    ownership: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Observation:
    project: str
    agent: AgentId
    client_version: str
    profile_digest: str
    observed_packages: dict[str, str]
    loaded_skills: tuple[str, ...]
    capabilities: dict[str, bool]
    confirmed_at: str


def adapter(agent: AgentId):
    from . import codex, claude_code
    return {'codex': codex, 'claude-code': claude_code}[agent]


def marketplace_name(bundle: Bundle) -> str:
    return f'project-kit-{bundle.digest[:16]}'


def runtime_root(project: Path, bundle: Bundle) -> Path:
    return contained_path(project, f'.project-kit/runtime/{bundle.digest}')


def encode(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def materialize(project: Path, bundle: Bundle) -> None:
    target = runtime_root(project, bundle)
    # Verify every package before any copy, including a pre-existing destination.
    for package in bundle.packages:
        if digest_tree(package.root) != package.digest:
            raise ValueError(f'drift: source package {package.name}')
        destination = contained_path(project, f'.project-kit/runtime/{bundle.digest}/plugins/{package.name}')
        if destination.exists() and digest_tree(destination) != package.digest:
            raise ValueError(f'drift: local package {package.name}')
    for package in bundle.packages:
        destination = target / 'plugins' / package.name
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(package.root, destination, symlinks=True)


def configure(project: Path, bundle: Bundle, baseline: dict[str, bytes] | None = None) -> tuple[dict[str, bytes], dict, dict[str, bytes]]:
    """Preflight all mixed files before applying either adapter."""
    baseline = baseline or {}
    writes, ownership, expected = {}, {}, {}
    for agent in bundle.profile['agents']:
        planned = adapter(agent).plan(project, bundle, baseline=baseline)
        for relative, desired in planned.files.items():
            expected[relative] = desired
            target = contained_path(project, relative)
            entry = planned.ownership.get(relative)
            current = target.read_bytes() if target.exists() else b''
            if entry:
                ownership[relative] = entry
                desired = merge_owned(current, baseline.get(relative, b''), desired, entry['kind'],
                                      tuple(tuple(p) for p in entry['paths']))
            elif current and current != desired and baseline.get(relative) != current:
                raise MergeConflict(f'managed configuration changed: {relative}')
            if current != desired:
                writes[relative] = desired
    materialize(project, bundle)
    for relative, data in writes.items():
        write_atomic(contained_path(project, relative), data)
    return writes, ownership, expected


def common_observe(agent: AgentId, project: Path, bundle: Bundle, runtime: bool):
    name = f'agent:{agent}'
    for capability in ('hooks', 'mcp'):
        if bundle.profile.get(capability) not in (True, False, 'native'):
            return Check(name, 'incompatible', f'Unsupported {capability} policy'), None
    if not runtime:
        return Check(name, 'incomplete', 'Runtime not observed; rerun check --runtime'), None
    try:
        client_version = native.version(agent, project)
        snapshot = native.runtime(agent, project)
        if snapshot.get('errors'):
            return Check(name, 'incomplete', 'Native client reported configuration/load errors'), None
        rows = snapshot['packages']
        observed, skills = {}, []
        expected_ids = {f'{p.name}@{marketplace_name(bundle)}' for p in bundle.packages}
        names = {p.name for p in bundle.packages}
        if any(r['enabled'] and r['name'] in names and r['id'] not in expected_ids for r in rows):
            return Check(name, 'drift', 'Another version of a selected package is active; disable it in project settings'), None
        for package in bundle.packages:
            identifier = f'{package.name}@{marketplace_name(bundle)}'
            matches = [r for r in rows if r['id'] == identifier and r['enabled']]
            if len(matches) != 1:
                return Check(name, 'incomplete', f'{identifier}: install/enable in this project and restart client'), None
            row = matches[0]
            root = Path(row['root'])
            if not root.is_dir() or digest_tree(root) != package.digest:
                return Check(name, 'drift', f'{identifier}: installed payload differs from pinned source'), None
            expected = {p.relative_to(package.root).as_posix() for p in (package.root / 'skills').glob('*/SKILL.md')}
            actual = {Path(p).resolve().relative_to(root.resolve()).as_posix() for p in row['skills']}
            if not expected or not expected.issubset(actual):
                return Check(name, 'incomplete', f'{identifier}: native skill discovery is incomplete'), None
            for capability in ('hooks', 'mcp'):
                entries = row.get(capability)
                if entries is None:
                    return Check(name, 'incomplete', f'{identifier}: {capability} state unavailable'), None
                policy = bundle.profile[capability]
                if policy is False and entries:
                    return Check(name, 'incompatible', f'{identifier}: profile disables bundled {capability}; select a supported package/profile'), None
                if policy is not False and any(not e.get('ready') for e in entries):
                    return Check(name, 'incomplete', f'{identifier}: review/trust or configure native {capability}'), None
            observed[package.name] = package.digest
            skills.extend(f'{package.name}:{Path(p).parent.name}' for p in row['skills'])
        observation = Observation(str(project.resolve()), agent, client_version, digest_data(bundle.profile),
                                  observed, tuple(sorted(skills)), {'skills': True, 'hooks': True, 'mcp': True},
                                  datetime.now(timezone.utc).isoformat())
        return Check(name, 'ready', f'{client_version}: pinned packages discovered by native client'), observation
    except FileNotFoundError:
        return Check(name, 'incomplete', f'{agent} is not installed'), None
    except (ValueError, OSError, KeyError, TypeError, native.NativeError) as exc:
        return Check(name, 'incomplete', f'Native observation unavailable: {exc}'), None
