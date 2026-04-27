#!/usr/bin/env python3
"""Authenticate against Afrihost ClientZone and verify credentials.

Copy .env.example to .env and fill in your credentials before running:
    cp .env.example .env
    python test_login.py

On the first run with 2FA enabled the script will prompt for the OTP.
The session is saved to .afrihost_session.json so subsequent runs skip
the full auth flow for as long as the server session remains valid.
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
from pyafrihostapi.client import AfrihostClient, LoginError

SESSION_FILE = Path(__file__).parent / ".afrihost_session.json"
_log = logging.getLogger(__name__)


def do_login(client: AfrihostClient) -> None:
    """Full credential + optional 2FA login, then persist the session."""
    twofa_code = os.environ.get("AFRIHOST_2FA_CODE")
    try:
        client.login()
    except LoginError as e:
        if not client._pending_2fa:
            _log.error("Login error: %s", e)
            sys.exit(1)

        print("2FA required — check your SMS/WhatsApp for the OTP.")
        raw = twofa_code or input("Enter OTP code: ")
        code = "".join(filter(str.isdigit, raw))
        try:
            client.submit_2fa(code)
        except LoginError as e2:
            _log.error("2FA error: %s", e2)
            sys.exit(1)

    client.save_session(SESSION_FILE)
    _log.info("Session saved to %s", SESSION_FILE)


def main():
    url      = os.environ["AFRIHOST_URL"]
    username = os.environ["AFRIHOST_USERNAME"]
    password = os.environ["AFRIHOST_PASSWORD"]

    client = AfrihostClient(username, password, base_url=url)

    # Try the saved session first; fall back to a full login if it has expired
    session_loaded = client.load_session(SESSION_FILE)
    if session_loaded and client.verify_session():
        _log.info("Resumed saved session")
    else:
        if session_loaded:
            _log.info("Saved session has expired — re-authenticating (2FA may be required again)")
        else:
            _log.info("No saved session found — authenticating")
        do_login(client)

    try:
        contact = client.account.raw()
        cc = contact.get("client_contact", {})
        print(f"Logged in as: {cc.get('first_name')} {cc.get('last_name')} ({cc.get('email')})")
        print(f"Account status: {cc.get('status')}")
    except Exception as e:
        _log.error("Failed to fetch client contact: %s", e)


if __name__ == "__main__":
    main()
