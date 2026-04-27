#!/usr/bin/env python3
"""List all products under each Afrihost category using a saved session.

Run test_login.py first to create the session file, then:
    python test_products.py
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
from pyafrihostapi.client import AfrihostClient

SESSION_FILE = Path(__file__).parent / ".afrihost_session.json"
_log = logging.getLogger(__name__)


def fmt_bytes(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def main():
    client = AfrihostClient("", "")
    if not (client.load_session(SESSION_FILE) and client.verify_session()):
        _log.error("No valid session — run test_login.py first")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # CONNECTIVITY                                                         #
    # ------------------------------------------------------------------ #
    section("CONNECTIVITY")
    conn = client.connectivity.raw()

    fibre = conn.get("fibre_products", [])
    if fibre:
        print(f"\nFibre  ({len(fibre)} products)")
        for p in fibre:
            print(f"  [{p['id']}] {p.get('display_name', p.get('name'))} — {p.get('status')}")
    else:
        print("\n  No fibre products on this account")

    # ------------------------------------------------------------------ #
    # WIRELESS                                                             #
    # ------------------------------------------------------------------ #
    section("WIRELESS")
    wireless = client.wireless.products()
    print(f"\n{len(wireless)} fixed wireless / LTE products")
    for p in wireless:
        limit = fmt_bytes(int(p.get("bandwidth_limit", 0)))
        used  = float(p.get("percentage_used", 0))
        print(f"  [{p['id']}] {p.get('display_name', p.get('name'))} — {p['status']}")
        print(f"           {used:.2f}% used of {limit}")

    # ------------------------------------------------------------------ #
    # MOBILE  (SIM solutions + APN packages)                              #
    # ------------------------------------------------------------------ #
    section("MOBILE")
    mobile = client.mobile.products()

    sims = mobile["mobile_solutions"]
    print(f"\nSIM Solutions  ({len(sims)} products)")
    for p in sims:
        sol       = p.get("solution", {})
        plan      = sol.get("display_name", sol.get("name", ""))
        price     = sol.get("price")
        price_str = f"R{price}/month" if price else "free"
        children  = p.get("child_client_solutions", [])
        print(f"\n  [{p['id']}] {p['friendlyname']}  ({p.get('uid')})  — {p['status']}")
        print(f"           Plan: {plan}  {price_str}")
        for child in children:
            cs         = child.get("solution", {})
            limit_bytes = int(cs.get("bandwidth_limit_bytes", 0))
            if limit_bytes:
                print(f"           Bucket: {cs.get('display_name', cs.get('name'))}  {fmt_bytes(limit_bytes)}")

    apn = mobile["apn_packages"]
    if apn:
        print(f"\nAPN / Mobile Data  ({len(apn)} packages)")
        for p in apn:
            limit = fmt_bytes(int(p.get("bandwidth_limit", 0)))
            used  = float(p.get("percentage_used", 0))
            print(f"  [{p['id']}] {p.get('display_name', p.get('name'))} — {p['status']}")
            print(f"           {used:.2f}% used of {limit}")

    # ------------------------------------------------------------------ #
    # PURE VOIP                                                            #
    # ------------------------------------------------------------------ #
    section("PURE VOIP")
    voip = client.voip.products()
    print(f"\n{len(voip)} VoIP products")
    for p in voip:
        sol       = p.get("solution", {})
        plan      = sol.get("display_name", sol.get("name", ""))
        price     = sol.get("price")
        price_str = f"R{price}/month" if price else "free"
        print(f"  [{p['id']}] {p['friendlyname']}  ({p['uid']})  — {p['status']}")
        print(f"           Plan: {plan}  {price_str}")

    # ------------------------------------------------------------------ #
    # DEVICES                                                              #
    # ------------------------------------------------------------------ #
    section("DEVICES")
    devices = client.devices.products()
    print(f"\n{len(devices)} devices")
    for p in devices:
        sub = p.get("sub_product_item", {})
        print(f"  [{p['id']}] {p.get('description', sub.get('name', ''))} — {p['friendly_status']}")

    # ------------------------------------------------------------------ #
    # HOSTING                                                              #
    # ------------------------------------------------------------------ #
    section("HOSTING")
    hosting = client.hosting.raw()
    products = hosting.get("hosting_products", [])
    if products:
        stats = hosting.get("usage_stats", {})
        print(f"\n{len(products)} hosting products")
        for p in products:
            print(f"  [{p.get('id')}] {p.get('name', p.get('display_name'))} — {p.get('status')}")
        print(f"\n  Disk usage: {stats.get('used_percent', 0)}% used")
    else:
        print("\n  No hosting products on this account")

    print()


if __name__ == "__main__":
    main()
