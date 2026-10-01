# Claude Code

enabledPlugins хранится в проекте, абсолютный путь локального marketplace — в
игнорируемом settings.local.json. При необходимости штатной установки:
`claude plugin install PACKAGE@MARKETPLACE --scope project` из корня проекта.
Источник уже объявлен в extraKnownMarketplaces; глобальные настройки не меняются.

`check --runtime` получает нативный inventory и system/init новой сессии.
Probe ограничен 45 секундами, бюджетом $0.01 и завершается после init; история не
сохраняется. Возможен расход модели. Обычный check не запускает клиента.
Проверяется состав skills и содержимое установленного пакета, не текст ответа модели.
Если клиент не предоставляет доказательство состояния обязательных hooks, статус
остаётся incomplete. Это ограничение отражается в совместимости релиза.

[Локальные marketplaces](https://code.claude.com/docs/en/plugin-marketplaces).
