"""Strict, non-executable YAML inputs. Unknown fields are mistakes, not defaults."""
from dataclasses import fields
import json
from pathlib import Path
import re
import yaml
from .models import KitConfig, ProjectIntent, Lock


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str):
            raise ValueError('YAML keys must be strings')
        if key in result:
            raise ValueError(f'duplicate YAML key: {key}')
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def read_yaml(path: Path) -> dict:
    try:
        data = yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueLoader)
        if not isinstance(data, dict):
            raise ValueError('expected a mapping')
        json.dumps(data, allow_nan=False)
        return data
    except (yaml.YAMLError, TypeError, OverflowError, ValueError) as exc:
        raise ValueError(f'{path}: {exc}') from exc


def _keys(data, cls):
    unknown = set(data) - {f.name for f in fields(cls)}
    if unknown:
        raise ValueError(f'unknown fields: {sorted(unknown)}')


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{field}: expected nonempty text')
    return value


def _strings(value, field, nonempty=True):
    if not isinstance(value, list) or (nonempty and not value):
        raise ValueError(f'{field}: expected a list of strings')
    return tuple(_text(x, field) for x in value)


def config_from_data(data: dict) -> KitConfig:
    _keys(data, KitConfig)
    if type(data.get('schema')) is not int or data['schema'] != 1:
        raise ValueError('schema: expected 1')
    profile = _text(data.get('profile'), 'profile')
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', profile):
        raise ValueError('profile: invalid name')
    agents = _strings(data.get('agents'), 'agents')
    if len(set(agents)) != len(agents) or set(agents) - {'codex', 'claude-code'}:
        raise ValueError('agents: expected unique codex/claude-code values')
    overrides = data.get('overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('overrides: expected mapping')
    return KitConfig(1, profile, agents, overrides)


def load_config(path: Path) -> KitConfig:
    return config_from_data(read_yaml(path))


def intent_from_data(data: dict) -> ProjectIntent:
    _keys(data, ProjectIntent)
    values = {k: _text(data.get(k), k) for k in ('name', 'goal', 'scope', 'task_source')}
    for key in ('users', 'constraints', 'decisions', 'success'):
        values[key] = _strings(data.get(key), key, nonempty=key != 'constraints')
    commands = data.get('commands')
    if not isinstance(commands, dict) or not commands:
        raise ValueError('commands: expected named argv lists')
    values['commands'] = {_text(k, 'commands'): _strings(v, f'commands.{k}') for k, v in commands.items()}
    generation = data.get('generation')
    if not isinstance(generation, list):
        raise ValueError('generation: expected list of argv lists')
    values['generation'] = tuple(_strings(v, 'generation') for v in generation)
    return ProjectIntent(**values)


def load_intent(path: Path) -> ProjectIntent:
    return intent_from_data(read_yaml(path))


def lock_from_data(data: dict) -> Lock:
    _keys(data, Lock)
    if type(data.get('schema')) is not int or data['schema'] != 1:
        raise ValueError('lock.schema: expected 1')
    for key in ('kit_source', 'kit_commit', 'profile_digest'):
        _text(data.get(key), f'lock.{key}')
    if not re.fullmatch(r'[0-9a-f]{40,64}', data['kit_commit']):
        raise ValueError('lock.kit_commit: expected full commit')
    for key in ('profile', 'render_inputs', 'package_digests', 'managed_hashes', 'owned_settings'):
        if not isinstance(data.get(key), dict):
            raise ValueError(f'lock.{key}: expected mapping')
    for key in ('package_digests', 'managed_hashes'):
        if any(not isinstance(v, str) or not re.fullmatch(r'[0-9a-f]{64}', v) for v in data[key].values()):
            raise ValueError(f'lock.{key}: expected sha256 values')
    intent_from_data(data['render_inputs'])
    return Lock(**data)


def read_lock(path: Path) -> Lock:
    return lock_from_data(read_yaml(path))
