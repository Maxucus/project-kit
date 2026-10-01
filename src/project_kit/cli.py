"""Command-line entry points. Output describes only the requested checkout."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence
from .config import load_config, load_intent
from .init import initialize, restore
from .files import contained_path
from .sources import prepare_bundle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='project-kit')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create context or restore a pinned setup')
    init.add_argument('--project', type=Path, required=True)
    init.add_argument('--kit', type=Path)
    init.add_argument('--intent', type=Path)
    init.add_argument('--config', type=Path)
    init.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if not any((args.kit, args.intent, args.config)):
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
            print(f'  {check.status}: {check.name}: {check.detail}')
        if report.files:
            print('Changed files:')
            for relative in report.files:
                print(f'  {relative}')
    return 0 if report.status == 'ready' else 1
