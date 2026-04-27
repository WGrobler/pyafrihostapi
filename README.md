# pyafrihostapi

Unofficial Python client for the [Afrihost ClientZone](https://clientzone.afrihost.com) portal.
Intended for use as a standalone library or as the backend for integrations such as Home Assistant.

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Authentication

Afrihost ClientZone supports password login and optional two-factor authentication (OTP via SMS/WhatsApp).

### Environment variables

Copy `examples/.env.example` to `examples/.env` and fill in your credentials:

```
AFRIHOST_URL=https://clientzone.afrihost.com
AFRIHOST_USERNAME=you@example.com
AFRIHOST_PASSWORD=your_password_here
# AFRIHOST_2FA_CODE=123456    # digits only, no quotes — only needed if 2FA is enabled
LOG_LEVEL=INFO
```

### Session persistence

After a successful login the session is saved to `.afrihost_session.json` so subsequent runs skip the full auth flow. The file is ignored by git.

---

## Quick start

```bash
python examples/test_login.py
```

On first run (or when the session expires) this will authenticate with your credentials.
If 2FA is enabled it will prompt for the OTP or read it from `AFRIHOST_2FA_CODE` in `.env`.

---

## API

```python
from pyafrihostapi.client import AfrihostClient

client = AfrihostClient("you@example.com", "password")
client.login()          # handles 2FA if required
```

### Namespaces

All product data is accessed through namespaces on the client instance.

| Namespace | Description |
|---|---|
| `client.account` | Account profile and contact details |
| `client.mobile` | Mobile SIM solutions and legacy APN data packages |
| `client.wireless` | Fixed wireless / LTE products |
| `client.voip` | Pure VoIP numbers |
| `client.devices` | Hardware devices (routers, SIM cards) |
| `client.hosting` | Hosting products |
| `client.connectivity` | Internal gateway — raw connectivity API response |

### Listing products

Every namespace exposes a `products()` method that returns the list for that category.

```python
client.mobile.products()      # {"mobile_solutions": [...], "apn_packages": [...]}
client.wireless.products()    # [...]
client.voip.products()        # [...]
client.devices.products()     # [...]
```

### Per-product detail

Pass an `id` to `products()` to get a product object, then call `.raw()` for the full API response.

```python
client.mobile.products("1000000000001").raw()
client.voip.products("1000001000001").raw()
client.devices.products("100001").raw()
client.wireless.products("200001").raw()
```

VoIP products also accept the VoIP number as the identifier:

```python
client.voip.products("0870000001").raw()
```

### Raw API responses

Each namespace also exposes `.raw()` directly to return the unmodified API response.

```python
client.account.raw()
client.mobile.raw()
client.voip.raw()
client.hosting.raw()
```

### Session management

```python
client.save_session(".afrihost_session.json")
client.load_session(".afrihost_session.json")
client.verify_session()   # returns True/False

# For external storage (e.g. Home Assistant)
cookies = client.get_cookies()
client.set_cookies(cookies)
```

---

## Examples

| Script | Purpose |
|---|---|
| `examples/test_login.py` | Authenticate and verify credentials |
| `examples/test_products.py` | List all products across every category |

---

## Home Assistant integration

A separate Home Assistant custom component (the **Afrihost** integration) is built on top of this library. See the `afrihost-clientzone-ha` folder in the repository root.

---

## Notes

- This is an **unofficial** client. Afrihost does not provide a public API — endpoints were discovered by inspecting browser traffic and may change without notice.
- 2FA OTP codes expire after 15 minutes and can be reused within the same session window.
- The `connectivity` namespace is the internal gateway for `wireless`, `devices`, and `mobile` APN data. Users do not need to call it directly.

## Contributing

**Do not include real product identifiers, phone numbers, account IDs, or any other personally identifiable data in code, documentation, or commit history.**
All example values in the README and source code must be clearly fictional placeholders (e.g. `1000000000001`, `0870000001`).
