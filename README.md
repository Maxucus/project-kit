# Project Kit

Версионируемые правила, skills и scaffold для работы с Codex и Claude Code: от требований и выбора стека до проверки и обновления проекта. Сейчас — preview; подтверждённые возможности и ограничения находятся в [матрице совместимости](docs/compatibility.md).

## Начало

Нужны Git, Python 3.11+ и [uv](https://docs.astral.sh/uv/). Внешние пакеты закреплены Git submodules; вложенность сохраняет их историю и точный commit.

```bash
git clone --recurse-submodules https://github.com/Maxucus/project-kit.git
cd project-kit
uv sync --locked
```

Открой [project-init](skills/project-init/SKILL.md) в агенте. Он собирает цель, границы, ограничения, критерии результата и обоснование стека; результат — `intent.yaml` по [образцу](examples/intent.yaml) и [конфигурация](examples/project-kit.yaml). Команды `generation` задаются списками аргументов и исполняются в новом проекте; пустой список создаёт только контекст. Универсальный стек не навязывается.

```bash
# Создать проект по подготовленному описанию; kit должен быть чистым Git checkout.
uv run project-kit init --project ../my-project --kit . --intent /path/to/intent.yaml --config examples/project-kit.yaml

# Проверить файлы и фактическую загрузку пакетов клиентами.
uv run project-kit check --project ../my-project --runtime

# Подготовить обновление из явно выбранного checkout в отдельной ветке/worktree.
uv run project-kit upgrade --project ../my-project --kit /path/to/new-kit
```

Для восстановления после клонирования, незавершённой установки или merge обновления: `uv run project-kit init --project ../my-project`. Генераторы завершённых шагов повторно не запускаются. Upgrade требует чистый проект; возвращает путь нового worktree и сохраняет исходную ветку. Перед merge проверь diff.

`ready` означает успешную проверку всего профиля. Пропущенная runtime-проверка, отсутствие доверия/установки или непроверенные hooks дают `incomplete`; несовпадение содержимого — `drift`, неподдерживаемое сочетание — `incompatible`. Код выхода: `0` только для `ready`, `1` для остальных статусов, `2` для неверного ввода. `--json` возвращает отчёт; init/upgrade также показывают фактическое дерево файлов. Lock появляется только после успешной проверки.

## Устройство

```text
project-kit/
├── AGENTS.md / CLAUDE.md        # вход для клиентов
├── core/                      # компактные общие правила
├── skills/                    # собственные init, check, upgrade
├── profiles/default.yaml      # состав пакетов и маршруты workflows
├── upstream/                  # неизменённые Superpowers и ECC, submodules
├── templates/project/         # контекст нового проекта
├── examples/                  # входные YAML
├── .codex-plugin/ / .claude-plugin/
├── src/project_kit/            # CLI, pinning, merge, адаптеры
├── scripts/                   # оболочки трёх команд
├── tests/                     # два стека и сценарии ошибок
└── docs/                      # дизайн, план, совместимость
```

В новом проекте `docs/project.md` хранит задачу и границы, `docs/architecture.md` — архитектуру, `docs/development.md` — команды и единый источник задач, `docs/decisions/` — решения. `project-kit.yaml` задаёт профиль, `project-kit.lock.yaml` фиксирует применённый состав. `.project-kit/core/` версионируется; `.project-kit/runtime/` и машинные пути игнорируются. README, код и решения принадлежат проекту; управляемые блоки и ключи обновляются с обнаружением конфликтов.

Правила открываются по [маршруту контекста](core/context-policy.md). Собственные skills дополняют внешние, не копируют их текст. Для нового внешнего набора добавь submodule с полным commit, проверь нативные manifests и явно включи пакет в профиль. Graphify пока не подключён: конкретный источник не выбран.

Разработка: `uv run pytest -q` (для API-сценария нужен Node.js 22+). Автотесты изолируют внешние клиенты; они не заменяют живую проверку. Архитектура и критерии — в [дизайне](docs/superpowers/specs/2026-10-01-project-kit-design.md), изменения — в [changelog](CHANGELOG.md).
