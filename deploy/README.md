# Развёртывание Nannos на AWS

Перенос локального контура на одну виртуальную машину AWS. Elysco и база остаются
в Replit. Код приложений не меняется — только переменные окружения.

**Схема доступа к базе:** у каждого сервиса Nannos своя роль Neon, названная так же,
как его схема. База общая с Elysco, изоляция — на уровне ролей.

---

## Текущее состояние

Заполняется по ходу развёртывания.

| Параметр | Значение |
|---|---|
| Регион | `eu-north-1` (Стокгольм) |
| Инстанс | `t3.medium` |
| Elastic IP | `13.48.218.238` |
| Домен | `13-48-218-238.sslip.io` |
| Ключ SSH | `~/pems/RT/kp_nannos.pem` |
| ОС | Ubuntu 26.04 LTS |
| База | Neon, регион `us-east-2` (Огайо) |
| База | `neondb`, владелец `neondb_owner` (Elysco) |
| Роли Nannos | `console` → схема `console`, `nannos` → схема `nannos` |

Прогресс:

- [x] Инстанс создан, SSH работает
- [x] Тип `t3.medium`, диск 28 ГБ
- [x] Elastic IP привязан
- [x] Порты 80 и 443 открыты
- [x] Docker установлен
- [x] Ключ для GitHub Actions добавлен
- [x] Схемы в базе Neon созданы
- [x] Роли `console` и `nannos` созданы, схемы переданы им во владение
- [x] Файлы в репозитории
- [x] Секреты в GitHub
- [x] Первая сборка
- [x] Первый деплой
- [x] Миграции консоли применены (83 шт., схема `console`)
- [x] Форма входа Keycloak открывается (`redirect_uri` принят)
- [x] Секреты в GitHub приведены в рабочее состояние
- [x] Токен выдаётся (`test@local.dev`, группа `nannos-team`)
- [ ] Вход в UI работает
- [ ] Чат отвечает

---

## Содержание

