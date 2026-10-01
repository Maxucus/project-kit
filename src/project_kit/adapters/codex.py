"""Codex repo marketplace and effective plugin enablement."""
import json
from pathlib import Path
import tomlkit
from . import AdapterPlan, common_observe, encode, marketplace_name, native
from ..files import contained_path, MergeConflict
from ..models import Bundle


def plan(project: Path, bundle: Bundle, baseline: dict[str, bytes] | None = None) -> AdapterPlan:
    name = marketplace_name(bundle)
    relative = '.agents/plugins/marketplace.json'
    target = contained_path(project, relative)
    existing = json.loads(target.read_text()) if target.exists() else {}
    previous = json.loads(baseline.get(relative, b'{}')) if baseline else {}
    if existing and existing.get('name') != name and existing != previous:
        raise MergeConflict('Existing Codex marketplace has another name; preserve it and resolve catalog ownership explicitly')
    names = {p.name for p in bundle.packages}
    entries = [e for e in existing.get('plugins', []) if e.get('name') not in names]
    entries += [{'name': p.name, 'source': {'source': 'local', 'path': f'./.project-kit/runtime/{bundle.digest}/plugins/{p.name}'},
                 'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}} for p in bundle.packages]
    marketplace = {**existing, 'name': name, 'interface': existing.get('interface', {'displayName': 'Project Kit'}), 'plugins': entries}
    settings = tomlkit.document()
    settings['plugins'] = {}
    try:
        rows = native.inventory('codex', project)
    except (OSError, ValueError, native.NativeError):
        rows = []
    for row in rows:
        if row['name'] in names and row['id'] != f"{row['name']}@{name}":
            settings['plugins'][row['id']] = {'enabled': False}
    for package in bundle.packages:
        settings['plugins'][f'{package.name}@{name}'] = {'enabled': True}
    ownership = {'.codex/config.toml': {'kind': 'toml', 'paths': [['plugins', k, 'enabled'] for k in settings['plugins']]}}
    return AdapterPlan({relative: encode(marketplace), '.codex/config.toml': tomlkit.dumps(settings).encode()},
                       {f'{p.name}@{name}': p.digest for p in bundle.packages}, ownership)


def observe(project: Path, bundle: Bundle, runtime: bool):
    return common_observe('codex', project, bundle, runtime)
