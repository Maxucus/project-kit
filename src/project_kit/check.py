"""Read-only audits, including verification against a not-yet-applied candidate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Sequence
from .adapters import adapter
from .config import load_config, read_lock, intent_from_data
from .files import contained_path, owned_digest
from .models import Bundle, Check, Lock, Package, Report, Status
from .sources import digest_data, verify_bundle


def aggregate(checks: Sequence[Check]) -> Status:
    if not checks:
        return 'incomplete'
    order = {'ready': 0, 'incomplete': 1, 'drift': 2, 'incompatible': 3}
    return max((c.status for c in checks), key=order.__getitem__)


def bundle_for_lock(project: Path, lock: Lock) -> Bundle:
    digest = digest_data({'commit': lock.kit_commit, 'profile': lock.profile, 'packages': lock.package_digests})
    directory = contained_path(project, f'.project-kit/runtime/{digest}')
    data = json.loads((directory / 'bundle.json').read_text())
    if data['kit_commit'] != lock.kit_commit or data['profile'] != lock.profile or data['digest'] != digest:
        raise ValueError('Local bundle metadata differs from lock')
    packages = tuple(Package(p['name'], contained_path(directory, p['root']), p['commit'], p['digest']) for p in data['packages'])
    if {p.name: p.digest for p in packages} != lock.package_digests:
        raise ValueError('Local package declarations differ from lock')
    return Bundle(lock.kit_source, lock.kit_commit, digest, lock.profile, packages)


def audit_prompts(project: Path, bundle: Bundle) -> tuple[Check, ...]:
    checks = []
    required = ['AGENTS.md', 'CLAUDE.md', 'docs/project.md', 'docs/architecture.md',
                'docs/development.md', 'docs/decisions/0001-stack.md']
    files = [contained_path(project, p) for p in required]
    files += list(contained_path(project, '.project-kit/core').glob('*.md'))
    own = next(p.root for p in bundle.packages if p.name == 'project-kit')
    files += list((own / 'skills').rglob('*.md'))
    for path in files:
        if not path.is_file() or not path.read_text().strip():
            checks.append(Check('context', 'incomplete', f'Missing/empty context: {path.name}'))
            continue
        text = path.read_text()
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
            if '://' in target or target.startswith('#'):
                continue
            if not (path.parent / target.split('#')[0]).exists():
                checks.append(Check('context-link', 'incomplete', f'{path.name}: {target}'))
    initial = [contained_path(project, p) for p in ('AGENTS.md', '.project-kit/core/entry.md')]
    if all(p.is_file() for p in initial):
        words = sum(len(p.read_text().split()) for p in initial)
        checks.append(Check('prompt-budget', 'ready', f'Startup context: {words}/400 words' + ('; review and justify excess' if words > 400 else '')))
    for path in (own / 'skills').glob('*/SKILL.md'):
        words = len(path.read_text().split('---', 2)[-1].split())
        checks.append(Check('prompt-budget', 'ready', f'{path.parent.name}: {words}/250 words' + ('; review and justify excess' if words > 250 else '')))
    if not checks:
        checks.append(Check('context', 'incomplete', 'No context was audited'))
    return tuple(checks)


def check_project(project: Path, runtime: bool, expected: Lock | None = None) -> Report:
    project = project.resolve()
    started = datetime.now(timezone.utc)
    checks = []
    try:
        lock = expected or read_lock(contained_path(project, 'project-kit.lock.yaml'))
        intent_from_data(lock.render_inputs)
        from dataclasses import asdict
        config = json.loads(json.dumps(asdict(load_config(contained_path(project, 'project-kit.yaml')))))
        checks.append(Check('profile', 'ready' if config == lock.profile['_config'] and digest_data(lock.profile) == lock.profile_digest else 'drift',
                            'Declared configuration compared with applied profile'))
        for relative, digest in lock.managed_hashes.items():
            path = contained_path(project, relative)
            if not path.is_file():
                checks.append(Check('managed-file', 'incomplete', f'Missing: {relative}'))
                continue
            content = path.read_bytes()
            if relative in lock.owned_settings:
                entry = lock.owned_settings[relative]
                actual = owned_digest(content, entry['kind'], tuple(tuple(p) for p in entry['paths']))
            else:
                actual = hashlib.sha256(content).hexdigest()
            checks.append(Check('managed-file', 'ready' if actual == digest else 'drift', relative))
        bundle = bundle_for_lock(project, lock)
        checks.extend(verify_bundle(bundle))
        checks.extend(audit_prompts(project, bundle))
        for agent in bundle.profile['agents']:
            check, observation = adapter(agent).observe(project, bundle, runtime)
            if check.status == 'ready':
                valid = (observation is not None and observation.project == str(project)
                         and observation.profile_digest == lock.profile_digest
                         and observation.observed_packages == lock.package_digests
                         and bool(observation.client_version)
                         and datetime.fromisoformat(observation.confirmed_at) >= started)
                if not valid:
                    check = Check(f'agent:{agent}', 'incomplete', 'Stale or unrelated runtime observation')
            checks.append(check)
    except FileNotFoundError as exc:
        checks.append(Check('setup', 'incomplete', f'Missing {Path(exc.filename).name if exc.filename else "installation"}; run init to restore local setup'))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        checks.append(Check('configuration', 'incompatible', str(exc)))
    return Report(str(project), aggregate(checks), tuple(checks))
