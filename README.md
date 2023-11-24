# QuickBooks sandbox connector

A Django proof of concept that starts an Intuit accounting authorization flow and returns a small JSON snapshot of bills and vendors after the callback. Despite the repository name, it does **not** perform recurring synchronization, reconcile records, persist ledger entries or write accounting transactions.

The original project calls itself Routable. The implemented provider is QuickBooks; Xero credentials in the old example configuration did not correspond to an implemented Xero connector and have been removed.

## How the demo works

```mermaid
sequenceDiagram
    actor Staff
    participant Django
    participant Intuit
    Staff->>Django: Start connection while signed in as staff
    Django->>Django: Store random state with 10-minute expiry
    Django-->>Staff: Redirect to Intuit authorization
    Staff->>Intuit: Approve sandbox company
    Intuit-->>Django: Callback with state, code and realmId
    Django->>Django: Validate and consume state; check configured company
    Django->>Intuit: Exchange code and read bills/vendors
    Django-->>Staff: JSON snapshot, no-store response
```

The callback checks single-use browser state **before** creating a provider client or exchanging a code. Authorization codes are not stored in the Django session. An optional configured company ID restricts accepted callbacks; the validated callback realm is passed to QuickBooks.

The SDK's state parameter is documented in the [Intuit AuthClient reference](https://oauth-pythonclient.readthedocs.io/en/latest/reference/oauth-client.html). This demo does not implement a separate refresh-token storage and lifecycle service.

## Prepare a local sandbox

Use Python 3.11 in a virtual environment. Requirements retain the original Django 4.2.7 and SDK pins; the complete pinned environment was not installed during this review.

```sh
git clone https://github.com/dev-nezuko/accounting-sync-connector.git
cd accounting-sync-connector
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp example.env .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver localhost:8003
```

Create your own application and company in the [Intuit sandbox](https://developer.intuit.com/app/developer/sandbox), then fill the private `.env` values for client ID, client secret and redirect URI. Register exactly:

```text
http://localhost:8003/accounts/quickbooks/login/callback/
```

Keep the environment set to `sandbox`. Sign in at `/admin/` as staff before opening `/initiate_ledger_process/`. The example contains no usable credentials or company identifier. If an old client secret or Django signing key was ever used, rotate it at the provider/deployment too; removing Git values does not revoke them or clear external copies.

Local debug mode uses a process-local random signing key when none is configured. Set a private `DJANGO_SECRET_KEY` before disabling `DJANGO_DEBUG`. Production also needs deliberate host, HTTPS, session-cookie and deployment settings; the development configuration is not a hosted service plan.

## Returned data and boundaries

A successful callback returns four fields:

```json
{
  "single_bill": null,
  "all_bills": [],
  "single_vendor": null,
  "all_vendors": []
}
```

That is a synthetic response shape, not a captured accounting record. Individual reads default to the original example bill ID `1` and vendor ID `56`; those IDs may not exist in your sandbox. Select suitable IDs in `LedgerClient` for your fixture. Requested IDs now reach the SDK rather than being silently replaced by instance defaults. List reads return at most 50 items and do not page through a complete ledger.

Provider failures return a generic 502 instead of provider exception details. A company mismatch, expired state or replay returns 400. The JSON snapshot is staff-only and marked `Cache-Control: no-store`, but it can still contain financial data: use a sandbox and do not publish screenshots or saved responses with real records.

## Code and checks

| File | Responsibility |
| --- | --- |
| `api/views.py` | Staff access, OAuth state checks and callback response |
| `api/ledger.py` | Intuit authorization and QuickBooks read calls |
| `routeable_app/settings.py` | Django, private environment configuration and session setup |
| `api/tests.py` | Eight focused OAuth/access and SDK-argument regressions |

The unused alternative client-credentials implementation was removed; it was not used by the routed views. Credentials and tokens remain server-side during a request, but durable encrypted token storage, rotation, revocation, pagination, retries and idempotent synchronization are future work.

```sh
python manage.py test api --settings=api.test_settings
```

The isolated settings use in-memory SQLite and a separate test URL configuration; never deploy with them. Eight checks passed with Django 4.2 and provider test doubles that fail if called without a mock. No live Intuit authorization, token exchange, company read, SDK integration or full django-allauth runtime was verified. No UI screenshot is appropriate for this JSON-first prototype.

The repository has no license file; this README does not grant reuse rights.
