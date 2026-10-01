# Project Kit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Выпустить компактный версионируемый набор, создающий и сопровождающий проекты с Codex и Claude Code.

**Architecture:** Общие инструкции, готовые upstream-пакеты и профиль собираются из закреплённого Git commit. Небольшой Python CLI управляет проектными файлами и адаптерами; skills ведут диалог и вызывают его с уже принятыми решениями. Управляемое состояние отделено от проектных данных и активного runtime.

**Tech Stack:** Python >=3.11, Git, uv; PyYAML >=6,<7 для YAML, tomlkit >=0.15,<1 для сохранения посторонних TOML-настроек; pytest >=8,<10 для проверок. Точные версии фиксируются uv.lock. Стек набора не ограничивает стеки создаваемых продуктов.

**Spec:** [Одобренный дизайн](../specs/2026-10-01-project-kit-design.md).

## Global Constraints

- «Обязательные агенты первой версии — Codex и Claude Code».
- «Внешние исходники сохраняются без локальных правок».
- «Краткость оценивается вместе с полнотой».
- «Ориентир для наших стартовых инструкций AGENTS.md + core/entry.md — до 400 слов суммарно; для тела собственного SKILL.md — до 250 слов».
- «Это порог для review, а не команда обрезать текст».
- «Общий статус выбирается в порядке incompatible, drift, incomplete, ready; успешный код завершения возвращается только для ready».
- «Установка и обновление для одного проекта сохраняют настройки других проектов и активных сессий».
- «Lock записывается атомарно после успешного завершения относящегося к нему этапа».
- «Пропущенная runtime-проверка остаётся incomplete».

## Review Focus

1. Путь с пробелами, Unicode или выходом через symlink: работа в указанном корне без записи за его пределы — задачи 3, 4.
2. Посторонние настройки, локальные дополнения и dirty worktree: сохранение данных и конкретная диагностика — задачи 3, 6.
3. Одинаковый номер версии при разных исходниках, moving tag и изменённый кеш: проверка commit и содержимого — задачи 2, 5.
4. Отсутствующий клиент, неподдерживаемая возможность и устаревшее runtime evidence: отсутствие ложного ready — задачи 4, 5.
5. Короткий промпт с потерянным ограничением либо неработающей ссылкой: полнота важнее счётчика слов — задачи 1, 7.

## Структура реализации

Деревья пользовательских артефактов определены в спецификации. Реализация команд добавляет:

~~~text
pyproject.toml, uv.lock
src/project_kit/
  __init__.py, __main__.py
  models.py       # типы состояния и отчёта
  config.py       # чтение и проверка YAML
  sources.py      # commits и неизменяемые пакеты
  files.py        # границы записи, merge, атомарная фиксация
  init.py         # создание общих файлов
  adapters/
    __init__.py, codex.py, claude_code.py
  check.py        # готовность и диагностика
  upgrade.py      # отдельная ветка и сравнение версий
  cli.py          # init/check/upgrade, вывод JSON и дерева
tests/
  test_config.py, test_sources.py, test_files.py
  test_init.py, test_adapters.py, test_check.py, test_upgrade.py
  test_lifecycle.py, conftest.py
~~~

Команды: project-kit init --project PATH --kit PATH --intent FILE --config FILE; project-kit check --project PATH --runtime; project-kit upgrade --project PATH --kit PATH. Для существующего проекта project-kit init --project PATH восстанавливает локальную установку из lock без повторной генерации. Флаг --json возвращает структурированный отчёт; обычный вывод — результат, необходимые действия и фактическое дерево файлов. scripts/init, scripts/check и scripts/upgrade делегируют соответствующей CLI-команде.

Новые механизмы реализуются в task-ветке; создание текущего репозитория и публикация документов уже отдельно разрешены пользователем. На момент написания проверено только наличие клиентов: Codex CLI 0.159.1 и Claude Code 2.1.283. Это исходные версии для smoke-проверки, не заявление о совместимости.

---

### Task 1: Компактное ядро, skills и шаблоны

**Files:** создать core/entry.md, core/workflow.md, core/git.md, core/context-policy.md, core/quality.md; skills/project-init/SKILL.md и references/discovery.md, references/stack-selection.md; skills/project-check/SKILL.md; skills/project-upgrade/SKILL.md; templates/project/README.md, AGENTS.md, CLAUDE.md, .gitignore, project-kit.yaml и docs/project.md, architecture.md, development.md, decisions/0001-stack.md; корневые AGENTS.md, CLAUDE.md; tests/scenarios.md. Обновить README.md.

