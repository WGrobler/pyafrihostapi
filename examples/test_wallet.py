#!/usr/bin/env python3
"""Show airtime and SMS wallet balances for all mobile SIM products.

Run test_login.py first to create the session file, then:
    python test_wallet.py
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from pyafrihostapi.client import AfrihostClient

SESSION_FILE = Path(__file__).parent / ".afrihost_session.json"
_log = logging.getLogger(__name__)


def fmt_rands(balance: int, display_amount: float) -> str:
    return f"R{balance * display_amount:.2f}"


def fmt_timestamp(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def print_wallet(sim: dict, wallet: dict) -> None:
    name = sim.get("friendlyname") or sim.get("uid") or str(sim.get("id"))
    status = sim.get("status", "")
    print(f"\n  [{sim['id']}] {name}  —  {status}")

    for slug, label in (
        ("summary_airtime", "Airtime (total)"),
        ("evergreen",       "Airtime (evergreen)"),
        ("expiry",          "Airtime (expiring)"),
        ("summary_sms",     "SMS (total)"),
        ("sms",             "SMS (with expiry)"),
    ):
        entry = wallet.get(slug)
        if entry is None:
            continue

        balance = entry.get("balance", 0)
        wtype = entry.get("airtime_wallet_type", {})
        display_amount = wtype.get("display_amount", 1)
        display_symbol = (wtype.get("display_unit") or wtype.get("unit") or {}).get("symbol", "")
        prefix = (wtype.get("display_unit") or {}).get("prefix_symbol", False)

        display_value = balance * display_amount
        if prefix:
            value_str = f"{display_symbol}{display_value:.2f}"
        else:
            value_str = f"{display_value:.0f} {display_symbol}"

        expiry = entry.get("expiry_date")
        expiry_str = f"  (expires {fmt_timestamp(expiry)})" if expiry else ""

        print(f"    {label:<22}  {value_str}{expiry_str}")

    pending = wallet.get("asap_pending", {})
    pending_airtime = pending.get("airtime", [])
    pending_sms = pending.get("sms", [])
    if pending_airtime or pending_sms:
        print(f"    Pending transactions:  {len(pending_airtime)} airtime, {len(pending_sms)} SMS")


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
    print(f"  MOBILE WALLET BALANCES  ({len(sims)} SIM product(s))")
    print("=" * 60)

    for sim in sims:
        try:
            resp = client.mobile.wallet_balances(sim)
            wallet = resp.get("data", {})
            print_wallet(sim, wallet)
        except Exception as exc:
            name = sim.get("friendlyname") or str(sim.get("id"))
            _log.warning("Could not fetch wallet for %s: %s", name, exc)

    print()


if __name__ == "__main__":
    main()
