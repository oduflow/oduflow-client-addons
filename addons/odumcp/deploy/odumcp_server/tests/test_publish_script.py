from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

PUBLISH_SCRIPT = Path(__file__).parents[2] / "publish.sh"


def _fake_docker(tmp_path: Path, manifest_result: str) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "docker-calls"
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >>"$DOCKER_CALLS"\n'
        'if [ "$1 $2" = "buildx version" ]; then exit 0; fi\n'
        'if [ "$1 $2" = "manifest inspect" ]; then\n'
        f"  {manifest_result}\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(docker.stat().st_mode | stat.S_IXUSR)
    return bin_dir, calls


def _run_publish(tmp_path: Path, manifest_result: str, **variables: str):
    bin_dir, calls = _fake_docker(tmp_path, manifest_result)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "DOCKER_CALLS": str(calls),
        **variables,
    }
    result = subprocess.run(  # noqa: S603 - test executes the repository script
        ["/bin/bash", str(PUBLISH_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    return result, calls.read_text(encoding="utf-8")


def test_registry_failure_aborts_instead_of_overwriting(tmp_path: Path) -> None:
    result, calls = _run_publish(
        tmp_path,
        'echo "unauthorized: token service unavailable" >&2; exit 1',
        SKIP_TESTS="1",
    )

    assert result.returncode != 0
    assert "Could not verify" in result.stderr
    assert "buildx build" not in calls


def test_missing_manifest_allows_a_dry_run(tmp_path: Path) -> None:
    result, calls = _run_publish(
        tmp_path,
        'echo "manifest unknown" >&2; exit 1',
        DRY_RUN="1",
    )

    assert result.returncode == 0
    assert "docker buildx build" in result.stdout
    assert "manifest inspect" in calls


def test_missing_uv_aborts_unless_skip_is_explicit(tmp_path: Path) -> None:
    result, calls = _run_publish(
        tmp_path,
        'echo "manifest unknown" >&2; exit 1',
    )

    assert result.returncode != 0
    assert "uv is required" in result.stderr
    assert "buildx build" not in calls


def test_explicit_test_skip_allows_publish(tmp_path: Path) -> None:
    result, calls = _run_publish(
        tmp_path,
        'echo "manifest unknown" >&2; exit 1',
        SKIP_TESTS="1",
    )

    assert result.returncode == 0
    assert "buildx build" in calls