**Interfaces:**
- Consumes: разделы 1, 5, 6 спецификации.
- Produces: шаблоны с явными подстановками имени и ссылок; project-init формирует intent с полями name, goal, users, scope, constraints, decisions, success, task_source, commands, generation; готовые документы содержат принятые значения.

- [ ] **Step 1:** Написать tests/scenarios.md с двумя brief: Python CLI для подсчёта строк CSV и Node.js HTTP API с GET /health. Для каждого перечислить ограничения, команды проверки и критерии успеха, которые должны сохраниться в контексте.
- [ ] **Step 2:** Написать ядро и skills по контракту «вход → действие → результат → проверка». В references вынести вопросы выбора стека и примеры; в собственных skills сохранить ссылки на основной workflow без его пересказа.
- [ ] **Step 3:** Создать шаблоны и навигацию. AGENTS.md направляет в .project-kit/core/entry.md и проектные документы; CLAUDE.md импортирует @AGENTS.md. Один источник задач задаётся через task_source.
- [ ] **Step 4:** Пройти оба brief по документам: цель, ограничения, решения, проверки и источники доступны; каждый входной вопрос влияет на решение. Проверить ориентиры 400/250 слов и относительные ссылки. Превышение объяснить в review, содержимое не обрезать. Тесты на точное совпадение формулировок не добавлять.
- [ ] **Step 5:** Закоммитить только файлы этой задачи: docs: add concise methodology and project workflows.

### Task 2: Контракты конфигурации и закреплённые пакеты

**Files:** создать pyproject.toml, uv.lock, src/project_kit/__init__.py, models.py, config.py, sources.py, profiles/default.yaml, .gitignore, .codex-plugin/plugin.json, .claude-plugin/plugin.json, tests/conftest.py, test_config.py, test_sources.py; добавить .gitmodules и submodules upstream/superpowers, upstream/ecc.

**Interfaces:**
- models.py: AgentId = Literal['codex', 'claude-code']; Status = Literal['ready', 'incomplete', 'drift', 'incompatible']; JSON = JSON-совместимое значение.
- ProjectIntent: name, goal, scope, task_source: str; users, constraints, decisions, success: tuple[str, ...]; commands: dict[str, tuple[str, ...]]; generation: tuple[tuple[str, ...], ...].
- KitConfig: schema: int, profile: str, agents: tuple[AgentId, ...], overrides: dict[str, JSON].
- Package: name: str, root: Path, commit: str, digest: str. Bundle: kit_source, kit_commit, digest: str; profile: dict[str, JSON]; packages: tuple[Package, ...].
- Check: name: str, status: Status, detail: str. Report: project: str, status: Status, checks: tuple[Check, ...], files: tuple[str, ...]. project — абсолютный корень, к которому относится результат.
- Lock: schema: int, kit_source: str, kit_commit: str, profile: dict[str, JSON], profile_digest: str, render_inputs: dict[str, JSON], package_digests: dict[str, str], managed_hashes: dict[str, str], owned_settings: dict[str, JSON].
- config.py: load_config(path: Path) -> KitConfig; load_intent(path: Path) -> ProjectIntent; read_lock(path: Path) -> Lock. Неверная схема, тип или пропущенное обязательное поле даёт ValueError с путём поля.
- sources.py: prepare_bundle(kit: Path, config: KitConfig, cache: Path) -> Bundle; verify_bundle(bundle: Bundle) -> tuple[Check, ...].

- [ ] **Step 1:** Добавить тесты test_missing_goal, test_unknown_schema, test_uninitialized_submodule, test_dirty_source_rejected и test_changed_payload_same_version. Проверки: схема только 1; agents уникальны и допустимы; goal и success обязательны; изменённый файл пакета обнаруживается независимо от номера версии.

  Контрольные assertions для соответствующих fixtures:
  ```python
  with pytest.raises(ValueError, match="goal"):
      load_intent(intent_without_goal)
  with pytest.raises(ValueError, match="schema"):
      load_config(config_schema_2)
  assert any(c.status == "drift" for c in verify_bundle(tampered_bundle))
  ```

