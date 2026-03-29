from __future__ import annotations
import json
from pathlib import Path
import yaml  # pip install pyyaml
from app.main import app  # change this import to your real module path


def main() -> None:
    schema = app.openapi()
    Path("openapi.json").write_text(
        json.dumps(schema, indent=2) + "\n",
        encoding="utf-8",
    )

    Path("openapi.yaml").write_text(
        yaml.safe_dump(
            schema,
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
