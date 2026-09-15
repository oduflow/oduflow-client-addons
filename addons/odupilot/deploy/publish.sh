#!/bin/sh
set -eu

usage() {
    cat <<'EOF'
Usage: ./addons/odupilot/deploy/publish.sh [IMAGE_TAG]

Build and publish the OduPilot bridge and OpenCode images for Apple Silicon
Macs and amd64 Linux servers as multi-architecture manifests.

Arguments:
  IMAGE_TAG  Immutable application tag. Defaults to the current short git SHA.

Environment:
  REGISTRY_NAMESPACE  Registry namespace (default: oduist)
  BUILDER_NAME         Dedicated Buildx builder (default: odupilot-multiarch)
  PLATFORMS            Target platforms (default: linux/amd64,linux/arm64)
  DRY_RUN              Set to 1 to print build commands without running them
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    usage
    exit 0
fi

if [ "$#" -gt 1 ]; then
    usage >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(git -C "$script_dir" rev-parse --show-toplevel)
context="$script_dir"

registry_namespace=${REGISTRY_NAMESPACE:-oduist}
builder_name=${BUILDER_NAME:-odupilot-multiarch}
image_tag=${1:-$(git -C "$repo_root" rev-parse --short=9 HEAD)}
opencode_version=$(sed -n \
    's|^ARG OPENCODE_IMAGE=.*opencode:\([^@]*\)@.*|\1|p' \
    "$context/Dockerfile.opencode")
platforms=${PLATFORMS:-linux/amd64,linux/arm64}
dry_run=${DRY_RUN:-0}

if [ -z "$opencode_version" ]; then
    echo "Cannot determine the pinned OpenCode version" >&2
    exit 1
fi

case "$registry_namespace" in
    ''|*[!A-Za-z0-9._/-]*)
        echo "Invalid REGISTRY_NAMESPACE: $registry_namespace" >&2
        exit 2
        ;;
esac
case "$image_tag" in
    ''|*[!A-Za-z0-9_.-]*)
        echo "Invalid IMAGE_TAG: $image_tag" >&2
        exit 2
        ;;
esac
case "$builder_name" in
    ''|*[!A-Za-z0-9_.-]*)
        echo "Invalid BUILDER_NAME: $builder_name" >&2
        exit 2
        ;;
esac
case "$opencode_version" in
    ''|*[!A-Za-z0-9_.-]*)
        echo "Invalid OPENCODE_VERSION: $opencode_version" >&2
        exit 2
        ;;
esac

bridge_image="$registry_namespace/odupilot-bridge:$image_tag"
opencode_image="$registry_namespace/odupilot-opencode:$opencode_version-$image_tag"

ensure_builder() {
    if docker buildx inspect "$builder_name" >/dev/null 2>&1; then
        driver=$(docker buildx inspect "$builder_name" | sed -n \
            's/^Driver:[[:space:]]*//p' | head -n 1)
        if [ "$driver" != "docker-container" ]; then
            echo "Buildx builder '$builder_name' uses unsupported driver '$driver'." >&2
            echo "Set BUILDER_NAME to a new name and run the command again." >&2
            exit 1
        fi
    else
        echo "Creating Buildx builder $builder_name with docker-container driver"
        docker buildx create \
            --name "$builder_name" \
            --driver docker-container >/dev/null
    fi
    echo "Bootstrapping Buildx builder $builder_name"
    docker buildx inspect "$builder_name" --bootstrap >/dev/null
}

run_build() {
    dockerfile=$1
    image=$2
    echo "Publishing $image for $platforms"
    if [ "$dry_run" = "1" ]; then
        echo "docker buildx build --builder $builder_name --platform $platforms --file $dockerfile --tag $image --push $context"
        return
    fi
    docker buildx build \
        --builder "$builder_name" \
        --platform "$platforms" \
        --file "$dockerfile" \
        --build-arg "ODUPILOT_BRIDGE_VERSION=$image_tag" \
        --tag "$image" \
        --push \
        "$context"
}

command -v docker >/dev/null 2>&1 || {
    echo "docker is required" >&2
    exit 1
}
docker buildx version >/dev/null

if [ "$dry_run" != "1" ]; then
    ensure_builder
fi

run_build "$context/Dockerfile" "$bridge_image"
run_build "$context/Dockerfile.opencode" "$opencode_image"

if [ "$dry_run" = "1" ]; then
    echo "Dry-run images:"
else
    echo "Published:"
fi
echo "  $bridge_image"
echo "  $opencode_image"