- [ ] **Step 2:** Настроить pyproject.toml и uv.lock; запустить uv run pytest tests/test_config.py tests/test_sources.py -q. Ожидается ошибка импорта ещё не реализованных контрактов.
- [ ] **Step 3:** Реализовать указанные типы и safe YAML parsing, запретить повторяющиеся YAML-ключи. Все subprocess-команды принимают argv, shell=False. Хешировать относительные пути, содержимое и исполняемые биты; .git исключать; внутренние symlinks сохранять, выходящие за пакет отклонять.
- [ ] **Step 4:** Добавить официальные upstream https://github.com/obra/superpowers.git и https://github.com/affaan-m/ECC.git на явно выбранных релизах, разрешённых в полные commits. Зафиксировать gitlinks; dirty исходники не принимать. Пакетировать полный родной набор с resources/scripts, сохраняя исходники; необходимые штатные сборки выполнять в staging и фиксировать результат по digest.
- [ ] **Step 5:** Создать default-профиль для двух агентов и трёх пакетов: project-kit, superpowers, ecc. Основные процессы discovery/planning/verification направить в соответствующие skills Superpowers; ECC подключить как технический набор. Hooks/MCP перечислять отдельно с явным состоянием и проверять штатную поддержку этого состояния. Создать нативные манифесты собственных skills.
- [ ] **Step 6:** Повторить команду Step 2; ожидается PASS. Закоммитить задачу: feat: resolve pinned project kit bundles.

### Task 3: Создание проекта без потери файлов

**Files:** создать src/project_kit/files.py, init.py, cli.py, __main__.py, scripts/init, tests/test_files.py, tests/test_init.py.

**Interfaces:**
- Consumes: ProjectIntent, KitConfig, Bundle, Lock, Report; prepare_bundle из задачи 2.
- files.py: contained_path(root: Path, relative: str) -> Path; write_atomic(path: Path, content: bytes) -> None; merge_owned(current: bytes, baseline: bytes, desired: bytes, kind: Literal['markdown','json','toml'], owned: tuple[tuple[str, ...], ...]) -> bytes. owned содержит пути ключей из lock.owned_settings; для Markdown — имя блока. Конфликт возвращается исключением MergeConflict с путём/ключом, без записи.
- init.py: render_project(intent: ProjectIntent, bundle: Bundle) -> dict[str, bytes]; initialize(project: Path, intent: ProjectIntent, bundle: Bundle) -> Report.
- cli.py: main(argv: Sequence[str] | None = None) -> int; пока реализуется init, прочие команды добавляются в своих задачах.

- [ ] **Step 1:** Написать test_init_preserves_readme, test_repeat_init_has_no_diff, test_unicode_space_path, test_symlink_escape_no_write и test_partial_write_keeps_lock. Прямо проверить сохранение исходных bytes, отсутствие файлов за корнем и неизменность прежнего lock при искусственном сбое записи.

  После соответствующих операций:
  ```python
  assert readme.read_bytes() == original_readme
  assert second_report.files == ()
  assert not escaped_target.exists()
  assert lock_path.read_bytes() == original_lock
  ```

- [ ] **Step 2:** Выполнить uv run pytest tests/test_files.py tests/test_init.py -q; ожидается FAIL из-за отсутствующих функций.
- [ ] **Step 3:** Реализовать границы путей и атомарную запись через временный файл в том же каталоге и os.replace. Смешанные Markdown-файлы обновлять в блоке PROJECT-KIT; JSON/TOML — только по owned_settings; локально изменённые управляемые значения считать конфликтом. Сохранять существующие mode bits.
- [ ] **Step 4:** Реализовать рендер общих файлов и проектных документов из intent. Выполнять принятые generation-команды в целевой директории с зафиксированными argv; хранить их в docs/development.md. Повторный init не запускает генератор заново. До записи проверить все коллизии; незавершённые шаги и кандидат lock отмечать в исключённом из Git .project-kit/operation.json для продолжения. Режим восстановления читает применённый lock и восстанавливает только локальные пакеты и настройки.
- [ ] **Step 5:** Создать Git-репозиторий в целевой директории, если его нет; чужую историю сохранять. После создания файлов вернуть incomplete до подключения и runtime-проверок адаптеров. Отчёт содержит только фактические созданные/изменённые пути; не включает кеш, секреты и сырые логи.
- [ ] **Step 6:** Повторить команду Step 2; ожидается PASS. Закоммитить задачу: feat: initialize projects with preserved local context.

