# BTC Top‑200 Watcher (Telegram Bot)

Бот присылает в чат уведомления, если какой‑то адрес Биткоина попал в Топ‑200 по балансу или вышел из Топ‑200.

## Быстрый старт

1) Установите Python 3.11+.
2) Скачайте и распакуйте проект (ниже есть ZIP).
3) В каталоге проекта:
   ```bash
   python -m venv .venv
   . .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env  # Windows: copy .env.example .env
   ```
4) Создайте Telegram‑бота через @BotFather и возьмите токен (`TELEGRAM_BOT_TOKEN`). Впишите его в файл `.env`.
5) Запустите бота:
   ```bash
   python bot.py
   ```
6) В чате с ботом выполните `/start` — чат будет добавлен в список подписчиков. Команды:
   - `/now` — показать сводку первых 20 адресов.
   - `/status` — показать параметры и подписанные чаты.

## Как это работает

- Раз в N минут (по умолчанию — 10) бот запрашивает текущий список Топ‑200 адресов.
- Сравнивает с предыдущим снимком (файл `top200_state.json`).
- Если появились новые адреса в Топ‑200 или какие‑то вышли из Топ‑200, отправляет сообщение в чат.
- Список чатов хранится в `chats.json` и пополняется по команде `/start`. Можно также указать фиксированные Chat ID в `.env` (переменная `NOTIFY_CHAT_IDS=123,456`).

## Источник данных (провайдеры)

По умолчанию используется провайдер `bitinfocharts`, который парсит две публичные страницы рейтинга богатейших адресов:
- `https://bitinfocharts.com/top-100-richest-bitcoin-addresses.html` (1–100)
- `https://bitinfocharts.com/top-100-richest-bitcoin-addresses-2.html` (101–200)

⚠️ Вёрстка или URL сайта могут измениться. В этом случае обновите список URL в `providers.py` или добавьте другой провайдер.
В `providers.get_provider(...)` легко подключить альтернативные API (Blockchair, Arkham, и т. п.), если у вас есть ключ и понятный эндпоинт.

При необходимости можно задать HTTP‑прокси через `.env` → `HTTP_PROXY`.

## Переменные окружения (.env)

```env
TELEGRAM_BOT_TOKEN=your-bot-token
NOTIFY_CHAT_IDS=          # опционально, через запятую
FETCH_INTERVAL_MIN=10     # частота проверок
PROVIDER=bitinfocharts    # имя провайдера данных
HTTP_PROXY=               # опционально
```

## Развёртывание как сервис (systemd, Linux)

Пример юнита (отредактируйте пути и пользователя):
```ini
[Unit]
Description=BTC Top200 Watcher
After=network.target

[Service]
WorkingDirectory=/opt/btc_top200_bot
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/btc_top200_bot/.venv/bin/python /opt/btc_top200_bot/bot.py
Restart=on-failure
User=youruser
Group=youruser

[Install]
WantedBy=multi-user.target
```

## Замечания и ограничения

- Публичный HTML может меняться — следите за логами бота, при ошибках провайдера обновите парсер в `providers.py`.
- На некоторых источниках действуют правила использования (ToS). Используйте ответственно.
- Если нужно чаще проверять, уменьшите `FETCH_INTERVAL_MIN`, но учитывайте нагрузку на источники.

## TODO (при желании)
- Добавить кэш/ETag и бэкофф при частых запросах.
- Добавить альтернативный API‑провайдер с верифицированным источником.
- Хранить историю изменений в SQLite и отдавать отчёты по запросу.
