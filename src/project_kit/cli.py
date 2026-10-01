"""Command-line entry points. Output describes only the requested checkout."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence
from .config import load_config, load_intent
from .init import initialize, restore
from .files import contained_path, visible_state
from .sources import prepare_bundle


def _tree(paths):
    root = {}
    for relative in paths:
        cursor = root
        for part in Path(relative).parts:
            cursor = cursor.setdefault(part, {})
    def emit(node, prefix=''):
        entries = sorted(node.items())
        for index, (name, children) in enumerate(entries):
            last = index == len(entries) - 1
            print(prefix + ('└── ' if last else '├── ') + name + ('/' if children else ''))
            emit(children, prefix + ('    ' if last else '│   '))
    emit(root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='project-kit')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create context or restore a pinned setup')
    init.add_argument('--project', type=Path, required=True)
    init.add_argument('--kit', type=Path)
    init.add_argument('--intent', type=Path)
    init.add_argument('--config', type=Path)
    init.add_argument('--json', action='store_true')
    check = commands.add_parser('check', help='Audit files and optionally native runtime')
    check.add_argument('--project', type=Path, required=True)
    check.add_argument('--runtime', action='store_true')
    check.add_argument('--json', action='store_true')
    upgrade = commands.add_parser('upgrade', help='Prepare a pinned kit update in a separate worktree')
    upgrade.add_argument('--project', type=Path, required=True)
    upgrade.add_argument('--kit', type=Path, required=True)
    upgrade.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'upgrade':
            from .upgrade import prepare_upgrade
            report = prepare_upgrade(args.project, args.kit)
        elif args.command == 'check':
            from .check import check_project
            report = check_project(args.project, args.runtime)
        elif not any((args.kit, args.intent, args.config)):
            report = restore(args.project)
        else:
            if not all((args.kit, args.intent, args.config)):
                raise ValueError('First init requires --kit, --intent and --config')
            intent = load_intent(args.intent)
            bundle = prepare_bundle(args.kit, load_config(args.config), contained_path(args.project, '.project-kit/runtime/bundles'))
            report = initialize(args.project, intent, bundle)
    except (ValueError, OSError) as exc:
        parser.exit(2, f'project-kit: {exc}\n')
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(f'{report.status}: {report.project}')
        for check in report.checks:
            if check.status != 'ready':
                print(f'  {check.status}: {check.name}: {check.detail}')
        print(f'  Checks passed: {sum(c.status == "ready" for c in report.checks)}/{len(report.checks)}')
        if args.command != 'check' and (Path(report.project) / '.git').exists():
            _tree(visible_state(Path(report.project)))
    return 0 if report.status == 'ready' else 1