### Task 4: Изолированные адаптеры Codex и Claude Code

**Files:** создать src/project_kit/adapters/__init__.py, codex.py, claude_code.py; adapters/codex/README.md, adapter.yaml; adapters/claude-code/README.md, adapter.yaml; tests/test_adapters.py. Дополнить init.py.

**Interfaces:**
- Consumes: Bundle, Check, merge_owned и write_atomic.
- adapters/__init__.py: AdapterPlan(files: dict[str, bytes], expected_packages: dict[str, str]); Observation(project: str, agent: AgentId, client_version: str, profile_digest: str, observed_packages: dict[str, str], loaded_skills: tuple[str, ...], capabilities: dict[str, bool], confirmed_at: str). project — абсолютный корень наблюдаемого checkout.
- Каждый адаптер: plan(project: Path, bundle: Bundle) -> AdapterPlan; observe(project: Path, bundle: Bundle, runtime: bool) -> tuple[Check, Observation | None].

- [ ] **Step 1:** Добавить test_two_projects_keep_distinct_versions, test_unrelated_settings_unchanged, test_missing_client_incomplete, test_unknown_capability_incompatible, test_native_paths_with_spaces. Проверять содержимое обоих проектов и отсутствие изменений глобальных настроек.

  Assertions после настройки второго проекта:
  ```python
  assert observation_a.observed_packages != observation_b.observed_packages
  assert project_a_settings.read_bytes() == original_a_settings
  assert global_settings.read_bytes() == original_global_settings
  assert missing_client_check.status == "incomplete"
  assert unsupported_capability_check.status == "incompatible"
  ```

- [ ] **Step 2:** Выполнить uv run pytest tests/test_adapters.py -q; ожидается FAIL.
- [ ] **Step 3:** Материализовать неизменяемые пакеты в .project-kit/runtime/<bundle.digest>/plugins; каталог исключить из Git. Имя локального marketplace — project-kit- плюс первые 16 символов digest; при совпадении имени обязательно сверять полный digest.
- [ ] **Step 4:** Codex: создать проектный .agents/plugins/marketplace.json с source.path внутри проекта и соответствующие plugins.<id>.enabled в .codex/config.toml. Сохранять чужие записи; конфликтующие одноимённые пакеты отключать только в проектном слое. Инвентарь получать через codex plugin list --json, проверять payload установленного кеша и наблюдаемую загрузку в новой сессии. При необходимости штатной установки вернуть точное требуемое действие и incomplete; не включать пакет глобально ради прохождения проверки.
- [ ] **Step 5:** Claude Code: сформировать локальный marketplace внутри runtime и проектные enabledPlugins; машинные пути extraKnownMarketplaces хранить в .claude/settings.local.json с сохранением чужих ключей. Конфликтующие версии отключать только для текущего проекта. Проверять через claude plugin validate и claude plugin list --json. Общие файлы содержат только переносимые настройки. Если клиент требует установки/доверия, явно вернуть incomplete до штатного завершения этого шага.
- [ ] **Step 6:** Добавить фиксацию Observation: состав и digest сверяются с нативным инвентарём и загруженными компонентами; один текстовый ответ модели не служит доказательством версии. Required hooks/MCP должны иметь подтверждённое состояние; неподдерживаемые настройки дают incompatible. Политики клиента не обходить.
- [ ] **Step 7:** Повторить Step 2; ожидается PASS. Проверить fake-native fixtures с корректным, отсутствующим и отличающимся пакетом. Закоммитить задачу: feat: add project-scoped agent adapters.

### Task 5: Проверка готовности и ёмкости контекста

**Files:** создать src/project_kit/check.py, scripts/check, tests/test_check.py; дополнить cli.py, init.py.

**Interfaces:**
- Consumes: Lock, Bundle, Check, Report, Observation и observe обоих адаптеров.
- check.py: aggregate(checks: Sequence[Check]) -> Status; audit_prompts(project: Path, bundle: Bundle) -> tuple[Check, ...]; check_project(project: Path, runtime: bool, expected: Lock | None = None) -> Report. expected задаёт кандидат состояния при init/upgrade; обычный check читает применённый lock. Проверка кандидата предшествует записи lock.

