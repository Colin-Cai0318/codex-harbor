from urllib.parse import urlsplit

from starlette.responses import JSONResponse


class LocalRequestGuard:
    """Local-user HTTP boundary, including form CSRF and DNS rebinding."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])
        hosts = [v.decode("latin1") for k, v in headers if k.lower() == b"host"]
        origins = [v.decode("latin1") for k, v in headers if k.lower() == b"origin"]
        try:
            target = (
                urlsplit(f"{scope.get('scheme', 'http')}://{hosts[0]}")
                if len(hosts) == 1
                else None
            )
            valid = (
                target
                and target.hostname in {"127.0.0.1", "localhost", "::1"}
                and not target.username
                and not target.password
                and not target.path
                and not target.query
                and not target.fragment
            )
            if target:
                target_port = target.port or (443 if target.scheme == "https" else 80)
        except ValueError:
            valid = False
        if not valid:
            return await JSONResponse(
                {"detail": "Only local Host headers are accepted"}, status_code=400
            )(scope, receive, send)
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            fetch_sites = [v for k, v in headers if k.lower() == b"sec-fetch-site"]
            same_origin = not origins
            if len(origins) == 1:
                try:
                    origin = urlsplit(origins[0])
                    same_origin = (
                        (
                            origin.scheme,
                            origin.hostname,
                            origin.port or (443 if origin.scheme == "https" else 80),
                        )
                        == (
                            target.scheme,
                            target.hostname,
                            target_port,
                        )
                        and not origin.username
                        and not origin.password
                        and not origin.path
                        and not origin.query
                        and not origin.fragment
                    )
                except ValueError:
                    same_origin = False
            if not same_origin or b"cross-site" in fetch_sites:
                return await JSONResponse(
                    {"detail": "Cross-origin mutations are not permitted"},
                    status_code=403,
                )(scope, receive, send)
        await self.app(scope, receive, send)
