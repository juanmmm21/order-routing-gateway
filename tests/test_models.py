from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from order_routing_gateway.models import (
    ExchangeId,
    GatewayConfig,
    InternalOrder,
    OrderSide,
    OrderType,
    RoutingMode,
)


def test_internal_order_requires_limit_price_for_limit_type() -> None:
    with pytest.raises(ValueError, match="limit_price is required"):
        InternalOrder(
            client_order_id="ord-1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.01"),
            submitted_at=datetime(2024, 1, 1, tzinfo=UTC),
        )


def test_gateway_config_rejects_negative_commission() -> None:
    with pytest.raises(ValueError, match="commission_rate"):
        GatewayConfig(
            exchange=ExchangeId.BINANCE,
            mode=RoutingMode.PAPER,
            commission_rate=Decimal("-0.001"),
        )
