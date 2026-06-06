from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def get_json(base_url: str, path: str) -> dict:
    url = f"{base_url.rstrip('/')}{path}"

    with urllib.request.urlopen(url, timeout=10) as response:
        body = response.read().decode("utf-8")

        if response.status < 200 or response.status >= 400:
            raise RuntimeError(f"{url} returned HTTP {response.status}")

        return json.loads(body)


def check_status(base_url: str, path: str, expected: str) -> None:
    data = get_json(base_url, path)

    actual = data.get("status")
    if actual != expected:
        raise RuntimeError(f"{path} expected status={expected}, got {actual}")

    print(f"OK {path} status={actual}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--expect-git-sha")
    parser.add_argument("--info-path", default="/")
    args = parser.parse_args()

    check_status(args.base_url, "/health/live", "alive")
    check_status(args.base_url, "/health/ready", "ready")

    info = get_json(args.base_url, args.info_path)

    print(f"OK {args.info_path} name={info.get('name')}")
    print(f"OK git_sha={info.get('git_sha')}")
    print(f"OK environment={info.get('environment')}")

    if args.expect_git_sha and info.get("git_sha") != args.expect_git_sha:
        raise RuntimeError(
            f"Expected git_sha={args.expect_git_sha}, got {info.get('git_sha')}"
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SMOKE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
