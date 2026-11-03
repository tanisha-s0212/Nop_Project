"""Local JSON command interface for the existing business query service."""

import argparse
import json
from pathlib import Path

from .query import DynamicBusinessQueryService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--question")
    inputs.add_argument("--request", type=Path, help="JSON request file")
    arguments = parser.parse_args()
    try:
        request = json.loads(arguments.request.read_text(encoding="utf-8-sig")) if arguments.request else arguments.question
        result = DynamicBusinessQueryService(arguments.root).process(request)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
