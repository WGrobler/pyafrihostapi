#!/usr/bin/env python3
"""Show airtime and SMS wallet balances for all mobile SIM products.

Handles both wallet endpoint types:
  - Regular/prepaid SIMs  → /en/api/voice/balances/wallet/{airtime_child_id}
  - AirMobile products    → /en/api/v1/client-solution-airmobile/{id}/balances/summary

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
from pyafrihostapi.client import AfrihostClient, _is_airmobile

SESSION_FILE = Path(__file__).parent / ".afrihost_session.json"
_log = logging.getLogger(__name__)


def fmt_timestamp(ts: int | None) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def print_voice_wallet(sim: dict, wallet: dict) -> None:
    """Print wallet entries from the /en/api/voice/balances/wallet response."""
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
        unit = wtype.get("display_unit") or wtype.get("unit") or {}
        symbol = unit.get("symbol", "")
        prefix = unit.get("prefix_symbol", False)

        display_value = balance * display_amount
        value_str = f"{symbol}{display_value:.2f}" if prefix else f"{display_value:.0f} {symbol}"

        expiry = entry.get("expiry_date")
        expiry_str = f"  (expires {fmt_timestamp(expiry)})" if expiry else ""
        print(f"    {label:<22}  {value_str}{expiry_str}")

    pending = wallet.get("asap_pending", {})
    p_air = pending.get("airtime", [])
    p_sms = pending.get("sms", [])
    if p_air or p_sms:
        print(f"    Pending transactions:  {len(p_air)} airtime, {len(p_sms)} SMS")


def print_airmobile_wallet(sim: dict, resp: dict) -> None:
    """Print airtime balance from /balances/summary (AirMobile products)."""
    for b in resp.get("balances", []):
        slug = b.get("slug", "")
        amount = b.get("amount", 0)
        label = b.get("display_name", slug)
        if slug == "airtime":
            print(f"    {label:<22}  R{amount / 100:.2f}")


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
        name = sim.get("friendlyname") or sim.get("uid") or str(sim.get("id"))
        status = sim.get("status", "")
        sol = sim.get("solution", {})
        wallet_type = "AirMobile" if _is_airmobile(sim) else "Voice"
        print(f"\n  [{sim['id']}] {name}  —  {status}  ({wallet_type} wallet)")
        try:
            resp = client.mobile.wallet_balances(sim)
            if _is_airmobile(sim):
                print_airmobile_wallet(sim, resp)
            else:
                wallet = resp.get("data", {}) if isinstance(resp, dict) else {}
                print_voice_wallet(sim, wallet)
        except Exception as exc:
            _log.warning("Could not fetch wallet for %s: %s", name, exc)

    print()


if __name__ == "__main__":
    main()
