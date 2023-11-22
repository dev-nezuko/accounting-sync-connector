from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from intuitlib.exceptions import AuthClientError
from quickbooks import QuickBooks
from quickbooks.exceptions import ObjectNotFoundException, QuickbooksException
from quickbooks.objects.bill import Bill
from quickbooks.objects.vendor import Vendor
from requests import RequestException

MAX_LIST_RESULTS = 50
# Intuit stopped serving minor versions below 75 on 2025-08-01.
QBO_MINOR_VERSION = 75

# Everything the provider SDKs raise for auth, API or transport failures.
PROVIDER_ERRORS = (AuthClientError, QuickbooksException, RequestException)


def quickbooks_settings():
    qbo = settings.QUICKBOOKS
    missing = [name for name in ("client_id", "secret_key", "redirect_uri") if not qbo.get(name)]
    if missing:
        raise ImproperlyConfigured("QuickBooks settings are incomplete: " + ", ".join(missing))
    if qbo.get("qbook_env") not in ("sandbox", "production"):
        raise ImproperlyConfigured("QBOOK_ENVIRONMENT must be 'sandbox' or 'production'.")
    return qbo


def bill_summary(bill):
    # VendorRef is optional on QuickBooks bills; a missing one must not fail the whole snapshot.
    vendor_ref = getattr(bill, "VendorRef", None)
    return {"id": bill.Id, "balance": bill.Balance, "vendor_name": getattr(vendor_ref, "name", None)}


def vendor_summary(vendor):
    return {"id": vendor.Id, "balance": vendor.Balance, "vendor_name": vendor.DisplayName}


def _list_limit(num):
    return min(MAX_LIST_RESULTS, max(1, int(num)))


class LedgerClient:
    """Reads bills and vendors from one QuickBooks company for the lifetime of a single request.

    Tokens live only on this object; nothing is persisted, so there is no refresh lifecycle to manage.
    """

    def __init__(self, bill_id=1, vendor_id=56):
        qbo = quickbooks_settings()
        self.auth_client = AuthClient(
            client_id=qbo["client_id"],
            client_secret=qbo["secret_key"],
            environment=qbo["qbook_env"],
            redirect_uri=qbo["redirect_uri"],
        )
        self.qb = None
        self.bill_id = bill_id
        self.vendor_id = vendor_id

    def authorization_url(self, state):
        return self.auth_client.get_authorization_url([Scopes.ACCOUNTING], state_token=state)

    def connect(self, auth_code, realm_id):
        self.auth_client.get_bearer_token(auth_code=auth_code, realm_id=realm_id)
        self.qb = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self.auth_client.refresh_token,
            company_id=realm_id,
            minorversion=QBO_MINOR_VERSION,
        )

    def bills(self, num=MAX_LIST_RESULTS):
        return [bill_summary(bill) for bill in Bill.all(qb=self.qb, max_results=_list_limit(num))]

    def vendors(self, num=MAX_LIST_RESULTS):
        return [vendor_summary(vendor) for vendor in Vendor.all(qb=self.qb, max_results=_list_limit(num))]

    def bill(self, bill_id):
        try:
            return bill_summary(Bill.get(bill_id, qb=self.qb))
        except ObjectNotFoundException:
            return None

    def vendor(self, vendor_id):
        try:
            return vendor_summary(Vendor.get(vendor_id, qb=self.qb))
        except ObjectNotFoundException:
            return None

    def snapshot(self):
        return {
            "single_bill": self.bill(self.bill_id),
            "all_bills": self.bills(),
            "single_vendor": self.vendor(self.vendor_id),
            "all_vendors": self.vendors(),
        }
