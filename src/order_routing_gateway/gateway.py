from __future__ import annotations

from order_routing_gateway.binance_client import (
    BinanceCredentials,
    BinanceSpotClient,
    RawHttpTransport,
)
from order_routing_gateway.live_router import LiveOrderRouter
from order_routing_gateway.models import GatewayConfig, RoutingMode
from order_routing_gateway.paper_router import PaperTradingRouter
from order_routing_gateway.protocols import HttpTransport, OrderRouter
from order_routing_gateway.testnet_router import TestnetOrderRouter


class OrderRoutingGateway:
    """Selecciona el router adecuado según modo paper o live."""

    def __init__(
        self,
        config: GatewayConfig,
        transport: HttpTransport | None = None,
        api_key: str = "",
        api_secret: str = "",
        raw_transport: RawHttpTransport | None = None,
    ) -> None:
        self._config = config
        self._router = self._build_router(config, transport, api_key, api_secret, raw_transport)

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
        raw_transport: RawHttpTransport | None,
    ) -> OrderRouter:
        if config.mode is RoutingMode.PAPER:
            return PaperTradingRouter(config)
        if config.mode is RoutingMode.TESTNET:
            client = BinanceSpotClient(BinanceCredentials.from_env(), transport=raw_transport)
            return TestnetOrderRouter(config, client)
        return LiveOrderRouter(
            config=config,
            transport=transport,
            api_key=api_key,
            api_secret=api_secret,
        )
