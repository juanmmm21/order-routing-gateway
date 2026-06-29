from __future__ import annotations

from order_routing_gateway.live_router import LiveOrderRouter
from order_routing_gateway.models import GatewayConfig, RoutingMode
from order_routing_gateway.paper_router import PaperTradingRouter
from order_routing_gateway.protocols import HttpTransport, OrderRouter


class OrderRoutingGateway:
    """Selecciona el router adecuado según modo paper o live."""

    def __init__(
        self,
        config: GatewayConfig,
        transport: HttpTransport | None = None,
        api_key: str = "",
        api_secret: str = "",
    ) -> None:
        self._config = config
        self._router = self._build_router(config, transport, api_key, api_secret)

    @property
    def config(self) -> GatewayConfig:
        return self._config

    @property
    def router(self) -> OrderRouter:
        return self._router

    def _build_router(
        self,
        config: GatewayConfig,
        transport: HttpTransport | None,
        api_key: str,
        api_secret: str,
    ) -> OrderRouter:
        if config.mode is RoutingMode.PAPER:
            return PaperTradingRouter(config)
        return LiveOrderRouter(
            config=config,
            transport=transport,
            api_key=api_key,
            api_secret=api_secret,
        )
