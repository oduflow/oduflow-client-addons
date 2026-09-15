#!/bin/sh
set -eu

ai_uid="${ODUPILOT_UID:-1000}"
ai_gid="${ODUPILOT_GID:-1000}"

runtime_group=$(awk -F: -v gid="$ai_gid" '$3 == gid { print $1; exit }' /etc/group)
if [ -z "$runtime_group" ]; then
    runtime_group=odupilot
    addgroup -S -g "$ai_gid" "$runtime_group"
fi

runtime_user=$(awk -F: -v uid="$ai_uid" '$3 == uid { print $1; exit }' /etc/passwd)
if [ -z "$runtime_user" ]; then
    runtime_user=odupilot
    adduser -S -D -H -u "$ai_uid" -G "$runtime_group" \
        -h /var/lib/opencode "$runtime_user"
fi

install -d -m 0700 -o "$ai_uid" -g "$ai_gid" \
    /var/lib/opencode \
    /var/lib/opencode/.cache \
    /var/lib/opencode/.config \
    /var/lib/opencode/.local \
    /var/lib/opencode/.local/share \
    /var/lib/opencode/.local/state
install -d -m 0750 -o "$ai_uid" -g "$ai_gid" /workspace

export HOME=/var/lib/opencode

exec su-exec "$runtime_user:$runtime_group" opencode "$@"
