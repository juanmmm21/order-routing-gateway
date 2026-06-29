from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from order_routing_gateway.models import (
    GatewayConfig,
    InternalOrder,
    OrderAcknowledgement,
    OrderStatus,
    PriceTick,
    RoutedFill,
    RoutingResult,
)

logger = logging.getLogger(__name__)


class PaperTradingRouter:
    """Simula ejecución instantánea al precio de mercado más reciente."""

    def __init__(self, config: GatewayConfig) -> None:
        self._config = config
        self._last_price: Decimal | None = None

    def update_market_price(self, tick: PriceTick) -> None:
        if tick.price <= Decimal("0"):
            raise ValueError("tick price must be positive")
        self._last_price = tick.price

    def route_order(
        self,
        order: InternalOrder,
        market_price: PriceTick | None = None,
    ) -> RoutingResult:
        reference = market_price or (
            PriceTick(
                symbol=order.symbol,
                price=self._last_price,
                event_time=order.submitted_at,
            )
            if self._last_price is not None
            else None
        )
        if reference is None or reference.price <= Decimal("0"):
            raise ValueError("market price is required for paper routing")

        fill_price = self._resolve_fill_price(order, reference.price)
        commission = fill_price * order.quantity * self._config.commission_rate
        exchange_order_id = f"paper-{uuid.uuid4().hex[:12]}"

        acknowledgement = OrderAcknowledgement(
            client_order_id=order.client_order_id,
            exchange_order_id=exchange_order_id,
            exchange=self._config.exchange,
            status=OrderStatus.FILLED,
            submitted_at=order.submitted_at,
            message="paper fill at market price",
        )
        fill = RoutedFill(
            client_order_id=order.client_order_id,
            exchange_order_id=exchange_order_id,
            exchange=self._config.exchange,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            fill_price=fill_price,
            commission=commission,
            filled_at=reference.event_time,
        )
        logger.info(
            "paper fill client_order_id=%s symbol=%s side=%s price=%s",
            order.client_order_id,
            order.symbol,
            order.side.value,
            fill_price,
        )
        return RoutingResult(acknowledgement=acknowledgement, fill=fill)

    def _resolve_fill_price(self, order: InternalOrder, market_price: Decimal) -> Decimal:
        from order_routing_gateway.models import OrderType

        if order.order_type is OrderType.LIMIT and order.limit_price is not None:
            if order.side.value == "buy" and order.limit_price < market_price:
                return order.limit_price
            if order.side.value == "sell" and order.limit_price > market_price:
                return order.limit_price
        return market_price
