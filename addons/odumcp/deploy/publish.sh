#!/usr/bin/env bash
# Собирает и публикует образ odumcp_server на Docker Hub.
#
# Пушит два тега: версию из pyproject.toml и latest. Требуется `docker login`
# с правом записи в целевой namespace (по умолчанию oduist) — тот же образ,
# что указан в odumcp_server/docker-compose.example.yml.
#
# Использование:
#   ./addons/odumcp/deploy/publish.sh
#
# Переменные окружения:
#   ODUMCP_REGISTRY   namespace на Docker Hub (по умолчанию oduist)
#   ODUMCP_PLATFORM   целевые платформы (по умолчанию linux/amd64)
#   ODUMCP_OVERWRITE  1 — разрешить перезапись уже опубликованной версии
#   SKIP_TESTS             1 — не прогонять pytest перед сборкой
#   DRY_RUN                1 — только показать команды сборки
set -euo pipefail
cd "$(dirname "$0")/odumcp_server"

VERSION="$(grep -m1 -E '^version *=' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')"
[ -n "${VERSION:-}" ] || { echo "Could not read version from pyproject.toml" >&2; exit 1; }

REGISTRY="${ODUMCP_REGISTRY:-oduist}"
PLATFORM="${ODUMCP_PLATFORM:-linux/amd64}"
OVERWRITE="${ODUMCP_OVERWRITE:-0}"
SKIP_TESTS="${SKIP_TESTS:-0}"
DRY_RUN="${DRY_RUN:-0}"
IMAGE="$REGISTRY/odumcp_server"

command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 1; }
docker buildx version >/dev/null

# Версия образа неизменяемая: перезапись опубликованного тега оставила бы
# развёрнутые окружения с непонятно каким кодом под тем же номером.
if [ "$OVERWRITE" != "1" ]; then
    set +e
    MANIFEST_OUTPUT="$(docker manifest inspect "$IMAGE:$VERSION" 2>&1)"
    MANIFEST_STATUS=$?
    set -e
    if [ "$MANIFEST_STATUS" -eq 0 ]; then
        echo "$IMAGE:$VERSION is already published." >&2
        echo "Bump version in pyproject.toml, or set ODUMCP_OVERWRITE=1 to replace it." >&2
        exit 1
    fi
    if ! grep -Eqi 'manifest unknown|no such manifest|not found' <<<"$MANIFEST_OUTPUT"; then
        echo "Could not verify whether $IMAGE:$VERSION is already published." >&2
        echo "$MANIFEST_OUTPUT" >&2
        exit 1
    fi
fi

if [ "$SKIP_TESTS" != "1" ] && [ "$DRY_RUN" != "1" ]; then
    command -v uv >/dev/null 2>&1 || {
        echo "uv is required to run release checks; install it or explicitly set SKIP_TESTS=1" >&2
        exit 1
    }
    echo "Running the sidecar test suite"
    uv run --extra test pytest -q
    uv run --extra test ruff check src tests
fi

echo "Publishing $IMAGE:{$VERSION,latest} ($PLATFORM)"
if [ "$DRY_RUN" = "1" ]; then
    echo "docker buildx build --platform $PLATFORM -t $IMAGE:$VERSION -t $IMAGE:latest --push ."
    exit 0
fi

docker buildx build --platform "$PLATFORM" \
    -t "$IMAGE:$VERSION" -t "$IMAGE:latest" --push .

echo "Done: $IMAGE:{$VERSION,latest}"
echo "Deployed hosts pull the new image with: docker compose pull && docker compose up -d"
