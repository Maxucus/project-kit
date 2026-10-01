"""Prepare an upgrade in a resumable Git worktree; never switch or merge the caller."""
import hashlib
import json
from pathlib import Path
import yaml
from .adapters import adapter, configure
from .check import bundle_for_lock, check_project
from .config import intent_from_data, load_config, read_lock
from .files import contained_path, merge_owned, owned_digest, write_atomic, MergeConflict
from .init import MIXED, json_data, make_lock, render_project
from .models import Check, Report
from .sources import git, prepare_bundle, restore_bundle


def _baseline(project, bundle, lock):
    result = render_project(intent_from_data(lock.render_inputs), bundle)
    catalog = contained_path(project, '.agents/plugins/marketplace.json')
    previous = {'.agents/plugins/marketplace.json': catalog.read_bytes()} if catalog.exists() else {}
    for agent in bundle.profile['agents']:
        result.update(adapter(agent).plan(project, bundle, baseline=previous).files)
    # Previously owned disable-overrides may disappear from today's native inventory.
    # Their baseline is determined by the pinned IDs, never by current local values.
    from .adapters import marketplace_name
    import tomlkit
    selected = {f'{p.name}@{marketplace_name(bundle)}' for p in bundle.packages}
    for relative, entry in lock.owned_settings.items():
        if relative not in ('.codex/config.toml', '.claude/settings.json'):
            continue
        data = {}
        for keys in entry['paths']:
            cursor = data
            for key in keys[:-1]:
                cursor = cursor.setdefault(key, {})
            identifier = keys[1]
            cursor[keys[-1]] = identifier in selected
        result[relative] = ((tomlkit.dumps(data) if entry['kind'] == 'toml' else json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())
    for relative, digest in lock.managed_hashes.items():
        content = result[relative]
        entry = lock.owned_settings.get(relative)
        actual = (owned_digest(content, entry['kind'], tuple(tuple(p) for p in entry['paths'])) if entry
                  else hashlib.sha256(content).hexdigest())
        if actual != digest:
            raise MergeConflict(f'Cannot reproduce original managed baseline: {relative}')
    return result


def prepare_upgrade(project: Path, target_kit: Path) -> Report:
    project = project.resolve()
    worktree = project
    changed = []
    try:
        dirty = git(project, 'status', '--porcelain')
        if dirty:
            return Report(str(project), 'incomplete', (Check('git', 'incomplete', f'Commit or resolve local changes first:\n{dirty}'),))
        lock = read_lock(contained_path(project, 'project-kit.lock.yaml'))
        try:
            original = bundle_for_lock(project, lock)
        except FileNotFoundError:
            original = restore_bundle(lock, contained_path(project, '.project-kit/runtime'))
        target = prepare_bundle(target_kit, load_config(project / 'project-kit.yaml'), contained_path(project, '.project-kit/runtime/bundles'))
        if original.digest == target.digest:
            return check_project(project, runtime=True)
        operation = contained_path(project, '.project-kit/operation.json')
        state = json.loads(operation.read_text()) if operation.exists() else {}
        source_head = git(project, 'rev-parse', 'HEAD')
        if state:
            if state.get('kind') != 'upgrade' or state.get('target') != target.digest or state.get('base') != source_head:
                return Report(str(project), 'incompatible', (Check('operation', 'incompatible', 'Another operation is pending; resolve its journal first'),))
            worktree = contained_path(project, state['worktree'])
            if not (worktree / '.git').exists():
                raise ValueError('Upgrade worktree is missing; inspect operation journal')
        else:
            relative = f'.project-kit/runtime/worktrees/{target.digest[:16]}'
            worktree = contained_path(project, relative)
            branch = f'chore/project-kit-{target.kit_commit[:12]}'
            git(project, 'worktree', 'add', '-b', branch, str(worktree), source_head)
            state = {'kind': 'upgrade', 'target': target.digest, 'base': source_head, 'worktree': relative, 'branch': branch}
            write_atomic(operation, (json.dumps(state, indent=2) + '\n').encode())
        baseline = _baseline(worktree, original, lock)
        intent = intent_from_data(lock.render_inputs)
        desired = render_project(intent, target)
        writes, removals = {}, []
        core_paths = {p for p in baseline if p.startswith('.project-kit/core/')}
        core_paths.update(p for p in desired if p.startswith('.project-kit/core/'))
        for relative in sorted(core_paths | set(MIXED)):
            path = contained_path(worktree, relative)
            current = path.read_bytes() if path.exists() else b''
            before, after = baseline.get(relative, b''), desired.get(relative, b'')
            if relative in MIXED:
                # Detect local changes even when this release leaves the block unchanged.
                if owned_digest(current, 'markdown', (('PROJECT-KIT',),)) not in (
                        owned_digest(before, 'markdown', (('PROJECT-KIT',),)), owned_digest(after, 'markdown', (('PROJECT-KIT',),))):
                    raise MergeConflict(f'Managed block changed locally: {relative}')
                after = merge_owned(current, before, after, 'markdown', (('PROJECT-KIT',),))
            elif current != before and current != after:
                raise MergeConflict(f'Managed file changed locally: {relative}')
            if current != after:
                if after:
                    writes[relative] = after
                else:
                    removals.append(relative)
        adapter_writes, ownership, expected = configure(worktree, target, baseline, lock.owned_settings)
        changed.extend(p for p in adapter_writes if not p.startswith('.project-kit/runtime/') and p != '.claude/settings.local.json')
        for relative, content in writes.items():
            write_atomic(contained_path(worktree, relative), content)
            changed.append(relative)
        for relative in removals:
            contained_path(worktree, relative).unlink()
            changed.append(relative)
        candidate = make_lock(intent, target, {**desired, **expected}, ownership)
        result = check_project(worktree, runtime=True, expected=candidate)
        if result.status == 'ready':
            path = worktree / 'project-kit.lock.yaml'
            content = yaml.safe_dump(json_data(candidate), allow_unicode=True, sort_keys=True).encode()
            if path.read_bytes() != content:
                write_atomic(path, content)
                changed.append('project-kit.lock.yaml')
        return Report(str(worktree), result.status, result.checks + (Check('review', result.status,
                      f'Review git diff in this worktree; after merge run project-kit init --project {project}'),), tuple(changed))
    except MergeConflict as exc:
        return Report(str(worktree), 'drift', (Check('merge', 'drift', str(exc)),), tuple(changed))
    except (ValueError, OSError, KeyError) as exc:
        return Report(str(worktree), 'incomplete', (Check('upgrade', 'incomplete', str(exc)),), tuple(changed))
