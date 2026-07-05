# order-routing-gateway

Network abstraction layer that translates **internal orders** from the system into exchange REST calls (Binance, Coinbase) or into a simulated **paper trading** environment. Eighth module of the [quant-core-infra](https://github.com/juanmmm21/quant-core-infra) ecosystem.

Repository: [github.com/juanmmm21/order-routing-gateway](https://github.com/juanmmm21/order-routing-gateway)

---

## What it is and what problem it solves

The trading core emits orders in a canonical format (`InternalOrder`), but each exchange requires different REST payloads: field names, symbol conventions, order types, and authentication headers.

Coupling strategy or backtest logic directly to an exchange's API makes it impossible to switch platforms without rewriting code. This module solves that problem with the **Gateway + Adapter** pattern: a single configuration line (`exchange`, `mode`) determines the destination without touching the core.

---

## Role in quant-core-infra

```text
alpha-signal-generator ──► signals ──► event-driven-backtester ──► internal orders
                                                                          │
                                                                          ▼
                                                               order-routing-gateway
                                                                          │
                                    ┌─────────────────────────────────────┴──────────────────────┐
                                    ▼                                                            ▼
                            paper mode (simulated)                                      live mode (REST API)
                                    │                                                            │
                                    ▼                                                            ▼
                         trade-audit-logger ◄────────────────────────────────────── exchange (Binance/Coinbase)
```

It's the **bridge between decision logic and real (or simulated) market execution**.

---

## Purpose

Demonstrates:

- Gateway pattern with destination selection via configuration
- Per-exchange adapters (Binance Spot, Coinbase Advanced Trade)
- Paper trading mode with fills at market price
- Live mode with injectable HTTP transport and explicit error handling
- Prices and commissions with `Decimal` precision
- JSONL pipelines compatible with orders and reference ticks

---

## How it works

1. **Configuration:** a `GatewayConfig` is defined with `exchange` (binance/coinbase) and `mode` (paper/live).
2. **Ingestion:** orders are loaded from JSONL as `InternalOrder`.
3. **Translation:** the exchange adapter converts the internal order into an `ExchangeOrderRequest`.
4. **Routing:**
   - **Paper:** instant fill at the price of the most recent tick before `submitted_at`.
   - **Live:** HTTP request to the exchange's REST endpoint; ack and fill parsing.
5. **Output:** `RoutingResult` with `OrderAcknowledgement` and an optional `RoutedFill`.

---

## Architecture

```text
InternalOrder
      │
      ▼
OrderRoutingGateway ──► PaperTradingRouter  (mode=paper)
      │              └── LiveOrderRouter      (mode=live)
      │
      ▼
ExchangeOrderAdapter (Binance / Coinbase)
      │
      ▼
ExchangeOrderRequest ──► HTTP POST ──► OrderAcknowledgement + RoutedFill
```

### Components

| Module | Responsibility |
|--------|----------------|
| `models.py` | Domain types: orders, acks, fills, config |
| `protocols.py` | `ExchangeOrderAdapter`, `OrderRouter`, `HttpTransport` interfaces |
| `adapters/binance.py` | Translation to POST `/api/v3/order` |
| `adapters/coinbase.py` | Translation to POST `/api/v3/brokerage/orders` |
| `paper_router.py` | Fill simulation at market price |
| `live_router.py` | REST submission with injectable transport |
| `gateway.py` | Router factory based on mode |
| `ingest.py` | JSONL parsing |
| `pipeline.py` | End-to-end run |

### Technical decisions

- **Decimal** for quantities, prices, and commissions
- **Injectable HTTP transport** (`MockHttpTransport` in tests, `UrllibHttpTransport` in production)
- **No runtime dependencies** — stdlib only for HTTP
- **Dry-run** via the `translate` subcommand, which shows the payload without sending it

---

## Configuration: `GatewayConfig`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `exchange` | — | `binance` or `coinbase` |
| `mode` | — | `paper` or `live` |
| `commission_rate` | `0.001` | Commission on executed notional (paper and fill parsing) |

---

## Requirements

- Python **3.11+**

---

## Installation

```bash
cd order-routing-gateway
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## CLI usage

### Route orders in paper mode

```bash
order-routing-gateway route \
  --orders samples/btcusdt_orders.jsonl \
  --ticks samples/btcusdt_ticks.jsonl \
  --symbol BTCUSDT \
  --exchange binance \
  --mode paper \
  --output routing_results.json
```

### Translate an order into the exchange's format (dry-run)

```bash
order-routing-gateway translate \
  --symbol BTCUSDT \
  --exchange binance \
  --order-json '{"client_order_id":"ord-1","side":"buy","order_type":"market","quantity":"0.01","submitted_at":"2024-01-01T12:00:00.000Z"}'
```

### Expected output (excerpt)

```json
{
  "acknowledgement": {
    "client_order_id": "ord-1",
    "exchange_order_id": "paper-a1b2c3d4e5f6",
    "exchange": "binance",
    "status": "filled",
    "submitted_at": "2024-01-01T12:00:00+00:00",
    "message": "paper fill at market price"
  },
  "fill": {
    "client_order_id": "ord-1",
    "side": "buy",
    "quantity": "0.01",
    "fill_price": "100.0",
    "commission": "0.001"
  }
}
```

---

## JSONL formats

### Internal order

```json
{
  "client_order_id": "ord-1",
  "symbol": "BTCUSDT",
  "side": "buy",
  "order_type": "market",
  "quantity": "0.01",
  "submitted_at": "2024-01-01T12:00:00.000Z",
  "signal_id": "sig-42"
}
```

Also accepts `order_id` as an alias for `client_order_id`, for compatibility with `event-driven-backtester` and `market-condition-simulator`.

### Reference tick (paper mode)

```json
{
  "symbol": "BTCUSDT",
  "price": "100.5",
  "event_time": "2024-01-01T12:00:00.100Z"
}
```

---

## Programmatic usage

```python
from datetime import UTC, datetime
from decimal import Decimal

from order_routing_gateway import (
    ExchangeId,
    GatewayConfig,
    InternalOrder,
    OrderRoutingGateway,
    OrderSide,
    OrderType,
    RoutingMode,
    run_routing_pipeline,
)

# Pipeline from files
results = run_routing_pipeline(
    orders_path="orders.jsonl",
    ticks_path="ticks.jsonl",
    symbol="BTCUSDT",
    config=GatewayConfig(
        exchange=ExchangeId.BINANCE,
        mode=RoutingMode.PAPER,
        commission_rate=Decimal("0.001"),
    ),
)

# Manual gateway
gateway = OrderRoutingGateway(
    GatewayConfig(exchange=ExchangeId.BINANCE, mode=RoutingMode.PAPER),
)
order = InternalOrder(
    client_order_id="ord-1",
    symbol="BTCUSDT",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=Decimal("0.01"),
    submitted_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
)
result = gateway.router.route_order(order)
```

---

## Development

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Roadmap

- [ ] HMAC signing for Binance and Coinbase authentication in live mode
- [ ] Limit order support with configurable time-in-force
- [ ] Cancellation and status query for pending orders
- [ ] Direct integration with `risk-management-engine` as a pre-trade gate

---

## Troubleshooting

| Symptom | Likely cause | Solution |
|---------|----------------|----------|
| `market price is required for paper routing` | No tick before `submitted_at` | Make sure `--ticks` covers the orders' time range |
| `orders file is empty` | JSONL with no valid lines | Check the format and required fields |
| `unsupported symbol for coinbase` | Symbol not mappable to `product_id` | Use the `BTCUSDT` or `BTC-USD` format |
| Order rejected in live mode | Invalid API key or missing HMAC signature | Use `--mode paper` for development; see the roadmap for full auth |

---

## License

MIT
