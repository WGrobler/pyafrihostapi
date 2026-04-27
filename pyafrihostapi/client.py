import json
import logging
from pathlib import Path
from typing import Optional, Union

import requests
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


class LoginError(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _airtime_wallet_id(sim: dict) -> Optional[str]:
    """Return the airtime child product id (solution_type_id=900) from a SIM dict.

    Works with dicts from the /en/api/voice list endpoint, which carry a
    ``child_client_solutions`` list.  Returns None if no airtime child exists.
    """
    for child in sim.get("child_client_solutions", []):
        sol = child.get("solution") or {}
        if sol.get("solution_type_id") == 900:
            return str(child["id"])
    return None


# ---------------------------------------------------------------------------
# Per-product resource objects (returned by namespace.products(id))
# ---------------------------------------------------------------------------

class MobileProduct:
    """Single mobile product. Returned by ``client.mobile.products(id)``."""

    def __init__(self, client, product_id: str) -> None:
        self._client = client
        self.id = product_id

    def raw(self) -> dict:
        """Full raw detail for this product.

        SIM-based products use /en/api/voice/{id}.
        Legacy APN packages fall back to the connectivity response.
        """
        _LOGGER.info("Fetching mobile product %s (raw)", self.id)
        try:
            return self._client._get(f"/en/api/voice/{self.id}")
        except Exception:
            pass
        conn = self._client._get("/en/api/connectivity")
        for item in conn.get("data_products", []):
            if str(item.get("id")) == self.id:
                _LOGGER.debug("Found product %s in APN data_products", self.id)
                return item
        raise KeyError(f"Mobile product '{self.id}' not found")

    def wallet(self) -> dict:
        """Airtime and SMS wallet balances for this SIM.

        Fetches the detail page for this SIM first to locate the airtime child
        product (the ``airtime`` key in the response), then calls
        /en/api/voice/balances/wallet/{airtime_child_id}.

        Key wallets in the response: summary_airtime, summary_sms, evergreen,
        sms, expiry.  Balance values are in raw units (cents for airtime);
        multiply by airtime_wallet_type.display_amount to get the display value.
        """
        _LOGGER.info("Fetching wallet balances for mobile SIM %s", self.id)
        detail = self._client._get(f"/en/api/voice/{self.id}")
        airtime_child = detail.get("data", {}).get("airtime", {})
        wallet_id = airtime_child.get("id")
        if not wallet_id:
            raise KeyError(f"No airtime child found for SIM '{self.id}'")
        _LOGGER.debug("Airtime child id=%s for SIM %s", wallet_id, self.id)
        return self._client._get(f"/en/api/voice/balances/wallet/{wallet_id}")


class VoipProduct:
    """Single VoIP product. Returned by ``client.voip.products(id)``."""

    def __init__(self, client, product_id: str) -> None:
        self._client = client
        self.id = product_id

    def raw(self) -> dict:
        """Full raw detail for this VoIP product (looked up from the solutions list)."""
        _LOGGER.info("Fetching VoIP product %s (raw)", self.id)
        resp = self._client._get(
            "/en/api/v1/client-solutions?with[]=solution&solution_types[]=voip"
        )
        for item in resp.get("client_solutions", []):
            if str(item.get("id")) == self.id or str(item.get("uid")) == self.id:
                return item
        raise KeyError(f"VoIP product '{self.id}' not found")


class DeviceProduct:
    """Single hardware device. Returned by ``client.devices.products(id)``."""

    def __init__(self, client, product_id: str) -> None:
        self._client = client
        self.id = product_id

    def raw(self) -> dict:
        """Full raw detail for this device (looked up from the connectivity response)."""
        _LOGGER.info("Fetching device %s (raw)", self.id)
        for item in self._client.connectivity.raw().get("device_products", []):
            if str(item.get("id")) == self.id:
                return item
        raise KeyError(f"Device '{self.id}' not found")


class WirelessProduct:
    """Single fixed wireless / LTE product. Returned by ``client.wireless.products(id)``."""

    def __init__(self, client, product_id: str) -> None:
        self._client = client
        self.id = product_id

    def raw(self) -> dict:
        """Full raw detail for this wireless product (looked up from the connectivity response)."""
        _LOGGER.info("Fetching wireless product %s (raw)", self.id)
        for item in self._client.connectivity.raw().get("fixed_wireless_products", []):
            if str(item.get("id")) == self.id:
                return item
        raise KeyError(f"Wireless product '{self.id}' not found")


# ---------------------------------------------------------------------------
# Namespace resource classes (attached as attributes on AfrihostClient)
# ---------------------------------------------------------------------------

class AccountResource:
    """Account profile and contact details. Accessed via ``client.account``."""

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Raw account profile from /en/api/v1/client-contact.

        Keys: client_contact (id, first_name, last_name, company_name,
        cell_number, tel_number, email, status, created_at, username, …)
        """
        _LOGGER.info("Fetching account (raw)")
        return self._client._get("/en/api/v1/client-contact")


class ConnectivityResource:
    """Connectivity products. Accessed via ``client.connectivity``."""

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Raw connectivity response from /en/api/connectivity.

        Keys: data_products, lines, device_products, fibre_products,
        voice_products, fixed_wireless_products, composite_dsl,
        pending_data_orders.
        """
        _LOGGER.info("Fetching connectivity (raw)")
        return self._client._get("/en/api/connectivity")


class MobileResource:
    """Mobile products (SIM solutions + legacy APN packages).
    Accessed via ``client.mobile``.
    """

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Raw mobile response from /en/api/voice.

        Key: data — list of mobile solutions each with id, uid (msisdn),
        friendlyname, status, solution (plan/price), child_client_solutions
        (data buckets), mobile_subscriber_detail.
        """
        _LOGGER.info("Fetching mobile (raw)")
        return self._client._get("/en/api/voice")

    def products(self, product_id: str = None):
        """List all mobile products, or return a single product by id.

        ``client.mobile.products()``
            Returns ``{"mobile_solutions": [...], "apn_packages": [...]}``
            combining SIM-based voice products and legacy APN data packages.

        ``client.mobile.products("1000000000001")``
            Returns a :class:`MobileProduct` instance for the given id.
            Call ``.raw()`` on it to fetch the full detail.
        """
        if product_id is not None:
            return MobileProduct(self._client, str(product_id))
        _LOGGER.info("Fetching mobile products (combined)")
        voice = self._client._get("/en/api/voice").get("data", [])
        apn   = self._client.connectivity.raw().get("data_products", [])
        return {"mobile_solutions": voice, "apn_packages": apn}

    def wallet_balances(self, sim: dict) -> dict:
        """Airtime and SMS wallet balances for a SIM product.

        Pass the full SIM product dict (as returned by ``mobile.products()``
        or ``mobile.raw()``).  The airtime child product (solution_type_id=900)
        is located from ``child_client_solutions`` and its id is used to call
        /en/api/voice/balances/wallet/{airtime_child_id}.
        """
        wallet_id = _airtime_wallet_id(sim)
        if not wallet_id:
            raise KeyError(
                f"No airtime child (solution_type_id=900) found for SIM '{sim.get('id')}'"
            )
        _LOGGER.info("Fetching wallet balances via airtime child id=%s", wallet_id)
        return self._client._get(f"/en/api/voice/balances/wallet/{wallet_id}")


class VoipResource:
    """Pure VoIP products. Accessed via ``client.voip``."""

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Raw VoIP solutions response from the API.

        Keys: client_solutions (list), pagination.
        Each solution: id, uid (VoIP number), friendlyname, status,
        solution (plan/price), mobile_subscriber_detail.
        """
        _LOGGER.info("Fetching VoIP (raw)")
        return self._client._get(
            "/en/api/v1/client-solutions?with[]=solution&solution_types[]=voip"
        )

    def products(self, product_id: str = None):
        """List all VoIP products, or return a single product by id or number.

        ``client.voip.products()``
            Returns the ``client_solutions`` list.

        ``client.voip.products("1000001000001")`` or
        ``client.voip.products("0870000001")``
            Returns a :class:`VoipProduct` instance (accepts id or uid/number).
            Call ``.raw()`` on it to fetch the full detail.
        """
        if product_id is not None:
            return VoipProduct(self._client, str(product_id))
        _LOGGER.info("Fetching VoIP products")
        return self.raw().get("client_solutions", [])


class DevicesResource:
    """Hardware devices on the account. Accessed via ``client.devices``."""

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Device list extracted from the connectivity API response.

        Returns ``{"device_products": [...]}`` where each item has id,
        friendly_status, description, sub_product_item (name/price),
        stock_item (serial_number), client_order (delivery details).
        """
        _LOGGER.info("Fetching devices (raw)")
        return {"device_products": self._client.connectivity.raw().get("device_products", [])}

    def products(self, product_id: str = None):
        """List all devices, or return a single device by id.

        ``client.devices.products()``
            Returns the list of device dicts.

        ``client.devices.products("100001")``
            Returns a :class:`DeviceProduct` instance for the given id.
            Call ``.raw()`` on it to fetch the full detail.
        """
        if product_id is not None:
            return DeviceProduct(self._client, str(product_id))
        _LOGGER.info("Fetching devices")
        return self.raw()["device_products"]


class WirelessResource:
    """Fixed wireless / LTE products. Accessed via ``client.wireless``."""

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Fixed wireless products extracted from the connectivity API response.

        Returns ``{"fixed_wireless_products": [...]}`` where each item has id,
        name, display_name, status, bandwidth_limit, percentage_used,
        percentage_left, vendor_id.
        """
        _LOGGER.info("Fetching wireless (raw)")
        return {"fixed_wireless_products": self._client.connectivity.raw().get("fixed_wireless_products", [])}

    def products(self, product_id: str = None):
        """List all fixed wireless products, or return a single product by id.

        ``client.wireless.products()``
            Returns the list of fixed wireless product dicts.

        ``client.wireless.products("200001")``
            Returns a :class:`WirelessProduct` instance for the given id.
            Call ``.raw()`` on it to fetch the full detail.
        """
        if product_id is not None:
            return WirelessProduct(self._client, str(product_id))
        _LOGGER.info("Fetching wireless products")
        return self.raw()["fixed_wireless_products"]


class HostingResource:
    """Hosting products. Accessed via ``client.hosting``."""

    def __init__(self, client) -> None:
        self._client = client

    def raw(self) -> dict:
        """Raw hosting response from /en/api/my-hosting.

        Keys: hosting_products (list), usage_stats (used_percent,
        remaining_byte, percent_available), isBillingRun, isReseller,
        wordingNext.
        """
        _LOGGER.info("Fetching hosting (raw)")
        return self._client._get("/en/api/my-hosting")


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------

class AfrihostClient:

    def __init__(self, username: str, password: str, base_url: str = "https://clientzone.afrihost.com"):
        self.username = username
        self.password = password
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        })
        self._logged_in = False
        self._pending_2fa = False
        self._2fa_form: Optional[dict] = None
        self._last_response_url: Optional[str] = None

        # Namespace resources
        self.account      = AccountResource(self)
        self.connectivity = ConnectivityResource(self)
        self.mobile       = MobileResource(self)
        self.wireless     = WirelessResource(self)
        self.voip         = VoipResource(self)
        self.devices      = DevicesResource(self)
        self.hosting      = HostingResource(self)

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _get_login_page(self) -> str:
        url = f"{self.base_url}/en/login"
        _LOGGER.debug("GET %s", url)
        resp = self.session.get(url, timeout=15)
        _LOGGER.debug("Response: status=%d  url=%s", resp.status_code, resp.url)
        resp.raise_for_status()
        self._last_response_url = resp.url
        return resp.text

    def _extract_csrf(self, html: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        el = soup.find("input", attrs={"name": "_csrf_token"})
        if el and el.get("value"):
            token = el["value"]
            _LOGGER.debug("CSRF token found: %s…", token[:10])
            return token
        _LOGGER.warning("No CSRF token found in login page")
        return None

    def login(self) -> bool:
        """Attempt login. Raises LoginError with _pending_2fa=True when OTP is required."""
        _LOGGER.info("Attempting login for %s", self.username)
        html = self._get_login_page()
        token = self._extract_csrf(html)

        data = {"_username": self.username, "_password": self.password}
        if token:
            data["_csrf_token"] = token

        login_url = f"{self.base_url}/en/login_check"
        _LOGGER.debug("POST %s  fields=%s", login_url, list(data.keys()))
        resp = self.session.post(login_url, data=data, allow_redirects=True, timeout=15)
        self._last_response_url = resp.url
        _LOGGER.debug("Response: status=%d  url=%s", resp.status_code, resp.url)
        _LOGGER.debug("Response body (first 500 chars): %s", resp.text[:500])

        if resp.url and resp.url.rstrip("/").endswith("/en/login"):
            _LOGGER.error("Login failed — invalid username or password (redirected to login page)")
            raise LoginError("Login failed — invalid username or password")

        if resp.status_code == 511:
            _LOGGER.info("2FA required — OTP dispatched to registered contact")
            self._prepare_2fa(resp.text)
            raise LoginError("2FA required — call submit_2fa(code) after receiving code")

        body = resp.text.lower()
        if "otp" in body or "two-factor" in body or "verification code" in body:
            _LOGGER.info("2FA required — OTP dispatched to registered contact")
            self._prepare_2fa(resp.text)
            raise LoginError("2FA required — call submit_2fa(code) after receiving code")

        if resp.status_code == 200 and resp.url and "/en/login" not in resp.url:
            self._logged_in = True
            _LOGGER.info("Login successful — landed on %s", resp.url)
            return True

        _LOGGER.error("Login failed: status=%d  url=%s", resp.status_code, resp.url)
        raise LoginError("Login failed — check credentials or inspect response")

    def _prepare_2fa(self, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        # login.js intercepts the form and POSTs via AJAX to /en/security/otp/verify.
        # On success the JS navigates to requestURI to complete the session.
        verify_url = f"{self.base_url}/en/security/otp/verify"

        for form in soup.find_all("form"):
            inputs = form.find_all("input")
            code_field = None
            hidden = {}
            request_uri = f"{self.base_url}/en/"
            for inp in inputs:
                name = inp.get("name") or ""
                input_type = (inp.get("type") or "").lower()
                if input_type == "hidden":
                    hidden[name] = inp.get("value", "")
                if inp.get("id") == "requestURI" and inp.get("value"):
                    request_uri = inp["value"]
                lname = name.lower()
                if lname in ("otp", "code", "verification_code", "verify_code"):
                    code_field = name
                if not code_field and input_type in ("text", "tel", "number") and ("otp" in lname or "code" in lname):
                    code_field = name

            if code_field:
                self._pending_2fa = True
                self._2fa_form = {
                    "action": verify_url,
                    "method": "post",
                    "hidden": hidden,
                    "code_field": code_field,
                    "request_uri": request_uri,
                }
                _LOGGER.debug(
                    "2FA form parsed: verify_url=%s  code_field=%s  request_uri=%s  hidden_keys=%s",
                    verify_url, code_field, request_uri, list(hidden.keys()),
                )
                return

        _LOGGER.warning("No 2FA form matched — using fallback (field=otp, url=%s)", verify_url)
        self._pending_2fa = True
        self._2fa_form = {
            "action": verify_url,
            "method": "post",
            "hidden": {},
            "code_field": "otp",
            "request_uri": f"{self.base_url}/en/",
        }

    def submit_2fa(self, code: str) -> bool:
        """Submit the OTP received via SMS/WhatsApp."""
        if not self._pending_2fa or not self._2fa_form:
            raise LoginError("No pending 2FA flow to submit to")

        code = "".join(filter(str.isdigit, str(code)))
        if not code:
            raise LoginError("Invalid OTP — must contain digits")

        form = self._2fa_form
        data = dict(form.get("hidden", {}))
        data[form.get("code_field")] = code

        submit_url = form.get("action")
        request_uri = form.get("request_uri", f"{self.base_url}/en/")

        _LOGGER.info("Submitting 2FA OTP to %s", submit_url)
        _LOGGER.debug("2FA payload keys: %s", list(data.keys()))

        headers = {
            "Referer": self._last_response_url or self.base_url,
            "Origin": self.base_url,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        }

        resp = self.session.post(submit_url, data=data, headers=headers,
                                 allow_redirects=True, timeout=15)

        self._last_response_url = resp.url
        _LOGGER.debug("2FA verify response: status=%d  url=%s", resp.status_code, resp.url)
        _LOGGER.debug("2FA verify body (first 500 chars): %s", resp.text[:500])

        if resp.status_code != 200:
            body = resp.text.lower()
            if "invalid" in body or "incorrect" in body:
                _LOGGER.error("2FA rejected: invalid code")
                raise LoginError("Invalid 2FA code")
            _LOGGER.error("2FA verify failed: status=%d  url=%s", resp.status_code, resp.url)
            raise LoginError("2FA submission failed — code may be incorrect or expired")

        # Verify succeeded — follow JS navigation to requestURI to establish session
        _LOGGER.debug("2FA verify accepted — navigating to %s", request_uri)
        nav = self.session.get(request_uri, allow_redirects=True, timeout=15)
        self._last_response_url = nav.url
        _LOGGER.debug("Post-2FA navigation: status=%d  url=%s", nav.status_code, nav.url)

        if nav.status_code == 200 and "/en/login" not in nav.url:
            self._logged_in = True
            self._pending_2fa = False
            self._2fa_form = None
            _LOGGER.info("2FA accepted — logged in successfully, landed on %s", nav.url)
            return True

        _LOGGER.error("2FA navigation failed: status=%d  url=%s", nav.status_code, nav.url)
        raise LoginError("2FA submission failed — inspect response")

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict:
        """Authenticated GET to a JSON API path. Raises LoginError if not logged in."""
        if not self._logged_in:
            raise LoginError("Not logged in")
        url = f"{self.base_url}{path}"
        _LOGGER.debug("GET %s", url)
        resp = self.session.get(url, timeout=15)
        _LOGGER.debug("Response: status=%d  url=%s", resp.status_code, resp.url)
        resp.raise_for_status()
        data = resp.json()
        _LOGGER.debug("Response data: %s", data)
        return data

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def get_cookies(self) -> dict:
        """Return current session cookies as a plain dict (for external storage)."""
        return dict(self.session.cookies)

    def set_cookies(self, cookies: dict) -> None:
        """Inject previously saved cookies and optimistically mark as logged in.
        Call verify_session() afterwards to confirm the session is still valid."""
        self.session.cookies.update(cookies)
        self._logged_in = True
        _LOGGER.debug("Session cookies injected: %s", list(cookies.keys()))

    def verify_session(self) -> bool:
        """Probe the API to confirm the current session is still authenticated.
        Resets _logged_in to False on failure so login() can be retried."""
        try:
            self._get("/en/api/v1/client-contact")
            _LOGGER.debug("Session verified — still authenticated")
            return True
        except Exception as exc:
            _LOGGER.debug("Session verify failed: %s", exc)
            self._logged_in = False
            return False

    def save_session(self, path: Union[str, Path]) -> None:
        """Persist session cookies to a JSON file."""
        with open(path, "w") as fh:
            json.dump(self.get_cookies(), fh)
        _LOGGER.debug("Session saved to %s", path)

    def load_session(self, path: Union[str, Path]) -> bool:
        """Load cookies from a JSON file. Returns True if the file was found and loaded.
        Does NOT verify the session — call verify_session() to confirm it is still valid."""
        try:
            with open(path) as fh:
                self.set_cookies(json.load(fh))
            _LOGGER.debug("Session loaded from %s", path)
            return True
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            _LOGGER.debug("Could not load session from %s: %s", path, exc)
            return False
