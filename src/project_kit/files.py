"""Guarded paths, atomic replacement, and three-way merges of owned content."""
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
from typing import Literal
import tomlkit


class MergeConflict(ValueError):
    """A managed block/key was changed locally; leave all bytes untouched."""


def visible_state(root: Path) -> dict[str, tuple[int, int]]:
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-co', '--exclude-standard', '-z'],
                            capture_output=True, check=True, timeout=15)
    state = {}
    for relative in filter(None, result.stdout.decode().split('\0')):
        path = contained_path(root, relative)
        if path.exists():
            stat = path.lstat()
            state[relative] = (stat.st_size, stat.st_mtime_ns)
    return state


def contained_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or '..' in path.parts or '.git' in path.parts:
        raise ValueError(f'unsafe project path: {relative}')
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f'path outside project: {relative}')
    return target


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _block(content: bytes):
    pattern = rb'(?m)^(?:<!-- BEGIN PROJECT-KIT -->|# BEGIN PROJECT-KIT)\r?\n.*?^(?:<!-- END PROJECT-KIT -->|# END PROJECT-KIT)(?:\r?\n|$)'
    matches = list(re.finditer(pattern, content, re.S | re.M))
    if len(matches) > 1 or (b'BEGIN PROJECT-KIT' in content and not matches):
        raise MergeConflict('PROJECT-KIT: malformed or duplicate block')
    return matches[0] if matches else None


_MISSING = object()


def _get(data, keys):
    for key in keys:
        if not isinstance(data, dict) and not hasattr(data, 'get'):
            raise MergeConflict(f'expected mapping at {keys}')
        data = data.get(key, _MISSING)
        if data is _MISSING:
            break
    return data


def _put(data, keys, value):
    for key in keys[:-1]:
        if key not in data:
            data[key] = {}
        data = data[key]
        if not hasattr(data, 'get'):
            raise MergeConflict(f'expected mapping at {keys}')
    if value is _MISSING:
        data.pop(keys[-1], None)
    else:
        data[keys[-1]] = value


def merge_owned(current: bytes, baseline: bytes, desired: bytes,
                kind: Literal['markdown', 'json', 'toml'], owned: tuple[tuple[str, ...], ...]) -> bytes:
    if kind == 'markdown':
        old, local, new = (_block(c) for c in (baseline, current, desired))
        old_bytes, local_bytes, new_bytes = (m.group() if m else b'' for m in (old, local, new))
        if local_bytes == new_bytes:
            return current
        if local_bytes != old_bytes:
            raise MergeConflict('PROJECT-KIT block changed locally')
        if local:
            return current[:local.start()] + new_bytes + current[local.end():]
        return current + (b'\n' if current and not current.endswith(b'\n') else b'') + new_bytes
    parser = json.loads if kind == 'json' else tomlkit.parse
    old, local, new = (parser(c.decode() or '{}') if kind == 'json' else parser(c.decode())
                       for c in (baseline, current, desired))
    changed = False
    for keys in owned:
        before, present, after = (_get(d, keys) for d in (old, local, new))
        if present == after:
            continue
        if present != before:
            raise MergeConflict(f'key changed locally: {keys}')
        _put(local, keys, after)
        changed = True
    if not changed:
        return current
    return ((json.dumps(local, ensure_ascii=False, indent=2) + '\n') if kind == 'json' else tomlkit.dumps(local)).encode()


def owned_digest(content: bytes, kind: str, paths: tuple[tuple[str, ...], ...]) -> str:
    """Ignore project additions when auditing a mixed file."""
    from .sources import digest_data
    if kind == 'markdown':
        match = _block(content)
        return digest_data(match.group().decode() if match else '')
    data = json.loads(content) if kind == 'json' else tomlkit.parse(content.decode())
    values = []
    for keys in paths:
        value = _get(data, keys)
        values.append([list(keys), None if value is _MISSING else value, value is not _MISSING])
    return digest_data(values)
