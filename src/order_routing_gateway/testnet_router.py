"""Route orders to the Binance Spot **testnet** (paper trading with exchange-side matching)."""

from __future__ import annotations

import logging

from order_routing_gateway.adapters.binance import BinanceOrderAdapter
from order_routing_gateway.binance_client import BinanceApiError, BinanceSpotClient
from order_routing_gateway.models import (
    ExchangeId,
    GatewayConfig,
    InternalOrder,
    OrderAcknowledgement,
    OrderStatus,
    OrderType,
    PriceTick,
    RoutingResult,
)

logger = logging.getLogger(__name__)


class TestnetOrderRouter:
    """Signed testnet orders. ``ExchangeUnavailableError`` is propagated untouched: the order
    may or may not exist, and only ``client.query_order`` can tell."""

    __test__ = False  # not a pytest test class despite the name

    def __init__(self, config: GatewayConfig, client: BinanceSpotClient) -> None:
        if config.exchange is not ExchangeId.BINANCE:
            raise ValueError("testnet routing is only implemented for Binance")
        self._config = config
        self._client = client
        self._adapter = BinanceOrderAdapter()

    def route_order(
        self, order: InternalOrder, market_price: PriceTick | None = None
    ) -> RoutingResult:
        _ = market_price
        try:
            body = self._client.new_order(
                symbol=order.symbol,
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                client_order_id=order.client_order_id,
                price=order.limit_price if order.order_type is OrderType.LIMIT else None,
            )
        except BinanceApiError as exc:
            logger.warning("testnet rejected %s: %s", order.client_order_id, exc)
            return RoutingResult(
                acknowledgement=OrderAcknowledgement(
                    client_order_id=order.client_order_id,
                    exchange_order_id=f"rejected-{order.client_order_id}",
                    exchange=ExchangeId.BINANCE,
                    status=OrderStatus.REJECTED,
                    submitted_at=order.submitted_at,
                    message=f"{exc.code}: {exc.message}",
                ),
                fill=None,
            )
        ack = self._adapter.parse_acknowledgement(order, body)
        fill = None
        if ack.status is OrderStatus.FILLED:
            fill = self._adapter.parse_fill(order, body, self._config.commission_rate)
        logger.info("testnet route %s status=%s", order.client_order_id, ack.status.value)
        return RoutingResult(acknowledgement=ack, fill=fill)
