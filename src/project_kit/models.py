"""Values shared by file operations, adapters, and reports."""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

JSON: TypeAlias = None | bool | int | float | str | list['JSON'] | dict[str, 'JSON']
AgentId = Literal['codex', 'claude-code']
Status = Literal['ready', 'incomplete', 'drift', 'incompatible']


@dataclass(frozen=True)
class ProjectIntent:
    name: str
    goal: str
    scope: str
    task_source: str
    users: tuple[str, ...]
    constraints: tuple[str, ...]
    decisions: tuple[str, ...]
    success: tuple[str, ...]
    commands: dict[str, tuple[str, ...]]
    generation: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class KitConfig:
    schema: int
    profile: str
    agents: tuple[AgentId, ...]
    overrides: dict[str, JSON]


@dataclass(frozen=True)
class Package:
    name: str
    root: Path
    commit: str
    digest: str


@dataclass(frozen=True)
class Bundle:
    kit_source: str
    kit_commit: str
    digest: str
    profile: dict[str, JSON]
    packages: tuple[Package, ...]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


@dataclass(frozen=True)
class Report:
    project: str
    status: Status
    checks: tuple[Check, ...]
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class Lock:
    schema: int
    kit_source: str
    kit_commit: str
    profile: dict[str, JSON]
    profile_digest: str
    render_inputs: dict[str, JSON]
    package_digests: dict[str, str]
    managed_hashes: dict[str, str]
    owned_settings: dict[str, JSON]
