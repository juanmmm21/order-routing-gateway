from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from order_routing_gateway.models import ExchangeId, GatewayConfig, RoutingMode
from order_routing_gateway.pipeline import run_routing_pipeline


def test_pipeline_runs_sample_files() -> None:
    root = Path(__file__).resolve().parents[1]
    results = run_routing_pipeline(
        orders_path=str(root / "samples" / "btcusdt_orders.jsonl"),
        ticks_path=str(root / "samples" / "btcusdt_ticks.jsonl"),
        symbol="BTCUSDT",
        config=GatewayConfig(
            exchange=ExchangeId.BINANCE,
            mode=RoutingMode.PAPER,
            commission_rate=Decimal("0.001"),
        ),
    )
    assert len(results) == 2
    buy = results[0]
    sell = results[1]
    assert buy["acknowledgement"]["status"] == "filled"
    assert sell["acknowledgement"]["status"] == "filled"
    assert Decimal(buy["fill"]["fill_price"]) == Decimal("100.0")
    assert Decimal(sell["fill"]["fill_price"]) == Decimal("102.0")
