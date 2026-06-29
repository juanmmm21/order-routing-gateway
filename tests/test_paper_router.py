from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from order_routing_gateway.models import (
    ExchangeId,
    GatewayConfig,
    InternalOrder,
    OrderSide,
    OrderType,
    PriceTick,
    RoutingMode,
)
from order_routing_gateway.paper_router import PaperTradingRouter


def test_paper_router_fills_at_market_price() -> None:
    config = GatewayConfig(exchange=ExchangeId.BINANCE, mode=RoutingMode.PAPER)
    router = PaperTradingRouter(config)
    tick = PriceTick(
        symbol="BTCUSDT",
        price=Decimal("100"),
        event_time=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )
    order = InternalOrder(
        client_order_id="ord-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.01"),
        submitted_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
    )
    result = router.route_order(order, tick)
    assert result.fill is not None
    assert result.fill.fill_price == Decimal("100")
    assert result.acknowledgement.status.value == "filled"
