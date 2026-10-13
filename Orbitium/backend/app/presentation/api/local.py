import ipaddress
from urllib.parse import urlsplit
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import JSONResponse


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: tuple[str, ...]) -> None:
        self.app, self.allowed_origins = app, allowed_origins

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        try:
            local_client = ipaddress.ip_address(scope["client"][0]).is_loopback
            host = urlsplit("http://" + headers.get("host", "")).hostname
            allowed = local_client and host in ("localhost", "127.0.0.1", "::1")
        except (ValueError, TypeError):
            allowed = False
        origin = headers.get("origin")
        if not allowed or (origin is not None and origin not in self.allowed_origins):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": "Esta etapa solo admite acceso local"}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)
