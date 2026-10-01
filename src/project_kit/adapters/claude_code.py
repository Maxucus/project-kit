"""Claude project enablement with machine paths isolated in settings.local.json."""
from pathlib import Path
from . import AdapterPlan, common_observe, encode, marketplace_name, native, runtime_root
from ..models import Bundle


def plan(project: Path, bundle: Bundle, baseline: dict[str, bytes] | None = None) -> AdapterPlan:
    name = marketplace_name(bundle)
    base = runtime_root(project, bundle)
    market = {'name': name, 'owner': {'name': 'Project Kit'},
              'plugins': [{'name': p.name, 'source': f'./plugins/{p.name}'} for p in bundle.packages]}
    enabled = {f'{p.name}@{name}': True for p in bundle.packages}
    try:
        for row in native.inventory('claude-code', project):
            if row['name'] in {p.name for p in bundle.packages} and row['id'] not in enabled:
                enabled[row['id']] = False
    except (OSError, ValueError, native.NativeError):
        pass
    local = {'extraKnownMarketplaces': {name: {'source': {'source': 'directory', 'path': str(base.resolve())}}}}
    files = {f'.project-kit/runtime/{bundle.digest}/.claude-plugin/marketplace.json': encode(market),
             '.claude/settings.json': encode({'enabledPlugins': enabled}), '.claude/settings.local.json': encode(local)}
    ownership = {'.claude/settings.json': {'kind': 'json', 'paths': [['enabledPlugins', k] for k in enabled]},
                 '.claude/settings.local.json': {'kind': 'json', 'paths': [['extraKnownMarketplaces', name]]}}
    return AdapterPlan(files, {f'{p.name}@{name}': p.digest for p in bundle.packages}, ownership)


def observe(project: Path, bundle: Bundle, runtime: bool):
    return common_observe('claude-code', project, bundle, runtime)
