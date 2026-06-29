from __future__ import annotations

from typing import Protocol

from order_routing_gateway.models import (
    ExchangeOrderRequest,
    GatewayConfig,
    InternalOrder,
    OrderAcknowledgement,
    PriceTick,
    RoutedFill,
    RoutingResult,
)


class ExchangeOrderAdapter(Protocol):
    """Traduce órdenes internas al formato REST del exchange."""

    def build_request(self, order: InternalOrder) -> ExchangeOrderRequest:
        ...

    def parse_acknowledgement(
        self,
        order: InternalOrder,
        response_body: dict[str, object],
    ) -> OrderAcknowledgement:
        ...

    def parse_fill(
        self,
        order: InternalOrder,
        response_body: dict[str, object],
        commission_rate: object,
    ) -> RoutedFill:
        ...


class OrderRouter(Protocol):
    """Envía órdenes al destino configurado (paper o live)."""

    def route_order(
        self,
        order: InternalOrder,
        market_price: PriceTick | None = None,
    ) -> RoutingResult:
        ...


class HttpTransport(Protocol):
    """Abstracción de transporte HTTP para inyección en tests."""

    def send(
        self,
        method: str,
        url: str,
        payload: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, object]:
        ...


class GatewayFactory(Protocol):
    def create(self, config: GatewayConfig) -> OrderRouter:
        ...
