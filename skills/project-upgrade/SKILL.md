---
name: project-upgrade
description: Use when updating a project's pinned Project Kit version while preserving product code, decisions, and local settings.
---

# Обновить набор

Вход: корень проекта и checkout явно выбранной новой версии Project Kit.

Прочитай текущие project-kit.yaml/lock и changelog целевой версии.
Запусти `project-kit upgrade --project PATH --kit KIT`.
Команда готовит отдельную ветку и worktree. При конфликте сравни исходное,
локальное и новое содержимое; сохрани пользовательские изменения.
Не исправляй dirty checkout через reset/stash.

Проверь diff, изменившиеся workflows и результаты проверок обоих агентов.
Код продукта, его README, решения и технические настройки остаются проектными.
Результат: проверяемая ветка обновления, отчёт с точным корнем и команды продолжения.

После merge восстанови локальную установку в рабочем checkout через
`project-kit init --project PATH`, затем `project-kit check --project PATH --runtime`.
Готовность подготовленного worktree не подтверждает runtime другого checkout.
Заверши по процессу Git проекта; публикация не следует автоматически из подготовки diff.
