"""Register durable Harbor recovery without any model invocation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    commands = parser.add_subparsers(dest="command", required=True)
    arm = commands.add_parser("arm")
    arm.add_argument("--file", required=True)
    arm.add_argument("--thread-id")
    commands.add_parser("list")
    settings = commands.add_parser("settings")
    settings.add_argument("--allow-luna-reserve", choices=["true", "false"])
    cancel = commands.add_parser("cancel")
    cancel.add_argument("watch_id")
    args = parser.parse_args()
    url = urlparse(args.base_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "::1"}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        parser.error("base URL must be an HTTP loopback origin")
    path = "/api/recovery-watches"
    body = None
    method = "GET"
    if args.command == "arm":
        payload = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
        thread_id = (
            args.thread_id
            or os.getenv("CODEX_THREAD_ID")
            or os.getenv("CODEX_SESSION_ID")
        )
        if not thread_id:
            parser.error(
                "current thread id is unavailable; supply a verified --thread-id"
            )
        if payload.get("thread_id") and payload["thread_id"] != thread_id:
            parser.error("request thread_id differs from current/explicit thread id")
        payload["thread_id"] = thread_id
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
    elif args.command == "settings":
        path = "/api/recovery-settings"
        if args.allow_luna_reserve is not None:
            method = "PATCH"
            body = json.dumps(
                {"allow_luna_reserve": args.allow_luna_reserve == "true"}
            ).encode()
    elif args.command == "cancel":
        if not args.watch_id.isalnum():
            parser.error("invalid recovery watch id")
        path += f"/{args.watch_id}/cancel"
        method, body = "POST", b"{}"
    request = Request(
        args.base_url.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with build_opener(NoRedirect).open(request, timeout=45) as response:
            result = json.loads(response.read())
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except HTTPError as error:
        print(error.read().decode("utf-8", errors="replace"), file=sys.stderr)
        raise SystemExit(1) from error
    except URLError as error:
        print(f"Harbor is unreachable: {error.reason}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
