---
name: project-init
description: Use when starting a project from an idea or restoring its pinned Project Kit setup in Codex or Claude Code.
---

# Создать проект

Вход: задача, целевая директория, ограничения, выбранный checkout Project Kit.

1. Для существующего lock восстанови установку через `project-kit init --project PATH`;
   код и генератор повторно не запускаются.
2. Для нового проекта уточни только недостающие решения по
   [discovery](references/discovery.md). Выбери стек по
   [критериям](references/stack-selection.md) и пройди workflow профиля.
3. Сохрани принятые значения в intent YAML и config YAML; не помещай туда секреты.
   Intent: name, goal, users, scope, constraints, decisions, success, task_source,
   commands (имя → argv), generation (список argv с закреплёнными версиями инструментов).
   Config: schema: 1, profile: default, agents: [codex, claude-code], overrides: {}.
4. Выполни `project-kit init --project PATH --kit KIT --intent INTENT --config CONFIG`.
   Следуй конкретной диагностике установки и доверия клиента; затем повтори init.
5. Выполни проектные команды проверки и `project-kit check --project PATH --runtime`.

Результат: документы, обоснованный стек, техническая основа, настройки агентов,
закрепление и дерево фактических файлов. Сопоставь документы с brief: ни одно ключевое
условие не потеряно. Различай созданное, проверенное и ожидающее настройки;
ready допустим только после обязательных проверок.
