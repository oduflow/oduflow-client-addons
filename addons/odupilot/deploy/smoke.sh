#!/bin/sh
set -eu

: "${OPENCODE_URL:=http://127.0.0.1:4096}"
: "${OPENCODE_SERVER_USERNAME:=opencode}"
: "${OPENCODE_SERVER_PASSWORD:?Set OPENCODE_SERVER_PASSWORD}"
: "${ODUPILOT_SMOKE_DIRECTORY:?Set ODUPILOT_SMOKE_DIRECTORY}"
: "${ODUPILOT_SMOKE_MODEL:?Set ODUPILOT_SMOKE_MODEL}"

auth="${OPENCODE_SERVER_USERNAME}:${OPENCODE_SERVER_PASSWORD}"
encoded_directory=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$ODUPILOT_SMOKE_DIRECTORY")

curl --fail --silent --show-error --user "$auth" \
  "$OPENCODE_URL/global/health"

session=$(curl --fail --silent --show-error --user "$auth" \
  -H 'Content-Type: application/json' \
  -d '{"title":"odupilot smoke test"}' \
  "$OPENCODE_URL/session?directory=$encoded_directory")
session_id=$(printf '%s' "$session" | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])')

payload=$(ODUPILOT_SMOKE_MODEL="$ODUPILOT_SMOKE_MODEL" python3 -c '
import json, os
print(json.dumps({
    "model": {"providerID": "litellm", "modelID": os.environ["ODUPILOT_SMOKE_MODEL"]},
    "parts": [{"type": "text", "text": "Reply with exactly: odupilot smoke ok"}],
}))
')

curl --fail --silent --show-error --user "$auth" \
  -H 'Content-Type: application/json' \
  -d "$payload" \
  "$OPENCODE_URL/session/$session_id/message?directory=$encoded_directory"