- [ ] **Step 1:** Написать test_status_precedence, test_same_version_wrong_digest_is_drift, test_stale_observation_incomplete, test_broken_context_link, test_required_context_missing и test_candidate_checked_before_lock_written. После смены профиля или корня прежнее runtime-наблюдение недостаточно:

  ```python
  assert aggregate([Check("a", "drift", ""), Check("b", "incompatible", "")]) == "incompatible"
  assert aggregate([]) == "incomplete"
  assert stale_observation_report.status == "incomplete"
  assert wrong_digest_report.status == "drift"
  assert missing_context_report.status == "incomplete"
  assert lock_path.read_bytes() == original_lock  # до успешной проверки кандидата
  ```

- [ ] **Step 2:** Выполнить uv run pytest tests/test_check.py -q; ожидается FAIL.
- [ ] **Step 3:** Реализовать проверки декларации, lock, пакетов, управляемых файлов и актуального Observation. Изменение пути проекта, версии клиента, профиля или пакетов делает прежнее наблюдение недостаточным. --runtime получает новое наблюдение; без него сохраняется incomplete для обязательных runtime-проверок.
- [ ] **Step 4:** Проверять разрешимость ссылок и заполненность структурных полей intent. Счётчик слов даёт замечание при >400 суммарно в стартовых инструкциях и >250 в теле собственного skill; отсутствие смыслового условия не компенсируется малым размером. Полноту смысла проверять по brief в сценариях задачи 7.
- [ ] **Step 5:** Добавить check в CLI: exit 0 только ready, exit 1 для остальных состояний; отдельный exit 2 для ошибки входного формата. JSON-вывод содержит project, status, checks, files; человекочитаемый вывод кратко поясняет оставшиеся действия. После шагов init проверить кандидат через expected; только при ready атомарно записать lock и завершить транзакцию. Обычный check не изменяет файлы проекта.
- [ ] **Step 6:** Повторить Step 2; ожидается PASS. Закоммитить задачу: feat: report verified project readiness.

### Task 6: Обновление набора через отдельную ветку

**Files:** создать src/project_kit/upgrade.py, scripts/upgrade, tests/test_upgrade.py; дополнить cli.py.

**Interfaces:**
- Consumes: read_lock, prepare_bundle, render_project, merge_owned, check_project.
- upgrade.py: prepare_upgrade(project: Path, target_kit: Path) -> Report. Report.project указывает отдельный worktree; его ready относится только к этому корню. Исходный checkout остаётся на прежней ветке.

- [ ] **Step 1:** Написать test_upgrade_keeps_project_edits, test_modified_managed_block_conflicts, test_dirty_worktree_preserved, test_failed_runtime_keeps_old_lock, test_rerun_upgrade_resumes и test_other_project_unaffected. README, решения и пользовательские ключи сравниваются byte-for-byte; исходная ветка и lock остаются прежними при ошибке.

  Assertions соответствующих сценариев:
  ```python
  assert readme.read_bytes() == original_readme
  assert lock_path.read_bytes() == original_lock  # сбой runtime
  assert second_report.project == first_report.project  # продолжение операции
  assert other_project_settings.read_bytes() == original_other_settings
  ```

- [ ] **Step 2:** Выполнить uv run pytest tests/test_upgrade.py -q; ожидается FAIL.
- [ ] **Step 3:** Проверить чистоту исходного checkout; при dirty вернуть incomplete со списком путей, без stash/reset. Для чистого состояния создать ветку chore/project-kit-<target-short-sha> и отдельный worktree; записать локальный журнал операции для повторного запуска.
- [ ] **Step 4:** Восстановить baseline из прежнего kit commit и lock.render_inputs/profile, сверить baseline hashes. Сравнить baseline/local/desired; проектные файлы пропустить, смешанные обновить только через merge_owned. Конфликт оставить для явного разбора с доступным исходным содержимым.
- [ ] **Step 5:** Проверить кандидат через check_project(expected=candidate) в новом worktree; при ready атомарно записать новый lock. Подготовить diff, изменения workflows, результаты проверок и команды восстановления. После merge в другом checkout локальная установка восстанавливается через init --project PATH и проверяется заново. Merge ветки и выпуск версии выполняются обычным процессом проекта.
- [ ] **Step 6:** Повторить Step 2; ожидается PASS. Закоммитить задачу: feat: upgrade kit with conflict-aware file ownership.

### Task 7: Сквозные сценарии и готовность к выпуску

