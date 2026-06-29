from __future__ import annotations

import argparse
import json
import logging
from decimal import Decimal

from order_routing_gateway.ingest import parse_internal_order
from order_routing_gateway.models import GatewayConfig, parse_exchange_id, parse_routing_mode
from order_routing_gateway.pipeline import run_routing_pipeline, translate_order_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gateway de enrutamiento de órdenes hacia exchanges o paper trading.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    route = subparsers.add_parser("route", help="Enruta órdenes JSONL usando ticks de referencia.")
    route.add_argument("--orders", required=True)
    route.add_argument("--ticks", required=True)
    route.add_argument("--symbol", required=True)
    route.add_argument("--exchange", default="binance", choices=["binance", "coinbase"])
    route.add_argument("--mode", default="paper", choices=["paper", "live"])
    route.add_argument("--commission-rate", default="0.001")
    route.add_argument("--output", default=None)

    translate = subparsers.add_parser(
        "translate",
        help="Muestra la traducción de una orden interna al formato del exchange.",
    )
    translate.add_argument("--order-json", required=True)
    translate.add_argument("--symbol", required=True)
    translate.add_argument("--exchange", default="binance", choices=["binance", "coinbase"])

    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if args.command == "route":
        config = GatewayConfig(
            exchange=parse_exchange_id(args.exchange),
            mode=parse_routing_mode(args.mode),
            commission_rate=Decimal(args.commission_rate),
        )
        results = run_routing_pipeline(
            orders_path=args.orders,
            ticks_path=args.ticks,
            symbol=args.symbol,
            config=config,
        )
        rendered = json.dumps(results, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
                handle.write("\n")
            logging.getLogger(__name__).info(
                "wrote %s routing results to %s",
                len(results),
                args.output,
            )
            return
        print(rendered)
        return

    if args.command == "translate":
        payload = json.loads(args.order_json)
        if not isinstance(payload, dict):
            raise ValueError("order-json must be a JSON object")
        order = parse_internal_order(payload, default_symbol=args.symbol)
        config = GatewayConfig(
            exchange=parse_exchange_id(args.exchange),
            mode=parse_routing_mode("live"),
        )
        translated = translate_order_pipeline(order, config)
        print(json.dumps(translated, indent=2))
        return

    raise RuntimeError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    main()
