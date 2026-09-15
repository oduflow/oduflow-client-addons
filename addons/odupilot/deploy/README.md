# OduPilot infrastructure

This stack runs a pinned OpenCode server and the bidirectional Odoo bridge.
It intentionally exposes no OpenCode host port: only the bridge shares its
private Docker network. OpenCode and the bridge mount the same external
workspace volume with the same numeric UID/GID. Odoo uses only authenticated
RPC over `ODOO_URL`, may run on another server and never mounts this volume.
The bridge polls `/odupilot/bridge/poll` on the ordinary Odoo HTTP endpoint.
Empty responses are followed by a one-second wait. Bus wake-ups contain no
command data or secrets. Configure Odoo 19 WebSockets for browser Discuss.

Copy `.env.example` to `.env`, set every secret and deployment-specific value,
then create the shared volume before starting the stack:

```sh
docker volume create odupilot-workspace
docker compose up -d --build
```

OpenCode state is stored in the `odupilot-opencode-home` volume. Docker restarts
the process after an OOM kill; OpenCode sessions remain available after the
restart.

Both images carry the pinned AnyDoc document converter: the bridge converts
every supported attachment to Markdown while writing it into the workspace, and
the OpenCode image exposes the same converter as the `anydoc` command. Keep
`ANYDOC_VERSION` in `Dockerfile.opencode` and `firecrawl-anydoc` in
`requirements.txt` on the same version.

## Publishing images

From the repository root, publish both images for Apple Silicon Macs and amd64
Linux servers under one multi-architecture tag:

```sh
./addons/odupilot/deploy/publish.sh
```

The default application tag is the current nine-character git SHA. Pass an
explicit tag when reproducing an earlier deployment:

```sh
./addons/odupilot/deploy/publish.sh c2a2fc641
```

The script creates and bootstraps a dedicated `docker-container` Buildx builder
named `odupilot-multiarch`; this also works when Docker Desktop or OrbStack has
selected a default `docker` builder that cannot publish multiple platforms.
Set `BUILDER_NAME`, `REGISTRY_NAMESPACE` or `PLATFORMS` to override their
defaults. The OpenCode tag version is read from the pinned base image in
`Dockerfile.opencode`. `DRY_RUN=1` prints both build commands without publishing
anything.

For the M0 acceptance check, create a directory containing a valid
`opencode.json` with the profile's LiteLLM key and run:

```sh
ODUPILOT_SMOKE_DIRECTORY=/workspace/smoke \
ODUPILOT_SMOKE_MODEL=your-model \
OPENCODE_SERVER_PASSWORD=... \
docker compose exec -T bridge sh /app/smoke.sh
```

The bridge uses a dedicated Odoo technical user. That user needs the **OduPilot
Bridge Service** group (`odupilot.group_bridge`) and nothing else; bridge RPC
methods reject every other caller, including system administrators.
