"""
This create a neon; saves the database pooled and non pooled url to the root .env; runs mmigration based on the databse models already created.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://console.neon.tech/api/v2"

PROJECT_NAME = "myapi"
REGION_ID = "aws-us-east-1"  # AWS US 1 / US East
PG_VERSION = 18
BRANCH_NAME = "main"
DB_NAME = "food"
ROLE_NAME = "food_owner"
SAFE_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_name(value: str, field: str) -> str:
    """
    Allow only simple CLI-safe names.

    Good:
        food
        food_owner
        myapi-prod

    Bad:
        food; rm -rf /
        $(whoami)
        name with spaces
    """
    if not SAFE_NAME.fullmatch(value):
        raise ValueError(f"Invalid {field}: {value!r}")

    return value


def require_api_key() -> str:
    api_key = os.environ.get("NEON_API_KEY")
    if not api_key:
        raise SystemExit(
            "Missing NEON_API_KEY.\n"
            "Run this first:\n\n"
            "  export NEON_API_KEY='paste_your_neon_api_key_here'\n"
        )
    return api_key


def api_request(
    method: str,
    path: str,
    api_key: str,
    payload: dict | None = None,
) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print("\nNeon API error response:", file=sys.stderr)
        print(body, file=sys.stderr)
        raise SystemExit(f"Neon API failed: HTTP {e.code}") from e


def wait_for_operations(project_id: str, operations: list[dict], api_key: str) -> None:
    if not operations:
        return

    print("Waiting for Neon operations to finish...")

    for op in operations:
        op_id = op["id"]

        while True:
            data = api_request(
                "GET",
                f"/projects/{project_id}/operations/{op_id}",
                api_key,
            )

            status = data["operation"]["status"]
            print(f"  operation {op_id}: {status}")

            if status == "finished":
                break

            if status in {"failed", "error", "cancelled"}:
                raise SystemExit(f"Operation failed: {op_id} status={status}")

            time.sleep(2)


def find_neon_cli() -> str:
    for name in ("neonctl", "neon"):
        path = shutil.which(name)
        if path:
            return path

    raise SystemExit(
        "Neon CLI not found.\n"
        "Install the pinned Linux x64 binary first, then rerun this script."
    )


def to_sqlalchemy_psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url

    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)

    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)

    raise ValueError(f"Not a Postgres URL: {url}")


def run_neon_cli(cli: str, args: list[str], api_key: str) -> str:
    env = os.environ.copy()
    env["NEON_API_KEY"] = api_key

    try:
        result = subprocess.run(
            [cli, *args],
            check=True,
            capture_output=True,  # if output is large; stream to file; output stored in memory
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("neonctl timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"neonctl failed with exit code {exc.returncode}: {exc.stderr.strip()}"
        ) from exc

    url = to_sqlalchemy_psycopg_url(result.stdout.strip()).split("?")[0]

    return url


def get_connection_string(
    cli: str,
    api_key: str,
    project_id: str,
    pooled: bool,
) -> str:
    args = [
        "connection-string",
        BRANCH_NAME,
        "--project-id",
        project_id,
        "--database-name",
        DB_NAME,
        "--role-name",
        ROLE_NAME,
    ]

    if pooled:
        args.append("--pooled")

    return run_neon_cli(cli, args, api_key)


def find_project_root(start: Path | None = None) -> Path:
    """
    Find project root by walking upward until we see common root markers.
    """
    current = (start or Path.cwd()).resolve()

    root_markers = {
        ".git",
        "pyproject.toml",
        "uv.lock",
        "requirements.txt",
    }

    for path in [current, *current.parents]:
        if any((path / marker).exists() for marker in root_markers):
            return path

    raise RuntimeError(f"Could not find project root from: {current}")


def write_env_values(env_path: Path, values: dict[str, str]) -> None:
    """
    Update existing keys in .env.
    Append missing keys.
    Preserve comments and unrelated values.
    """
    existing_lines: list[str] = []

    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    keys_to_write = set(values)
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue

        key = line.split("=", 1)[0].strip()

        if key in values:
            new_lines.append(f"{key}={values[key]}")
            keys_to_write.remove(key)
        else:
            new_lines.append(line)

    if keys_to_write:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")

        for key in keys_to_write:
            new_lines.append(f"{key}={values[key]}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.chmod(env_path, 0o600)


def main() -> None:
    api_key = "....."
    cli = find_neon_cli()

    payload = {
        "project": {
            "name": PROJECT_NAME,
            "region_id": REGION_ID,
            "pg_version": PG_VERSION,
            "branch": {
                "name": BRANCH_NAME,
                "database_name": DB_NAME,
                "role_name": ROLE_NAME,
            },
        }
    }

    print("Creating Neon project...")
    created = api_request("POST", "/projects", api_key, payload)

    project = created["project"]
    project_id = project["id"]

    print(f"Created project: {project['name']}")
    print(f"Project ID: {project_id}")
    print(f"Region: {project['region_id']}")
    print(f"Postgres version: {project['pg_version']}")

    wait_for_operations(project_id, created.get("operations", []), api_key)

    print("Getting direct connection string...")
    direct_url = get_connection_string(
        cli=cli,
        api_key=api_key,
        project_id=project_id,
        pooled=False,
    )

    print("Getting pooled connection string...")
    pooled_url = get_connection_string(
        cli=cli,
        api_key=api_key,
        project_id=project_id,
        pooled=True,
    )

    env_path = find_project_root() / ".env"

    write_env_values(
        env_path,
        {
            "DATABASE_URL_DIRECT": direct_url,
            "DATABASE_URL_POOLED": pooled_url,
        },
    )

    print("\nDone.\n")
    print("\nSaved urls in the project's .env file.")


if __name__ == "__main__":
    main()
