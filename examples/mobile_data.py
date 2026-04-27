#!/usr/bin/env python3
"""Show data (bandwidth) usage for all mobile SIM products.

Data sources by product type:
  - Regular/prepaid SIMs  → /en/api/voice/{id}/composite  (data.data.usage.*)
  - AirMobile products    → /en/api/v1/client-solution-airmobile/{id}/balances/summary
                            (balances[slug=data].amount in bytes)

Run test_login.py first to create the session file, then:
    python test_data.py
"""
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from pyafrihostapi.client import AfrihostClient, _is_airmobile

SESSION_FILE = Path(__file__).parent / ".afrihost_session.json"
_log = logging.getLogger(__name__)


def fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def print_voice_data(sim: dict, usage: dict) -> None:
    """Print bandwidth data from the composite endpoint (voice SIMs)."""
    limit     = usage.get("bandwidth_limit", 0)
    used      = usage.get("bandwidth_used", 0)
    available = usage.get("bandwidth_available", 0)
    pct       = usage.get("percentage_used", "0")

    print(f"    {'Limit':<22}  {fmt_bytes(limit)}")
    print(f"    {'Used':<22}  {fmt_bytes(used)}")
    print(f"    {'Remaining':<22}  {fmt_bytes(available)}")
    print(f"    {'Usage':<22}  {float(pct):.2f}%")


def print_airmobile_data(sim: dict, resp: dict) -> None:
    """Print data balance from /balances/summary (AirMobile products)."""
    for b in resp.get("balances", []):
        if b.get("slug") == "data":
            amount = b.get("amount", 0)
            label = b.get("display_name", "Data")
            print(f"    {label:<22}  {fmt_bytes(amount)}")
            return
    print("    No data balance found.")


def main() -> None:
    client = AfrihostClient("", "")
    if not (client.load_session(SESSION_FILE) and client.verify_session()):
        _log.error("No valid session — run test_login.py first")
        sys.exit(1)

    mobile = client.mobile.products()
    sims = mobile.get("mobile_solutions", [])

    if not sims:
        print("No mobile SIM products found on this account.")
        return

    print(f"\n{'=' * 60}")
    print(f"  MOBILE DATA USAGE  ({len(sims)} SIM product(s))")
    print("=" * 60)

    for sim in sims:
        name = sim.get("friendlyname") or sim.get("uid") or str(sim.get("id"))
        status = sim.get("status", "")
        wallet_type = "AirMobile" if _is_airmobile(sim) else "Voice"
        print(f"\n  [{sim['id']}] {name}  —  {status}  ({wallet_type})")
        try:
            if _is_airmobile(sim):
                resp = client.mobile.wallet_balances(sim)
                print_airmobile_data(sim, resp)
            else:
                comp = client.mobile.composite(str(sim["id"]))
                usage = comp.get("data", {}).get("data", {}).get("usage", {})
                if usage:
                    print_voice_data(sim, usage)
                else:
                    print("    No usage data available.")
        except Exception as exc:
            _log.warning("Could not fetch data for %s: %s", name, exc)

    print()


if __name__ == "__main__":
    main()