**Files:** создать tests/test_lifecycle.py, tests/fixtures/materialize.py, tests/fixtures/cli/brief.yaml, tests/fixtures/cli/starter/app.py, tests/fixtures/web-api/brief.yaml, tests/fixtures/web-api/starter/server.mjs, tests/run, .github/workflows/checks.yml, CHANGELOG.md, docs/compatibility.md; дополнить README.md и tests/scenarios.md.

**Interfaces:**
- Consumes: три CLI-команды и контракты задач 1–6.
- Produces: воспроизводимые команды CI, результаты двух сценариев, фактически проверенная матрица клиентов и компактная инструкция использования.

- [ ] **Step 1:** Добавить lifecycle-тесты на временных Git-репозиториях: init → повторный init → проектные изменения → upgrade. Использовать локальные версии пакетов с различающимися commits/digests. materialize.py копирует минимальный starter по пути в argv; это тестовая замена генератора выбранного стека. Для CSV задать вход с заголовком и двумя строками данных; API возвращает {"status":"ok"}:

  ```python
  assert csv_process.stdout.strip() == "2"
  assert health_response.status == 200
  assert json.loads(health_body) == {"status": "ok"}
  assert repeated_init.files == ()
  assert upgraded_lock.kit_commit != initial_lock.kit_commit
  assert restore_report.status == "ready"
  ```

- [ ] **Step 2:** Запустить uv run pytest tests/test_lifecycle.py -q; до сборки полного маршрута ожидается FAIL.
- [ ] **Step 3:** Соединить шаги CLI и восстановление после незавершённой установки. Для CLI brief получить программу подсчёта строк CSV и проверить известный вход; для API brief проверить ответ GET /health. Выбор технических средств каждого проекта сохраняется в его ADR и командах, не в универсальном генераторе набора.
- [ ] **Step 4:** Выполнить uv run pytest -q; ожидается PASS. CI устанавливает Node.js 22 для API-fixture и запускает эту же команду на Python 3.11 и 3.14, проверяет структуру пакетов и ссылки. Реальные платные вызовы агентов в обычный CI не включать.
- [ ] **Step 5:** Провести ограниченную живую проверку обоих агентов в подготовленных проектах: наблюдаемая загрузка нужного skill, общих правил и правильного пакета; два разных закрепления сохраняются при обновлении одного проекта. Использовать существующую авторизацию; сохранять только сведения о версиях, digest и результате, без сырых приватных логов. Непроверенные клиенты отмечать как непроверенные.
- [ ] **Step 6:** Проверить по исходным brief, что короткие инструкции сохранили цели, ограничения, решения и критерии результата. Проверить фактические деревья файлов. В README оставить вход, три операции, ссылку на контекст и ограничения подтверждённой совместимости.
- [ ] **Step 7:** Закоммитить задачу: test: verify project kit lifecycle and agent compatibility. Подготовить changelog и результат для review; готовность релиза определяется критериями спецификации.

## Проверка покрытия перед передачей

| Спецификация | Задачи |
| --- | --- |
| Назначение, методология, структура и ёмкость промптов | 1, 3, 5, 7 |
| Внешние зависимости, собственные skills, профили и версии | 1, 2, 4 |
| Два агента и сохранение контекста | 1, 4, 7 |
| Запуск, проверка, обновление | 3, 5, 6 |
| Владение файлами, ошибки и восстановление | 2, 3, 4, 5, 6 |
| Два проекта, повторный запуск и разные закрепления | 4, 6, 7 |

## Технические основания

- [Codex: проектный каталог и настройки плагинов](https://developers.openai.com/plugins/build/plugins#enable-or-disable-a-plugin-for-a-repo): обнаружение каталога и активность плагина проверяются отдельно; подключение требует доверенного проекта.
- [Claude Code: локальные marketplaces](https://code.claude.com/docs/en/plugin-marketplaces): сохраняется полный пакет, проверяются manifest и фактическая установка.
- [PyYAML](https://pypi.org/project/PyYAML/) и [tomlkit](https://pypi.org/project/tomlkit/): используются для чтения YAML и изменения TOML; зависимости будут закреплены в uv.lock при реализации.

Статус плана: подготовлен для review. Исполнение начинается после review плана и выбора Native либо Subagent-driven. Для этой реализации рекомендуется Native: задачи тесно связаны общими контрактами и требуют последовательной проверки состояния файлов и клиентов.
