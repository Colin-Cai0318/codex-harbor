#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description="Call the Codex Harbor loopback API")
    parser.add_argument("method", choices=["GET", "POST", "PATCH", "DELETE"])
    parser.add_argument("path", help="API path beginning with /api/")
    parser.add_argument("--data", help="JSON request object")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme != "http" or parsed.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        parser.error("base URL must be an HTTP loopback address")
    if not args.path.startswith("/api/"):
        parser.error("path must begin with /api/")
    body = args.data.encode("utf-8") if args.data is not None else None
    if body is not None:
        json.loads(args.data)
    request = Request(
        args.base_url.rstrip("/") + args.path,
        data=body,
        method=args.method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
            print(
                json.dumps(json.loads(payload), indent=2, ensure_ascii=False)
                if payload
                else "{}"
            )
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        print(detail or str(error), file=sys.stderr)
        raise SystemExit(1)
    except URLError as error:
        print(f"Codex Harbor is unreachable: {error.reason}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
