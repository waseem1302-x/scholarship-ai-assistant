"""Trusted proxy handling for the supported production ingress modes."""

from collections.abc import Awaitable, Callable

from uvicorn._types import ASGIReceiveCallable, ASGISendCallable, Scope


class AzureContainerAppsProxyHeadersMiddleware:
    """Accept only Azure Container Apps' safe forwarding semantics.

    Azure Container Apps overwrites ``X-Forwarded-Proto`` and appends the
    connection's client address as the rightmost ``X-Forwarded-For`` value.
    The app container is reachable only through that ingress, so this adapter
    deliberately uses that rightmost value instead of accepting an arbitrary
    value a browser may have supplied earlier in the header.
    """

    def __init__(
        self,
        app: Callable[[Scope, ASGIReceiveCallable, ASGISendCallable], Awaitable[None]],
    ) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        forwarded_proto = headers.get(b"x-forwarded-proto", b"").decode("latin1").strip()
        if forwarded_proto in {"http", "https", "ws", "wss"}:
            scope["scheme"] = (
                forwarded_proto.replace("http", "ws")
                if scope["type"] == "websocket"
                else forwarded_proto
            )

        forwarded_for = headers.get(b"x-forwarded-for", b"").decode("latin1")
        client_ip = forwarded_for.rsplit(",", maxsplit=1)[-1].strip()
        if client_ip:
            current_port = scope.get("client", ("", 0))[1]
            scope["client"] = (client_ip, current_port)

        await self.app(scope, receive, send)