1. [Что где живёт](#1-что-где-живёт)
2. [Виртуальная машина](#2-виртуальная-машина)
3. [Настройка машины](#3-настройка-машины)
4. [Домен](#4-домен)
5. [База в Neon](#5-база-в-neon)
6. [Файлы в репозиторий](#6-файлы-в-репозиторий)
7. [Секреты GitHub](#7-секреты-github)
8. [Первый запуск](#8-первый-запуск)
9. [Если сломалось](#9-если-сломалось)
10. [Синхронизация с апстримом](#10-синхронизация-с-апстримом)

---

## 1. Что где живёт

```
Replit                          AWS EC2 (одна VM)
├── Elysco                      ├── console-frontend  nginx :8081
└── Neon Postgres    ◄──TLS───► ├── console-backend   :5001
    ├── схемы Elysco            ├── orchestrator      :10001
    ├── схема console           ├── keycloak          :8180
    ├── схема nannos            ├── litellm           :4000
    └── схема keycloak          └── caddy             :80/:443
```

Наружу смотрит только Caddy. Остальные контейнеры общаются по внутренней сети Docker.

> **Про задержки.** Оркестратор пишет чекпоинт после каждого шага агента, и каждая
> запись идёт из AWS в Neon через интернет. Выбирайте регион EC2 поближе к региону
> базы — на длинном диалоге разница складывается в заметные секунды.

---

## 2. Виртуальная машина

Замеры локального контура: все сервисы Nannos вместе занимают около **2 ГБ памяти**
в покое, образы весят примерно 3,5 ГБ.

| Параметр | Значение | Почему |
|---|---|---|
| Тип | `t3.medium` | 2 vCPU, 4 ГБ. На `t3.small` не поместится |
| Диск | 30 ГБ gp3 | Восьми по умолчанию не хватит |
| ОС | Ubuntu Server 24.04 LTS | Свежий Docker из репозитория |
| Ключ | ED25519, формат `.pem` | Скачивается один раз |

### Порты (security group)

| Тип | Порт | Источник | Зачем |
|---|---|---|---|
| SSH | 22 | My IP | Ваш доступ |
| HTTP | 80 | `0.0.0.0/0` | Проверка Let's Encrypt |
| HTTPS | 443 | `0.0.0.0/0` | Сам UI |

Порт 80 обязателен, даже если сайт только по HTTPS — через него идёт проверка
владения доменом.

### Постоянный IP

`EC2` → `Elastic IPs` → **Allocate** → **Associate** с инстансом.

Без этого адрес сменится при перезапуске машины и всё сломается.

Дальше по тексту `13.48.218.238` — подставляйте свой.

---

## 3. Настройка машины

```bash
ssh -i ~/pems/RT/kp_nannos.pem ubuntu@13.48.218.238

sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker

sudo mkdir -p /opt/nannos && sudo chown ubuntu:ubuntu /opt/nannos
```

Выйдите и зайдите заново, чтобы группа `docker` применилась. Проверка: `docker ps`
должен отработать без ошибки прав.

### Ключ для GitHub Actions

Отдельная пара, не ваш личный ключ. Генерируйте **на своей машине**:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/nannos_deploy -N "" -C "github-actions"
cat ~/.ssh/nannos_deploy.pub
```

На сервере:

```bash
echo "ssh-ed25519 AAAA... github-actions" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Проверка:

```bash
ssh -i ~/.ssh/nannos_deploy ubuntu@13.48.218.238 "echo работает"
```

---

## 4. Домен

Домена нет — используем **sslip.io**. Сервис отдаёт IP прямо из имени, регистрировать
ничего не нужно, Let's Encrypt такие имена принимает.

```
IP:     13.48.218.238
Домен:  13-48-218-238.sslip.io
```

Проверка: `ping -c 1 13-48-218-238.sslip.io` должен ответить вашим адресом.

HTTPS обязателен — без него ломаются сессионные cookie и OIDC-редиректы.

> Когда появится настоящий домен: меняете `PUBLIC_HOST`, направляете A-запись на тот
> же Elastic IP, перезапускаете. Caddy получит новый сертификат сам.

---

## 5. База в Neon

### Строка подключения

Из панели Replit/Neon:

```
postgresql://ПОЛЬЗОВАТЕЛЬ:ПАРОЛЬ@ep-xxx.eu-central-1.aws.neon.tech/ИМЯ_БАЗЫ?sslmode=require
```

Нужны четыре части: пользователь, пароль, хост, имя базы. Под этой учёткой
(`neondb_owner`) работает Elysco — она же понадобится, чтобы создать роли ниже.

### Схемы и роли

Хост базы общий с Elysco, поэтому важно, чтобы сервисы Nannos физически не могли
попасть в её таблицы. Решает это одно правило Postgres.

`search_path` по умолчанию равен `"$user", public`. Плейсхолдер `$user`
разворачивается в **имя текущей роли**. Значит, если назвать роль так же, как
схему, всё безымянное — создаваемые таблицы, служебная таблица миграций rambler —
автоматически попадает в нужную схему, впереди `public`.

Ничего настраивать не надо: ни `ALTER ROLE ... SET search_path`, ни `RAMBLER_TABLE`.

Выполните под `neondb_owner`:

```sql
CREATE SCHEMA IF NOT EXISTS nannos;
CREATE SCHEMA IF NOT EXISTS console;
CREATE SCHEMA IF NOT EXISTS keycloak;

-- Console: своя роль, своя схема
CREATE ROLE console LOGIN PASSWORD 'ПАРОЛЬ_CONSOLE';
GRANT console TO neondb_owner;          -- ALTER SCHEMA требует членства в целевой роли
ALTER SCHEMA console OWNER TO console;
GRANT CONNECT ON DATABASE neondb TO console;
GRANT USAGE ON SCHEMA public TO console; -- нужен только для расширения vector

-- Orchestrator: то же самое
CREATE ROLE nannos LOGIN PASSWORD 'ПАРОЛЬ_NANNOS';
GRANT nannos TO neondb_owner;
ALTER SCHEMA nannos OWNER TO nannos;
GRANT CONNECT ON DATABASE neondb TO nannos;
GRANT USAGE ON SCHEMA public TO nannos;

-- Консоль читает хранилище оркестратора
GRANT USAGE ON SCHEMA nannos TO console;
GRANT SELECT ON ALL TABLES IN SCHEMA nannos TO console;
```

> **Схемы создать обязательно.** Ни одна из 83 миграций консоли не выполняет
> `CREATE SCHEMA`. Пропустите шаг — миграции упадут на первой таблице.

Если схема `nannos` уже была из дампа, таблицы в ней всё ещё принадлежат старому
владельцу — передайте их роли:

```sql
DO $$ DECLARE r record; BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='nannos' LOOP
    EXECUTE format('ALTER TABLE nannos.%I OWNER TO nannos', r.tablename);
  END LOOP;
END $$;
```

Миграция выполняет `CREATE INDEX IF NOT EXISTS`, а это требует владения таблицей.
Без передачи получите `must be owner of table store`.

**Проверка.** Подключитесь под ролью `console` и создайте таблицу без указания схемы:

```sql
CREATE TABLE probe_test (id int);
SELECT schemaname FROM pg_tables WHERE tablename = 'probe_test';  -- должно быть: console
DROP TABLE probe_test;
```

Если вернулось `public` — роль названа не так, как схема, либо схема не создана.

### Расширение vector

```sql
SELECT extname, nspname FROM pg_extension e
  JOIN pg_namespace n ON n.oid = e.extnamespace WHERE extname = 'vector';
```

Должно вернуть `vector | public`. Пул подключения ставит `search_path = схема, public`,
поэтому тип найдётся.

### Пароли

```bash
echo "роль console:           $(openssl rand -hex 16)"
echo "роль nannos:            $(openssl rand -hex 16)"
echo "litellm master:         sk-$(openssl rand -hex 24)"
echo "keycloak admin:         $(openssl rand -base64 18)"
echo "kc-secret orchestrator: $(openssl rand -hex 32)"
echo "kc-secret agent-console: $(openssl rand -hex 32)"
```

Сохраните в менеджере паролей. Первые два — пароли ролей из блока выше.

> **Keycloak** ходит под `neondb_owner`: свою схему он создаёт и мигрирует сам,
> и `search_path` для этого не использует. Отдельная роль ему не нужна.

---

## 6. Файлы в репозиторий

Отдельная ветка, чтобы `main` оставался чистой копией апстрима:

```bash
cd nannos
git checkout -b deploy/aws
mkdir -p deploy .github/workflows
```

### Копируем отлаженное локально

```bash
cp ../nannos-frontend/nginx.conf                deploy/
cp ../litellm/config.yaml                       deploy/litellm-config.yaml
cp scripts/local-dev/keycloak/realm-export.json deploy/
```

### Правки в realm-export.json

Три обязательные, без них не заработает.

**1. Scope `basic`** — без него в токене нет поля `sub`, backend отвечает
`Invalid token: missing subject`. Для клиентов `agent-console` и `orchestrator`:

```json
"defaultClientScopes": ["basic", "roles", "profile", "email", "service_account"]
```

**2. Адреса возврата** у `agent-console`:

```json
"redirectUris": ["https://13-48-218-238.sslip.io/*"],
"webOrigins":   ["https://13-48-218-238.sslip.io"]
```

**3. Секреты** — везде, где `"secret": "local-secret"`, поставьте настоящие значения.

> Файл импортируется только при первом старте с пустой базой. Дальнейшие правки в нём
> Keycloak игнорирует — меняйте через админку.

### deploy/Caddyfile

```
{$PUBLIC_HOST} {
	handle_path /auth/* {
		reverse_proxy keycloak:8080
	}
	handle {
		reverse_proxy console-frontend:8081
	}
}
```

### deploy/docker-compose.prod.yml

```yaml
name: nannos

services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    environment:
      PUBLIC_HOST: ${PUBLIC_HOST}

  console-frontend:
    image: ghcr.io/authrion/nannos-console-frontend:${TAG:-latest}
    restart: unless-stopped
    volumes:
      # проксирует /api/ на backend и подменяет Origin
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro

  console-backend:
    image: ghcr.io/authrion/nannos-console-backend:${TAG:-latest}
    restart: unless-stopped
    env_file: [./console-backend.env]
    # RAMBLER_SSLMODE не переопределяем: в образе стоит require,
    # и для Neon это как раз верно

  orchestrator:
    image: ghcr.io/authrion/nannos-orchestrator:${TAG:-latest}
    restart: unless-stopped
    env_file: [./orchestrator.env]

  keycloak:
    image: quay.io/keycloak/keycloak:26.5.5
    restart: unless-stopped
    command: start --optimized --import-realm
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD}
      KC_HOSTNAME: https://${PUBLIC_HOST}/auth
      KC_HTTP_RELATIVE_PATH: /auth
      KC_PROXY_HEADERS: xforwarded
      KC_HTTP_ENABLED: "true"
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://${KC_DB_HOST}/${KC_DB_NAME}?sslmode=require
      KC_DB_USERNAME: ${KC_DB_USER}
      KC_DB_PASSWORD: ${KC_DB_PASSWORD}
      KC_DB_SCHEMA: keycloak
    volumes:
      - ./realm-export.json:/opt/keycloak/data/import/realm-export.json:ro

  litellm:
    image: ghcr.io/berriai/litellm:main-stable
    restart: unless-stopped
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    env_file: [./litellm.env]
    volumes:
      - ./litellm-config.yaml:/app/config.yaml:ro

volumes:
  caddy-data:
  caddy-config:
```

### deploy/.gitignore

```
*.env
!*.env.example
*.key
*.pem
```

### .github/workflows/build.yml

```yaml
name: build

on:
  push:
    branches: [main, deploy/aws]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    strategy:
      matrix:
        include:
          - name: nannos-orchestrator
            context: packages/orchestrator-agent
            file: packages/orchestrator-agent/Dockerfile.local
            target: ""
          - name: nannos-console-backend
            context: packages/console-backend
            file: packages/console-backend/Dockerfile.local
            target: api
          - name: nannos-console-frontend
            context: packages/console-frontend
            file: packages/console-frontend/Dockerfile
            target: ""
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.file }}
          target: ${{ matrix.target }}
          build-contexts: |
            ringier-a2a-sdk=packages/ringier-a2a-sdk
            agent-common=packages/agent-common
            object-storage=packages/object-storage
          push: true
          tags: |
            ghcr.io/${{ github.repository_owner }}/${{ matrix.name }}:${{ github.sha }}
            ghcr.io/${{ github.repository_owner }}/${{ matrix.name }}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### .github/workflows/deploy.yml

```yaml
name: deploy

on:
  workflow_run:
    workflows: [build]
    types: [completed]
  workflow_dispatch:
    inputs:
      tag:
        description: SHA или latest
        default: latest

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: github.event.workflow_run.conclusion == 'success' || github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4

      - name: Собрать конфиги
        run: |
          mkdir -p out
          cp deploy/docker-compose.prod.yml deploy/Caddyfile \
             deploy/nginx.conf deploy/litellm-config.yaml \
             deploy/realm-export.json out/

          cat > out/.env <<EOF
          PUBLIC_HOST=${{ secrets.PUBLIC_HOST }}
          TAG=${{ inputs.tag || github.event.workflow_run.head_sha || 'latest' }}
          KEYCLOAK_ADMIN_PASSWORD=${{ secrets.KEYCLOAK_ADMIN_PASSWORD }}
          KC_DB_HOST=${{ secrets.KC_DB_HOST }}
          KC_DB_NAME=${{ secrets.KC_DB_NAME }}
          KC_DB_USER=${{ secrets.KC_DB_USER }}
          KC_DB_PASSWORD=${{ secrets.KC_DB_PASSWORD }}
          EOF

          # printf, а не echo: у echo разное поведение с обратными
          # слешами, пароль с "\" может исказиться
          printf '%s\n' "${{ secrets.ORCHESTRATOR_ENV }}"    > out/orchestrator.env
          printf '%s\n' "${{ secrets.CONSOLE_BACKEND_ENV }}" > out/console-backend.env
          printf '%s\n' "${{ secrets.LITELLM_ENV }}"         > out/litellm.env
          chmod 600 out/*.env

      - name: Скопировать
        uses: appleboy/scp-action@v0.1.7
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ubuntu
          key: ${{ secrets.SSH_KEY }}
          source: "out/*"
          target: /opt/nannos
          strip_components: 1

      - name: Перезапустить
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.SSH_HOST }}
          username: ubuntu
          key: ${{ secrets.SSH_KEY }}
          script: |
            cd /opt/nannos
            echo "${{ secrets.GITHUB_TOKEN }}" | docker login ghcr.io -u ${{ github.actor }} --password-stdin
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d --remove-orphans
            docker image prune -f
            docker compose -f docker-compose.prod.yml ps
```

### Коммит

```bash
git add deploy .github/workflows packages/*/Dockerfile.local packages/*/.dockerignore
git commit -m "add AWS deployment"
git push -u origin deploy/aws

# убедиться, что .env не попал
git show --stat HEAD | grep -i env
```

---

## 7. Секреты GitHub

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

### Простые

| Имя | Значение |
|---|---|
| `SSH_HOST` | `13.48.218.238` |
| `SSH_KEY` | содержимое `~/.ssh/nannos_deploy` целиком |
| `PUBLIC_HOST` | `13-48-218-238.sslip.io` |
| `KEYCLOAK_ADMIN_PASSWORD` | сгенерированный |
| `KC_DB_HOST` | `ep-xxx.neon.tech:5432` |
| `KC_DB_NAME` | имя базы |
| `KC_DB_USER` | пользователь Neon |
| `KC_DB_PASSWORD` | пароль Neon |

`SSH_KEY` копируйте через `pbcopy < ~/.ssh/nannos_deploy` — должен начинаться с
`-----BEGIN OPENSSH PRIVATE KEY-----` и заканчиваться `-----END...` с переводом
строки. Потерянная последняя строка даёт `invalid format`.

> **Секрет заменяется целиком, не построчно.** GitHub не умеет править отдельную
> строку: сохранение перезаписывает всё содержимое. Меняете один пароль — вставляйте
> заново весь блок. Урезанный секрет ломает сервис молча: без `POSTGRES_HOST`
> контейнер берёт дефолт образа `127.0.0.1` и уходит в цикл рестартов.
>
> Плейсхолдеры вида `<строка 164 realm-export.json>` подставляйте реальными
> значениями. Такая строка попадает в конфиг как есть и даёт `unauthorized_client`.
>
> Проверить, что секрет доехал целиком:
> ```bash
> ssh ... 'cd /opt/nannos && wc -l *.env'   # ждём 24 и 30 строк
> ```

### ORCHESTRATOR_ENV

```
POSTGRES_HOST=ep-xxx.eu-central-1.aws.neon.tech
POSTGRES_PORT=5432
POSTGRES_DB=имя-базы
POSTGRES_USER=nannos
POSTGRES_PASSWORD=пароль-роли-nannos
POSTGRES_SCHEMA=nannos

OIDC_ISSUER=https://13-48-218-238.sslip.io/auth/realms/nannos
OIDC_CLIENT_ID=orchestrator
OIDC_CLIENT_SECRET=kc-secret-orchestrator

LLM_GATEWAY_URL=http://litellm:4000
LLM_GATEWAY_API_KEY=sk-мастер-ключ

CONSOLE_BACKEND_URL=http://console-backend:5001
CONSOLE_FRONTEND_URL=https://13-48-218-238.sslip.io
AGENT_BASE_URL=http://orchestrator:10001

OBJECT_STORAGE_TYPE=local
LOCAL_STORAGE_PATH=/data/storage
LOG_LEVEL=INFO
LOG_MODE=JSON
LANGSMITH_TRACING=false
SUBAGENT_STREAM_STALL_TIMEOUT_SECONDS=60
```

### CONSOLE_BACKEND_ENV

```
POSTGRES_HOST=ep-xxx.eu-central-1.aws.neon.tech
POSTGRES_PORT=5432
POSTGRES_DB=имя-базы
POSTGRES_USER=console
POSTGRES_PASSWORD=пароль-роли-console
POSTGRES_SCHEMA=console

DOCSTORE_HOST=ep-xxx.eu-central-1.aws.neon.tech
DOCSTORE_PORT=5432
DOCSTORE_DB=имя-базы
DOCSTORE_USER=nannos
DOCSTORE_PASSWORD=пароль-роли-nannos

OIDC_ISSUER=https://13-48-218-238.sslip.io/auth/realms/nannos
OIDC_CLIENT_ID=agent-console
OIDC_CLIENT_SECRET=kc-secret-agent-console

ORCHESTRATOR_CLIENT_ID=orchestrator
ORCHESTRATOR_BASE_DOMAIN=orchestrator:10001
ORCHESTRATOR_ENVIRONMENT=prod
ENVIRONMENT=prod
BASE_DOMAIN=13-48-218-238.sslip.io

LLM_GATEWAY_URL=http://litellm:4000
LLM_GATEWAY_API_KEY=sk-мастер-ключ
LITELLM_MASTER_KEY=sk-мастер-ключ

OBJECT_STORAGE_TYPE=local
LOCAL_STORAGE_PATH=/data/storage
API_PORT=5001
LOG_LEVEL=INFO
LOG_MODE=JSON
```

> **Две ловушки, проверенные на практике.**
>
> `LITELLM_MASTER_KEY` **и** `LLM_GATEWAY_API_KEY` — оба, с одинаковым значением.
> Консоль читает первую, оркестратор вторую. Без первой получите
> `Illegal header value b'Bearer '` и пустой список моделей.
>
> `ORCHESTRATOR_ENVIRONMENT=prod`, и вместе с ним обязательно `BASE_DOMAIN` — в не-local
> режиме `app.py` читает его напрямую через `os.environ`, без него старт падает.
> Локально мы держали `local` ради списка CORS для Socket.IO, но то же значение
> отключает `ProxyHeadersMiddleware`: `request.url_for` тогда строит `http://`, и
> Keycloak отвечает `Invalid parameter: redirect_uri`. На `prod` список CORS
> собирается из `BASE_DOMAIN`, так что обходной путь не нужен вовсе.
>
> `DOCSTORE_*` смотрит в схему оркестратора, поэтому там роль `nannos`, а не `console`.
> Права на чтение выдаёт `GRANT SELECT ON ALL TABLES IN SCHEMA nannos TO console`
> из раздела 5, но подключение всё равно идёт под ролью-владельцем.

### LITELLM_ENV

```
OPENAI_API_KEY=новый-ключ-openai
LITELLM_MASTER_KEY=sk-мастер-ключ
```

> Ключ, использованный при локальной отладке, приходил в переписку открытым текстом.
> Отзовите его и выпустите новый.

---

## 8. Первый запуск

### Сборка

`Actions` → `build` → **Run workflow** → ветка `deploy/aws`

Занимает 5-10 минут. Проверьте раздел **Packages** на странице репозитория — должно
появиться три образа. Если они приватные, деплой не сможет их скачать: откройте
каждый → `Package settings` → `Change visibility` → Public.

### Деплой

`Actions` → `deploy` → **Run workflow** → tag `latest`

### Проверка

```bash
ssh -i ~/.ssh/nannos_deploy ubuntu@13.48.218.238
cd /opt/nannos
docker compose -f docker-compose.prod.yml ps
```

Шесть контейнеров в состоянии `running`. Сертификат Caddy получает за 10-30 секунд.

```bash
curl -sI https://13-48-218-238.sslip.io | head -1
curl -s https://13-48-218-238.sslip.io/api/v1/config | head -c 200
```

Второй запрос должен вернуть JSON. Если приходит HTML — не подключился `nginx.conf`.

Миграции:

```sql
SELECT count(*) FROM console.migrations;  -- 83
SELECT count(*) FROM nannos.migrations;   -- 1
```

### Первый вход

Откройте `https://13-48-218-238.sslip.io`, войдите под `test@local.dev` / `password`.
Запись в `console.users` создаётся при первом входе. Сразу после — выдайте себе права:

```sql
UPDATE console.users SET is_administrator = true, role = 'admin'
WHERE email = 'test@local.dev';
```

### Модель по умолчанию

Без неё агент ответит `No default chat model is configured`:

```sql
INSERT INTO console.model_defaults (role, model_alias)
VALUES ('chat', 'gpt-5-mini')
ON CONFLICT (role) DO UPDATE SET model_alias = EXCLUDED.model_alias;
```

> Именно `gpt-5-mini`. На `gpt-5.6-luna` агент зацикливался: вызывал инструмент `eval`
> с обычной приветственной строкой по четыре раза подряд и вис до срабатывания
> таймаута в 300 секунд. На `gpt-5-mini` ответ приходит за 6 секунд.

Напишите «привет» в чат — ответ должен прийти за несколько секунд.

---

## 9. Если сломалось

```bash
cd /opt/nannos
docker compose -f docker-compose.prod.yml logs --tail 80 console-backend
docker compose -f docker-compose.prod.yml logs --tail 80 orchestrator
docker compose -f docker-compose.prod.yml logs --tail 40 caddy
```

| Симптом | Причина |
|---|---|
| `ssh: invalid format` | `SSH_KEY` скопирован не целиком |
| `Permission denied (publickey)` | Ключа нет в `authorized_keys`, или права не 600 |
| `denied` при pull образов | Образы приватные — сделайте публичными |
| `password authentication failed` | Пароль в секрете не совпал с базой |
| `must be owner of table store` | Таблицы схемы принадлежат другой роли |
| `relation "users" already exists` | Роль названа не как схема — миграции ушли в `public` |
| `relation "migrations" already exists` | То же самое: rambler нашёл таблицу Elysco |
| `Illegal header value b'Bearer '` | Нет `LITELLM_MASTER_KEY` в `CONSOLE_BACKEND_ENV` |
| `Database not ready`, хост `127.0.0.1` | В секрете нет `POSTGRES_HOST` — образ взял свой дефолт |
| 404 на `/auth/realms/...` | В Caddyfile `handle_path` вместо `handle` — префикс срезается |
| 502 на `/api/` от nginx | Бэкенд перезапускался и сменил IP, nginx держит старый |
| `unauthorized_client` при старте | `OIDC_CLIENT_SECRET` не совпадает с `realm-export.json` |
| `Invalid parameter: redirect_uri` | `ENVIRONMENT=local` — прокси-заголовки не читаются, адрес строится как `http://` |
| `CSRF Warning! State not equal` | Старая cookie в браузере. Смена `local`→`prod` добавила флаг `secure`, и браузер держит две cookie `session` под одним именем. Очистить данные сайта |
| `is not an accepted origin` | `ORCHESTRATOR_ENVIRONMENT` не равен `local` |
| `Invalid token: missing subject` | В realm клиентам не назначен scope `basic` |
| `invalid_token` при входе | `OIDC_ISSUER` не совпадает посимвольно |
| Сертификат не выпустился | Порт 80 закрыт в security group |

### Проверить, доехала ли переменная

```bash
docker compose -f docker-compose.prod.yml exec console-backend \
  sh -c 'echo "LITELLM_MASTER_KEY задан: ${LITELLM_MASTER_KEY:+да}"'
```

### Миграции создают таблицы не в той схеме

Самая коварная ошибка: миграции проходят, но таблицы появляются в `public` и
конфликтуют с Elysco. Проверьте, куда смотрит роль:

```sql
-- под ролью сервиса, не под neondb_owner
SELECT current_user, current_schema, setting AS search_path
  FROM pg_settings WHERE name = 'search_path';
```

`current_schema` должна совпадать с именем роли. Если там `public` — роль названа
иначе, чем схема, либо схема не создана. Исправляется только созданием роли с
правильным именем; `RAMBLER_TABLE` эту проблему не решает, мы проверяли.

### Что не заработает — и это нормально

| Что | Почему |
|---|---|
| Инструменты MCP | `gatana` — боевой шлюз Ringier, локально его нет |
| Голосовой агент | Отдельный сервис, не разворачивается |
| `LLM risk scoring failed` | Переходит на запасной алгоритм |
| Семантический поиск | Заработает после назначения модели для роли embedding |

Чат работает без всего перечисленного.

---

## 10. Синхронизация с апстримом

`Authrion/nannos` — форк активного `ringier-data/nannos`: около 59 коммитов в месяц.

**Главное правило:** добавляйте файлы, не редактируйте чужие. Git конфликтует только
там, где обе стороны правили одну строку — новые файлы под это не подпадают.

Каталогов `deploy/` и `.github/workflows/` в апстриме нет: Ringier деплоит через
FluxCD в Kubernetes и GitHub Actions не использует. Эта территория ваша.

### Подключить upstream (один раз)

```bash
git remote add upstream https://github.com/ringier-data/nannos.git
```

### Слияние

```bash
git fetch upstream
git log --oneline HEAD..upstream/main | head -20

# проверить конфликты, не фиксируя результат
git merge --no-commit --no-ff upstream/main

git commit -m "merge upstream"   # если чисто
git merge --abort                # если нет
```

### Если апстрим изменил Dockerfile

Единственное место, где нужна ручная работа:

```bash
git log --oneline HEAD..upstream/main \
  -- packages/orchestrator-agent/Dockerfile packages/console-backend/Dockerfile
```

Если есть изменения — пересоздайте копию одной командой:

```bash
sed 's|^FROM docker.rcplus.io/|FROM |' \
  packages/orchestrator-agent/Dockerfile \
  > packages/orchestrator-agent/Dockerfile.local
```

Замена ровно одна: убрать префикс закрытого реестра Ringier.

### Чего избегать

| | Действие | Почему |
|---|---|---|
| ✗ | Править `packages/*/Dockerfile` | Конфликт при каждом их изменении |
| ✗ | Править `justfile`, `pyproject.toml`, `uv.lock` | Меняются часто |
| ✗ | Коммитить `.env` с реальными значениями | Из истории git это не убрать |
| ✗ | `git rebase upstream/main` | Переписывает историю |
| ✓ | Новые файлы и каталоги | Не конфликтуют никогда |
| ✓ | `git merge` с проверкой `--no-commit` | Видно результат до фиксации |

---

## Дальше стоит сделать

- **Бэкап схемы `keycloak`** — там пользователи и клиенты. Без неё потеряете доступ.
- **Ограничить SSH** адресами GitHub Actions или поднять бастион.
- **Ротация** ключа OpenAI и секретов Keycloak раз в квартал.
- **Свой домен** вместо sslip.io — меняется `PUBLIC_HOST` и адреса возврата в Keycloak.
- **Логи** пишутся в контейнеры и теряются при пересоздании. Стоит завести драйвер
  логов или CloudWatch.
