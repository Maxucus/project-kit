"""Tracked Git snapshots and content-addressed package assembly."""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from .config import read_yaml, config_from_data
from .models import Bundle, Check, KitConfig, Package, Lock
from .files import contained_path


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError(f'git {args[0]} failed in {root}')
    return result.stdout.strip()


def digest_data(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if '.git' in path.relative_to(root).parts:
            continue
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'symlink escapes package: {relative}')
            data = os.readlink(path).encode()
            kind = b'L'
        elif path.is_file():
            data = path.read_bytes()
            kind = b'X' if path.stat().st_mode & 0o111 else b'F'
        else:
            continue
        for part in (relative.encode(), kind, data):
            digest.update(len(part).to_bytes(8, 'big'))
            digest.update(part)
    return digest.hexdigest()


def _snapshot(root: Path, target: Path) -> None:
    target.mkdir(parents=True)
    entries = git(root, 'ls-files', '-z').split('\0')
    for relative in filter(None, entries):
        source = root / relative
        if source.is_dir() and not source.is_symlink():  # gitlink, handled separately
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            if not source.resolve().is_relative_to(root.resolve()):
                raise ValueError(f'symlink escapes package: {relative}')
            destination.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, destination)


def _clean(root: Path) -> str:
    commit = git(root, 'rev-parse', 'HEAD')
    if git(root, 'status', '--porcelain', '--untracked-files=normal'):
        raise ValueError(f'dirty source: {root}')
    return commit


def prepare_bundle(kit: Path, config: KitConfig, cache: Path) -> Bundle:
    kit = kit.resolve()
    commit = _clean(kit)
    sources = {'project-kit': (kit, commit)}
    for record in git(kit, 'ls-tree', '-r', '-z', 'HEAD').split('\0'):
        if not record.startswith('160000 '):
            continue
        metadata, relative = record.split('\t', 1)
        pinned = metadata.split()[2]
        source = kit / relative
        if not (source / '.git').exists() or _clean(source) != pinned:
            raise ValueError(f'submodule not initialized at pinned commit: {relative}')
        sources[source.name] = (source, pinned)
    profile = read_yaml(kit / 'profiles' / f'{config.profile}.yaml')
    allowed = {'packages', 'workflows', 'hooks', 'mcp'}
    if set(config.overrides) - allowed:
        raise ValueError('overrides: unsupported key')
    profile.update(config.overrides)
    profile['agents'] = list(config.agents)
    profile['_config'] = json.loads(json.dumps(asdict(config)))
    names = profile.get('packages')
    if not isinstance(names, list) or not names or names[0] != 'project-kit' or len(names) != len(set(names)):
        raise ValueError('profile.packages: unique packages starting with project-kit required')
    if set(names) - sources.keys():
        raise ValueError('profile.packages: missing pinned source')
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=cache) as temporary:
        stage = Path(temporary)
        packages = []
        for name in names:
            source, pin = sources[name]
            root = stage / name
            _snapshot(source, root)
            packages.append(Package(name, root, pin, digest_tree(root)))
        digest = digest_data({'commit': commit, 'profile': profile, 'packages': {p.name: p.digest for p in packages}})
        final = contained_path(cache, digest)
        if final.exists():
            for package in packages:
                if digest_tree(contained_path(final, package.name)) != package.digest:
                    raise ValueError(f'drift in cached package: {package.name}')
        else:
            stage.rename(final)
        packages = tuple(Package(p.name, final / p.name, p.commit, p.digest) for p in packages)
    # A local checkout is a usable source; remote origin is preferable for another machine.
    origin = subprocess.run(['git', '-C', str(kit), 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout.strip()
    return Bundle(origin or str(kit), commit, digest, profile, packages)


def verify_bundle(bundle: Bundle) -> tuple[Check, ...]:
    results = []
    for package in bundle.packages:
        try:
            valid = package.root.is_dir() and digest_tree(package.root) == package.digest
        except (OSError, ValueError):
            valid = False
        results.append(Check(f'package:{package.name}', 'ready' if valid else 'drift', package.commit))
    return tuple(results)


def restore_bundle(lock: Lock, cache: Path) -> Bundle:
    """Resolve the applied commit without advancing a branch or a floating tag."""
    config = config_from_data(lock.profile['_config'])
    local = Path(lock.kit_source)
    if local.is_dir() and git(local, 'rev-parse', 'HEAD') == lock.kit_commit:
        source = local
    else:
        source = contained_path(cache, f'sources/{lock.kit_commit}')
        if not source.exists():
            source.parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(['git', 'clone', '--no-checkout', '--no-hardlinks', '--', lock.kit_source, str(source)],
                                    capture_output=True, timeout=120)
            if result.returncode:
                raise ValueError('Pinned kit source unavailable; configure Git access and retry init')
        for option in ('--absolute-git-dir', '--git-common-dir'):
            metadata = Path(git(source, 'rev-parse', option))
            metadata = metadata if metadata.is_absolute() else source / metadata
            if not metadata.resolve().is_relative_to(source.resolve()):
                raise ValueError('Cached Git metadata points outside source checkout')
        if Path(git(source, 'rev-parse', '--show-toplevel')).resolve() != source.resolve():
            raise ValueError('Cached Git worktree points outside source checkout')
        git(source, 'checkout', '--detach', lock.kit_commit)
        git(source, 'submodule', 'update', '--init', '--recursive')
    bundle = prepare_bundle(source, config, contained_path(cache, 'bundles'))
    if bundle.profile != lock.profile or {p.name: p.digest for p in bundle.packages} != lock.package_digests:
        raise ValueError('Restored source differs from applied lock')
    return bundle
