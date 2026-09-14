# Развёртывание через demo odusfera MCP

## Ресурсы стенда

| Ресурс | Значение |
| --- | --- |
| Окружение | `hr-headscale`, Odoo `19.0` |
| Git | `https://github.com/oduflow/oduflow-client-addons`, ветка `19.0-headscale` |
| Модуль | `oduscale` |
| Интерфейс администратора | https://hr-headscale.demo.odusfera.pl |
| Headscale | `oduscale-hs`, `ghcr.io/juanfont/headscale:0.29.3` |
| Сервер подключения клиентов | https://oduscale-hs.demo.odusfera.pl |
| API внутри Docker | `http://oduflow-1-svc-oduscale-hs:8080` |
| VPN-шлюз | `oduscale-gateway`, `tailscale/tailscale:v1.98.3` |
| Odoo через VPN | http://odoo.oduscale.internal или http://100.80.0.1 |

Это демонстрационное окружение: публичный адрес Odoo остаётся доступным для
разработки и проверки. Отзыв в Oduscale блокирует VPN-подключение, но сам по себе
не запрещает вход по публичному адресу Odoo. Для эксплуатации исключительно
через VPN публичный маршрут Odoo нужно закрыть на входном прокси после подготовки
административного доступа через VPN.

HTTP на VPN-адресе передаётся внутри зашифрованного соединения Tailscale/WireGuard.
Шлюз направляет TCP на Odoo 8069, включая websocket при текущем `workers=0`.
Для нескольких Odoo workers потребуется внутренний HTTP-прокси с отдельной
маршрутизацией `/websocket` к gevent-порту. Логин Odoo остаётся обязательным.

## Порядок повторного развёртывания

1. Опубликовать ветку Git. Вызвать `create_environment` с `branch=19.0-headscale`,
   `env_name=hr-headscale`, `odoo_image=odoo:19.0`, `template_name=none` и URL репозитория.
   Установить `oduscale` через `pull_and_apply(install="oduscale")`.
2. Создать тома `oduscale-config`, `oduscale-data`, `oduscale-gateway-state`,
   `oduscale-gateway-config` через `create_volume`.
3. Через `write_file_in_volume` записать `headscale/config.yaml` и `headscale/policy.hujson`
   в `oduscale-config`, а `gateway/serve.json` в `oduscale-gateway-config`.
   При другом окружении заменить домены, имя контейнера Odoo и диапазоны VPN.
4. Создать сервис `oduscale-hs` с образом из таблицы, `command="serve"`, томами
   `oduscale-config:/etc/headscale:ro,oduscale-data:/var/lib/headscale`.
   Передать `routes` для `/health`, `/key`, `/ts2021`, `/register`, `/auth`,
   `/oidc/callback`, `/verify`, `/machine/ping-response`, каждый на `port=8080`.
   Не публиковать catch-all маршрут и `/api/v1`.
5. Выполнить через `run_service_command(name="oduscale-hs", shell=false)`:

   ```text
   headscale users create oduscale-gateway
   headscale apikeys create --expiration 2160h
   headscale users list -o json
   headscale preauthkeys create --user <gateway-user-id> --expiration 1h --tags tag:odoo -o json
   ```

   Не повторять создание пользователя, если он уже существует. API-ключ передать
   только в переменную окружения Odoo `ODUSCALE_API_KEY` через `update_environment`,
   сохраняя остальные переменные. Его значение не должно попадать в Git, chatter
   или отчёты. На стенде API-ключ действует 90 дней с 14 сентября 2026; перед истечением
   создать новый, обновить переменную Odoo, проверить подключение и отозвать старый
   через `headscale apikeys expire`.
