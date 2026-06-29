from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from order_routing_gateway.models import (
    InternalOrder,
    OrderType,
    PriceTick,
    decimal_from_value,
    parse_order_side,
    parse_order_type,
    utc_from_iso8601,
)


def load_orders(path: str | Path, default_symbol: str) -> list[InternalOrder]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"orders file not found: {file_path}")

    orders: list[InternalOrder] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid json on line {line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            orders.append(parse_internal_order(payload, default_symbol))

    if not orders:
        raise ValueError("orders file is empty")
    return orders


def load_ticks(path: str | Path, default_symbol: str) -> list[PriceTick]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"ticks file not found: {file_path}")

    ticks: list[PriceTick] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid json on line {line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            ticks.append(parse_price_tick(payload, default_symbol))

    if not ticks:
        raise ValueError("ticks file is empty")
    return ticks


def parse_internal_order(payload: dict[str, Any], default_symbol: str) -> InternalOrder:
    order_id = payload.get("client_order_id") or payload.get("order_id")
    if not order_id:
        raise ValueError("missing client_order_id or order_id")

    required = ("side", "quantity", "submitted_at")
    for field in required:
        if field not in payload:
            raise ValueError(f"missing required field: {field}")

    symbol = str(payload.get("symbol", default_symbol))
    order_type_raw = str(payload.get("order_type", OrderType.MARKET.value))
    limit_price_raw = payload.get("limit_price")

    return InternalOrder(
        client_order_id=str(order_id),
        symbol=symbol,
        side=parse_order_side(str(payload["side"])),
        order_type=parse_order_type(order_type_raw),
        quantity=decimal_from_value(payload["quantity"], "quantity"),
        submitted_at=utc_from_iso8601(str(payload["submitted_at"])),
        signal_id=str(payload.get("signal_id", "")),
        limit_price=(
            decimal_from_value(limit_price_raw, "limit_price")
            if limit_price_raw is not None
            else None
        ),
    )


def parse_price_tick(payload: dict[str, Any], default_symbol: str) -> PriceTick:
    if "price" not in payload or "event_time" not in payload:
        raise ValueError("tick requires price and event_time")

    symbol = str(payload.get("symbol", default_symbol))
    return PriceTick(
        symbol=symbol,
        price=decimal_from_value(payload["price"], "price"),
        event_time=utc_from_iso8601(str(payload["event_time"])),
    )
