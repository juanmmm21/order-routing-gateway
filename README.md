# order-routing-gateway

Capa de abstracción de red que traduce **órdenes internas** del sistema a llamadas REST de exchanges (Binance, Coinbase) o a un entorno de **paper trading** simulado. Octavo módulo del ecosistema [quant-core-infra](https://github.com/juanmmm21/quant-core-infra).

Repositorio: [github.com/juanmmm21/order-routing-gateway](https://github.com/juanmmm21/order-routing-gateway)

---

## Qué es y qué problema resuelve

El core de trading emite órdenes en un formato canónico (`InternalOrder`), pero cada exchange exige payloads REST distintos: nombres de campos, convenciones de símbolo, tipos de orden y cabeceras de autenticación.

Acoplar la lógica de estrategia o backtest directamente a la API de un exchange hace imposible cambiar de plataforma sin reescribir código. Este módulo resuelve ese problema con el patrón **Gateway + Adapter**: una sola línea de configuración (`exchange`, `mode`) determina el destino sin tocar el core.

---

## Rol en quant-core-infra

```text
alpha-signal-generator ──► señales ──► event-driven-backtester ──► órdenes internas
                                                                          │
                                                                          ▼
                                                               order-routing-gateway
                                                                          │
                                    ┌─────────────────────────────────────┴──────────────────────┐
                                    ▼                                                            ▼
                            modo paper (simulado)                                      modo live (REST API)
                                    │                                                            │
                                    ▼                                                            ▼
                         trade-audit-logger ◄────────────────────────────────────── exchange (Binance/Coinbase)
```

Es el **puente entre la lógica de decisión y la ejecución real** (o simulada) en el mercado.

---

## Objetivo

Demuestra:

- Patrón Gateway con selección de destino por configuración
- Adaptadores por exchange (Binance Spot, Coinbase Advanced Trade)
- Modo paper trading con fills al precio de mercado
- Modo live con transporte HTTP inyectable y manejo explícito de errores
- Precios y comisiones con precisión `Decimal`
- Pipelines JSONL compatibles con órdenes y ticks de referencia

---

## Cómo funciona

1. **Configuración:** se define `GatewayConfig` con `exchange` (binance/coinbase) y `mode` (paper/live).
2. **Ingesta:** las órdenes se cargan desde JSONL como `InternalOrder`.
3. **Traducción:** el adaptador del exchange convierte la orden interna a un `ExchangeOrderRequest`.
4. **Enrutamiento:**
   - **Paper:** fill instantáneo al precio del tick más reciente anterior a `submitted_at`.
   - **Live:** envío HTTP al endpoint REST del exchange; parseo de ack y fill.
5. **Salida:** `RoutingResult` con `OrderAcknowledgement` y `RoutedFill` opcional.

---

## Arquitectura

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

### Componentes

| Módulo | Responsabilidad |
|--------|----------------|
| `models.py` | Tipos de dominio: órdenes, acks, fills, config |
| `protocols.py` | Interfaces `ExchangeOrderAdapter`, `OrderRouter`, `HttpTransport` |
| `adapters/binance.py` | Traducción a POST `/api/v3/order` |
| `adapters/coinbase.py` | Traducción a POST `/api/v3/brokerage/orders` |
| `paper_router.py` | Simulación de fills al precio de mercado |
| `live_router.py` | Envío REST con transporte inyectable |
| `gateway.py` | Factory de router según modo |
| `ingest.py` | Parsing JSONL |
| `pipeline.py` | Run end-to-end |

### Decisiones técnicas

- **Decimal** en cantidades, precios y comisiones
- **Transporte HTTP inyectable** (`MockHttpTransport` en tests, `UrllibHttpTransport` en producción)
- **Sin dependencias runtime** — solo stdlib para HTTP
- **Dry-run** vía subcomando `translate` que muestra el payload sin enviar

---

## Configuración: `GatewayConfig`

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `exchange` | — | `binance` o `coinbase` |
| `mode` | — | `paper` o `live` |
| `commission_rate` | `0.001` | Comisión sobre notional ejecutado (paper y parseo de fills) |

---

## Requisitos

- Python **3.11+**

---

## Instalación

```bash
cd order-routing-gateway
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

---

## Uso CLI

### Enrutar órdenes en modo paper

```bash
order-routing-gateway route \
  --orders samples/btcusdt_orders.jsonl \
  --ticks samples/btcusdt_ticks.jsonl \
  --symbol BTCUSDT \
  --exchange binance \
  --mode paper \
  --output routing_results.json
```

### Traducir una orden al formato del exchange (dry-run)

```bash
order-routing-gateway translate \
  --symbol BTCUSDT \
  --exchange binance \
  --order-json '{"client_order_id":"ord-1","side":"buy","order_type":"market","quantity":"0.01","submitted_at":"2024-01-01T12:00:00.000Z"}'
```

### Salida esperada (extracto)

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

## Formatos JSONL

### Orden interna

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

También acepta `order_id` como alias de `client_order_id` para compatibilidad con `event-driven-backtester` y `market-condition-simulator`.

### Tick de referencia (paper mode)

```json
{
  "symbol": "BTCUSDT",
  "price": "100.5",
  "event_time": "2024-01-01T12:00:00.100Z"
}
```

---

## Uso programático

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

# Pipeline desde archivos
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

# Gateway manual
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

## Desarrollo

```bash
pytest -q
ruff check src tests
mypy src
```

---

## Roadmap

- [ ] Firma HMAC para autenticación Binance y Coinbase en modo live
- [ ] Soporte de órdenes limit con time-in-force configurables
- [ ] Cancelación y consulta de estado de órdenes pendientes
- [ ] Integración directa con `risk-management-engine` como pre-trade gate

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `market price is required for paper routing` | No hay tick anterior a `submitted_at` | Asegura que `--ticks` cubra el rango temporal de las órdenes |
| `orders file is empty` | JSONL sin líneas válidas | Verifica formato y campos obligatorios |
| `unsupported symbol for coinbase` | Símbolo no mapeable a `product_id` | Usa formato `BTCUSDT` o `BTC-USD` |
| Orden rechazada en modo live | API key inválida o sin firma HMAC | Usa `--mode paper` para desarrollo; ver roadmap para auth completa |

---

## Licencia

MIT