6. Создать `oduscale-gateway` с образом из таблицы, `port=65535` (без слушателя,
   VPN-порт не публикуется), томами
   `oduscale-gateway-state:/var/lib/tailscale,oduscale-gateway-config:/config:ro`.
   Параметры окружения:

   ```text
   TS_AUTHKEY=<одноразовый ключ шлюза из шага 5>
   TS_AUTH_ONCE=true
   TS_STATE_DIR=/var/lib/tailscale
   TS_USERSPACE=true
   TS_HOSTNAME=odoo
   TS_EXTRA_ARGS=--login-server=https://oduscale-hs.demo.odusfera.pl --accept-dns=false
   TS_SERVE_CONFIG=/config/serve.json
   ```

   Привилегии `privileged`, `NET_ADMIN` и host networking не нужны. Для Headscale
   с preauth key теги берутся из ключа: не добавлять `--advertise-tags` в команду клиента.
   После регистрации удалить `TS_AUTHKEY` из окружения через `update_service`,
   сохранив остальные параметры. Идентичность шлюза сохранена в томе.
7. В **Oduscale → Headscale Servers** создать сервер с API/login/VPN URL из таблицы,
   переменной ключа `ODUSCALE_API_KEY` и сроком ключей 60 минут. Нажать **Test connection**.
   Для нескольких серверов использовать разные имена переменных ключей.
8. Создать доступ сотрудника и проверить подключение по инструкции в корневом README.

SQLite использует WAL и постоянный том `oduscale-data`. PostgreSQL service database
не требуется: upstream Headscale рекомендует SQLite для новых установок. Копировать
БД через SQLite backup API или при остановленном Headscale; сохранять также private keys
и конфигурацию. При клонировании Odoo для независимого стенда использовать отдельный
Headscale и новую конфигурацию API, чтобы тестовые действия не затронули исходную сеть.

## Эксплуатация

- Синхронизация каждые 5 минут; `.oduflow/odoo.conf` включает один cron-поток.
- Oduflow может автоматически остановить неактивное dev-окружение. Перед проверкой
  запустить `start_environment(env_name="hr-headscale")`; это не production-развёртывание.
- При недоступном Headscale операции возвращают ошибку. Архивирование сотрудника/пользователя
  блокируется, если нельзя подтвердить отзыв. Восстановить сервис и повторить операцию.
- Запросы к Headscale не входят в транзакцию PostgreSQL. Если часть отзыва уже выполнена,
  повторный отзыв дочитает фактические ключи и устройства и завершит очистку.
- После отзыва пользователь Headscale остаётся для аудита и повторного подключения;
  его ключи истекли, устройства удалены. Повторная выдача доступа требует нового ключа.
- Секрет одноразового ключа хранится только в временном диалоге Odoo до очистки transient
  records (час плюс период фоновой очистки). В постоянной истории хранятся ID и срок.
- Headscale API даёт административные полномочия на отдельный сервер. Не подключать
  произвольный общий production Headscale к демонстрационной БД.

## Проверка 14 сентября 2026

- Установка и upgrade в `Odoo 19.0-20260908` успешны.
- 16 Odoo-тестов: 0 ошибок и 0 падений.
- Отдельный Tailscale-процесс зарегистрирован одноразовым ключом из `action_enroll`.
- Устройство `employee-test`, IP `100.80.0.2`, отобразилось online; ключ отмечен использованным.
- Через VPN получен HTTP 200 от `/web/login` на `100.80.0.1`.
- После `action_revoke` узел исчез из Headscale, повторное соединение завершилось таймаутом.
- Внешний `/api/v1/user` возвращает 404; `/health` — 200.
- Тестовый клиент остановлен, ключ отозван; запись сотрудника оставлена для проверки интерфейса.

## Upstream

- [Headscale 0.29.3 и схема API](https://github.com/juanfont/headscale/tree/v0.29.3)
- [Конфигурация Headscale, включая SQLite](https://github.com/juanfont/headscale/blob/v0.29.3/config-example.yaml)
- [Регистрация устройств Headscale](https://headscale.net/stable/ref/registration/)
- [Tailscale 1.98.3](https://github.com/tailscale/tailscale/releases/tag/v1.98.3)
