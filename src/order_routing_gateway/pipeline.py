from __future__ import annotations

from datetime import datetime
from typing import Any

from order_routing_gateway.gateway import OrderRoutingGateway
from order_routing_gateway.ingest import load_orders, load_ticks
from order_routing_gateway.models import (
    GatewayConfig,
    InternalOrder,
    PriceTick,
    RoutingResult,
)


def serialize_routing_result(result: RoutingResult) -> dict[str, Any]:
    ack = result.acknowledgement
    payload: dict[str, Any] = {
        "acknowledgement": {
            "client_order_id": ack.client_order_id,
            "exchange_order_id": ack.exchange_order_id,
            "exchange": ack.exchange.value,
            "status": ack.status.value,
            "submitted_at": ack.submitted_at.isoformat(),
            "message": ack.message,
        },
        "fill": None,
    }
    if result.fill is not None:
        fill = result.fill
        payload["fill"] = {
            "client_order_id": fill.client_order_id,
            "exchange_order_id": fill.exchange_order_id,
            "exchange": fill.exchange.value,
            "symbol": fill.symbol,
            "side": fill.side.value,
            "quantity": str(fill.quantity),
            "fill_price": str(fill.fill_price),
            "commission": str(fill.commission),
            "filled_at": fill.filled_at.isoformat(),
        }
    return payload


def run_routing_pipeline(
    orders_path: str,
    ticks_path: str,
    symbol: str,
    config: GatewayConfig,
) -> list[dict[str, Any]]:
    orders = load_orders(orders_path, default_symbol=symbol)
    ticks = load_ticks(ticks_path, default_symbol=symbol)
    gateway = OrderRoutingGateway(config)

    from order_routing_gateway.paper_router import PaperTradingRouter

    if isinstance(gateway.router, PaperTradingRouter):
        for tick in ticks:
            if tick.symbol == symbol:
                gateway.router.update_market_price(tick)

    results: list[dict[str, Any]] = []
    for order in orders:
        if order.symbol != symbol:
            continue
        market_tick = _tick_at_time(ticks, order.submitted_at, symbol)
        result = gateway.router.route_order(order, market_tick)
        results.append(serialize_routing_result(result))

    return results


def translate_order_pipeline(
    order: InternalOrder,
    config: GatewayConfig,
) -> dict[str, str]:
    from order_routing_gateway.live_router import LiveOrderRouter

    router = LiveOrderRouter(config=config)
    return router.translate_order(order)


def _tick_at_time(
    ticks: list[PriceTick],
    submitted_at: datetime,
    symbol: str,
) -> PriceTick | None:
    selected: PriceTick | None = None
    for tick in ticks:
        if tick.symbol != symbol:
            continue
        if tick.event_time <= submitted_at:
            selected = tick
        else:
            break
    return selected
