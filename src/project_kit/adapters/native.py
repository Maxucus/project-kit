"""Bounded native discovery. Never prints client configuration, auth, or raw logs."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import time


class NativeError(ValueError):
    pass


def executable(agent):
    return 'codex' if agent == 'codex' else 'claude'


def run(argv, project, timeout=40):
    try:
        result = subprocess.run(argv, cwd=project, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise NativeError(f'{argv[0]} timed out') from exc
    if result.returncode:
        raise NativeError(f'{argv[0]} {argv[1]} failed (exit {result.returncode})')
    return result.stdout


def version(agent, project):
    return run([executable(agent), '--version'], project).strip()


def inventory(agent, project):
    data = json.loads(run([executable(agent), 'plugin', 'list', '--json'], project))
    if agent == 'codex':
        return [{'id': r['pluginId'], 'name': r['name'], 'enabled': r['enabled']}
                for r in data['installed']]
    return [{'id': r['id'], 'name': r['id'].split('@')[0], 'enabled': r['enabled'], 'root': r['installPath']}
            for r in data]


def _stop(process):
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    for stream in (process.stdin, process.stdout):
        if stream:
            stream.close()


class JsonLines:
    """Keep framing bytes ourselves: TextIO can hide unread lines from select()."""
    def __init__(self, stream):
        self.stream = stream
        self.buffer = b''
        self.selector = selectors.DefaultSelector()
        self.selector.register(stream, selectors.EVENT_READ)

    def close(self):
        self.selector.close()

    def receive(self, deadline):
        while b'\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise NativeError('Native JSON response timed out')
            chunk = os.read(self.stream.fileno(), 65536)
            if not chunk:
                raise NativeError('Native response stream closed before evidence arrived')
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b'\n', 1)
        return json.loads(line)


class CodexRPC:
    def __init__(self, project):
        self.process = subprocess.Popen(['codex', 'app-server', '--stdio'], cwd=project,
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.reader = JsonLines(self.process.stdout)
        self.serial = 0

    def __enter__(self):
        try:
            self.call('initialize', {'clientInfo': {'name': 'project-kit', 'version': '0.1.0'}, 'capabilities': {'experimentalApi': True}})
            self.process.stdin.write(b'{"method":"initialized"}\n')
            self.process.stdin.flush()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        self.reader.close()
        _stop(self.process)

    def call(self, method, params):
        self.serial += 1
        self.process.stdin.write((json.dumps({'id': self.serial, 'method': method, 'params': params}) + '\n').encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            message = self.reader.receive(deadline)
            if message.get('id') != self.serial:
                continue
            if 'error' in message:
                raise NativeError(f'Codex API {method} unavailable')
            return message['result']
        raise NativeError(f'Codex API {method} timed out')


def _plugin_root(skill_path, agent):
    marker = '.codex-plugin' if agent == 'codex' else '.claude-plugin'
    for parent in Path(skill_path).parents:
        if (parent / marker / 'plugin.json').is_file():
            return parent
    raise NativeError('Native skill has no attributable plugin root')


def _selected_names(project, agent='codex'):
    from ..files import contained_path
    if agent == 'claude-code':
        settings = json.loads(contained_path(project, '.claude/settings.local.json').read_text())
        enabled = json.loads(contained_path(project, '.claude/settings.json').read_text()).get('enabledPlugins', {})
        names = set()
        for name, entry in settings.get('extraKnownMarketplaces', {}).items():
            if not name.startswith('project-kit-') or not any(value and key.endswith('@' + name) for key, value in enabled.items()):
                continue
            directory = Path(entry['source']['path'])
            relative = directory.relative_to(project.resolve())
            catalog = json.loads(contained_path(project, str(relative / '.claude-plugin/marketplace.json')).read_text())
            names.update(p['name'] for p in catalog['plugins'])
        return names
    catalog = json.loads(contained_path(project, '.agents/plugins/marketplace.json').read_text())
    return {p['name'] for p in catalog['plugins'] if p.get('source', {}).get('path', '').startswith('./.project-kit/runtime/')}


def _codex_runtime(project):
    with CodexRPC(project) as rpc:
        config = rpc.call('config/read', {'cwd': str(project.resolve()), 'includeLayers': True})
        if any(layer.get('name', {}).get('type') == 'project' and layer.get('disabledReason') for layer in config.get('layers') or []):
            raise NativeError('Codex project config is disabled: open this project in Codex, review project trust, then retry init')
        # Discovery must not be confused with installation.
        installed = {r['id'] for r in inventory('codex', project)}
        names = _selected_names(project)
        skills_data = rpc.call('skills/list', {'cwds': [str(project.resolve())], 'forceReload': True})
        hooks_data = rpc.call('hooks/list', {'cwds': [str(project.resolve())]})
        plugins_data = rpc.call('plugin/list', {'cwds': [str(project.resolve())], 'marketplaceKinds': ['local']})
        skills = [s for entry in skills_data['data'] for s in entry['skills'] if s['enabled']]
        hooks = [h for entry in hooks_data['data'] for h in entry['hooks']]
        errors = [e for data in (skills_data, hooks_data) for entry in data['data'] for e in entry['errors']]
        packages = []
        for market in plugins_data['marketplaces']:
            for row in market['plugins']:
                if row['name'] not in names or not row['enabled'] or not row['installed'] or row['id'] not in installed:
                    continue
                paths = [s['path'] for s in skills if s.get('pluginId') == row['id']]
                if not paths:
                    continue
                detail = rpc.call('plugin/read', {'pluginName': row['name'], 'marketplacePath': market['path']})
                detail = detail.get('plugin', detail)
                declared_mcp = detail.get('mcpServers', [])
                statuses = []
                if declared_mcp:
                    data = rpc.call('mcpServerStatus/list', {})
                    statuses = [s for s in data['data'] if s.get('pluginId') == row['id']]
                packages.append({'id': row['id'], 'name': row['name'], 'enabled': True,
                                 'root': str(_plugin_root(paths[0], 'codex')), 'skills': paths,
                                 'hooks': [{'ready': h['enabled'] and h['trustStatus'] in ('trusted', 'managed')}
                                           for h in hooks if h.get('pluginId') == row['id']],
                                 'mcp': [{'ready': any(s['name'] == server and s.get('runtimeStatus') == 'connected'
                                                      and bool(s.get('serverInfo')) and not s.get('toolsError')
                                                      for s in statuses)} for server in declared_mcp]})
        return {'packages': packages, 'errors': errors}


def _claude_runtime(project):
    rows = inventory('claude-code', project)
    names = _selected_names(project, 'claude-code')
    process = subprocess.Popen(['claude', '-p', '--output-format', 'stream-json', '--verbose',
                                '--no-session-persistence', '--max-budget-usd', '0.01', '--permission-mode', 'plan',
                                'Reply OK without using tools.'], cwd=project, stdout=subprocess.PIPE,
                               stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    reader = JsonLines(process.stdout)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            event = reader.receive(deadline)
            if event.get('type') != 'system' or event.get('subtype') != 'init':
                continue
            loaded = event.get('skills', event.get('slash_commands', []))
            active = {p.get('name'): p for p in event.get('plugins', [])}
            packages = []
            for row in rows:
                if row['name'] not in names or not row['enabled'] or not (row['id'] in active or row['name'] in active):
                    continue
                root = Path(row['root'])
                run(['claude', 'plugin', 'validate', str(root)], project)
                paths = [str(p) for p in (root / 'skills').glob('*/SKILL.md')
                         if f"{row['name']}:{p.parent.name}" in loaded or p.parent.name in loaded]
                manifest = json.loads((root / '.claude-plugin/plugin.json').read_text())
                has_hooks = bool(manifest.get('hooks')) or (root / 'hooks/hooks.json').exists()
                # Init confirms skill discovery; it does not attest all hook registrations.
                packages.append({**row, 'skills': paths, 'hooks': [{'ready': False}] if has_hooks else [],
                                 'mcp': [{'ready': s.get('status') == 'connected'} for s in event.get('mcp_servers', [])
                                         if s.get('name', '').startswith(f"plugin:{row['name']}:")]})
            return {'packages': packages, 'errors': []}
        raise NativeError('Claude initialization evidence unavailable')
    finally:
        reader.close()
        _stop(process)


def runtime(agent, project):
    return _codex_runtime(project) if agent == 'codex' else _claude_runtime(project)
