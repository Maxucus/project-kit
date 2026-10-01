"""Render accepted decisions and resume initialization without replaying generators."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
from string import Template
import yaml
from .files import contained_path, merge_owned, write_atomic, owned_digest
from .models import Bundle, Check, Lock, Package, ProjectIntent, Report
from .sources import digest_data, verify_bundle

MIXED = ('AGENTS.md', 'CLAUDE.md', '.gitignore')


def json_data(value):
    return json.loads(json.dumps(asdict(value), default=str, ensure_ascii=False))


def bundle_from_data(data: dict) -> Bundle:
    return Bundle(data['kit_source'], data['kit_commit'], data['digest'], data['profile'],
                  tuple(Package(p['name'], Path(p['root']), p['commit'], p['digest']) for p in data['packages']))


def render_project(intent: ProjectIntent, bundle: Bundle) -> dict[str, bytes]:
    root = next(p.root for p in bundle.packages if p.name == 'project-kit')
    values = asdict(intent)
    for key in ('users', 'constraints', 'decisions', 'success'):
        values[key] = '\n'.join(f'- {line}' for line in values[key]) or 'Нет дополнительных ограничений.'
    values['commands'] = '\n'.join(f'- {name}: `{json.dumps(argv, ensure_ascii=False)}`' for name, argv in intent.commands.items())
    values['generation'] = '\n'.join(f'- `{json.dumps(argv, ensure_ascii=False)}`' for argv in intent.generation) or 'Генерация не требуется.'
    values['config_yaml'] = yaml.safe_dump(bundle.profile['_config'], allow_unicode=True, sort_keys=False).rstrip()
    result = {}
    for source in sorted((root / 'templates/project').rglob('*')):
        if source.is_file():
            result[source.relative_to(root / 'templates/project').as_posix()] = Template(source.read_text()).substitute(values).encode()
    for source in sorted((root / 'core').glob('*.md')):
        result[f'.project-kit/core/{source.name}'] = source.read_bytes()
    return result


def make_lock(intent: ProjectIntent, bundle: Bundle, rendered: dict[str, bytes],
              ownership: dict | None = None) -> Lock:
    ownership = dict(ownership or {})
    for relative in MIXED:
        ownership[relative] = {'kind': 'markdown', 'paths': [['PROJECT-KIT']]}
    hashes = {}
    for relative, data in rendered.items():
        if relative in ownership:
            entry = ownership[relative]
            hashes[relative] = owned_digest(data, entry['kind'], tuple(tuple(p) for p in entry['paths']))
        elif relative.startswith('.project-kit/core/'):
            hashes[relative] = hashlib.sha256(data).hexdigest()
    return Lock(1, bundle.kit_source, bundle.kit_commit, bundle.profile, digest_data(bundle.profile),
                json_data(intent), {p.name: p.digest for p in bundle.packages}, hashes, ownership)


def initialize(project: Path, intent: ProjectIntent, bundle: Bundle) -> Report:
    project = project.resolve()
    changed = []
    try:
        if any(c.status != 'ready' for c in verify_bundle(bundle)):
            return Report(str(project), 'drift', (Check('packages', 'drift', 'Prepared package changed'),))
        rendered = render_project(intent, bundle)
        operation = contained_path(project, '.project-kit/operation.json')
        state = json.loads(operation.read_text()) if operation.exists() else {}
        identity = digest_data({'intent': json_data(intent), 'bundle': bundle.digest})
        if state and state.get('identity') != identity:
            return Report(str(project), 'incompatible', (Check('operation', 'incompatible', 'Pending operation has different inputs'),))
        writes = {}
        for relative, desired in rendered.items():
            target = contained_path(project, relative)
            if target.exists():
                current = target.read_bytes()
                if relative in MIXED:
                    desired = merge_owned(current, desired if state else b'', desired, 'markdown', (('PROJECT-KIT',),))
                elif relative.startswith('.project-kit/core/'):
                    if current != desired:
                        raise ValueError(f'managed file changed: {relative}')
                else:
                    continue  # Product-owned file: create once.
                if current == desired:
                    continue
            writes[relative] = desired
        project.mkdir(parents=True, exist_ok=True)
        if not (project / '.git').exists():
            subprocess.run(['git', 'init', '-q', '-b', 'main', str(project)], check=True, capture_output=True)
        if not state:
            state = {'schema': 1, 'identity': identity, 'bundle': json_data(bundle),
                     'intent': json_data(intent), 'generated': 0, 'candidate': json_data(make_lock(intent, bundle, rendered))}
            write_atomic(operation, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
        for relative, data in writes.items():
            write_atomic(contained_path(project, relative), data)
            changed.append(relative)
        for index, argv in enumerate(intent.generation):
            if index < state['generated']:
                continue
            result = subprocess.run(list(argv), cwd=project, capture_output=True, timeout=300)
            if result.returncode:
                raise ValueError(f'generation step {index + 1} failed (exit {result.returncode}); resolve before resuming init')
            state['generated'] = index + 1
            write_atomic(operation, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
        return Report(str(project), 'incomplete', (Check('agents', 'incomplete', 'Connect and verify native agent runtimes'),), tuple(changed))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        return Report(str(project), 'incomplete', (Check('init', 'incomplete', str(exc)),), tuple(changed))


def restore(project: Path) -> Report:
    """Resume pending init or restore only local installation from an applied lock."""
    from .config import read_lock, intent_from_data
    from .sources import restore_bundle
    project = project.resolve()
    operation = contained_path(project, '.project-kit/operation.json')
    if operation.exists():
        state = json.loads(operation.read_text())
        return initialize(project, intent_from_data(state['intent']), bundle_from_data(state['bundle']))
    lock = read_lock(contained_path(project, 'project-kit.lock.yaml'))
    bundle = restore_bundle(lock, contained_path(project, '.project-kit/runtime'))
    intent = intent_from_data(lock.render_inputs)
    # Mark generation complete before resuming: a restored checkout owns its code.
    state = {'schema': 1, 'identity': digest_data({'intent': json_data(intent), 'bundle': bundle.digest}),
             'bundle': json_data(bundle), 'intent': json_data(intent), 'generated': len(intent.generation),
             'candidate': json_data(lock), 'restore': True}
    write_atomic(operation, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
    return Report(str(project), 'incomplete', (Check('agents', 'incomplete', 'Restore native agent configuration'),))
