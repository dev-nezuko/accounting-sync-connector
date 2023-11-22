from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.bill import Bill
from quickbooks.objects.vendor import Vendor
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class LedgerClientBase:
    """Base Ledger Integration Client class"""

    def __init__(self):
        self._connection = self._get_connection()

    def _get_connection(self):
        raise NotImplementedError("`_get_connection()` must be implemented.")

    def get_bills(self, num=50, vendor_id=None):
        raise NotImplementedError("`get_bills()` must be implemented.")

    def get_bill(self, bill_id):
        raise NotImplementedError("`get_bill()` must be implemented.")

    def get_vendors(self, num=50):
        raise NotImplementedError("`get_vendors()` must be implemented.")

    def get_vendor(self, vendor_id):
        raise NotImplementedError("`get_vendor()` must be implemented.")


class LedgerClient(LedgerClientBase):
    def __init__(self, bill_id=1, vendor_id=56):
        qbo = quickbooks_settings()
        self.auth_client = AuthClient(
            client_id=qbo["client_id"],
            client_secret=qbo["secret_key"],
            environment=qbo["qbook_env"],
            redirect_uri=qbo["redirect_uri"],
        )
        self.client = None
        self.bill_id = bill_id
        self.vendor_id = vendor_id
        self.single_bill_data = None
        self.single_vendor_data = None
        self.list_bills = []
        self.list_vendors = []
        self._connection = None

    def _get_connection(self, state_token=None):
        authorization_url = self.auth_client.get_authorization_url([Scopes.ACCOUNTING], state_token=state_token)
        return authorization_url

    def initiate_quick_book(self, request, auth_code, realm_id):
        self.auth_client.get_bearer_token(auth_code=auth_code, realm_id=realm_id)

        # Initialize and return your QuickBooks connection
        self.client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self.auth_client.refresh_token,
            company_id=realm_id,
            # Intuit stopped serving minor versions below 75 on 2025-08-01.
            minorversion=75,
        )

    def get_bills(self, num=50, vendor_id=None):
        try:
            # Implement this method to retrieve a list of bills
            all_bills = Bill.all(qb=self.client, max_results=min(50, max(1, int(num))))
            self.list_bills = [bill_summary(bill) for bill in all_bills]
        except Exception as e:
            raise RuntimeError('Accounting provider request failed.') from None

    def get_bill(self, bill_id):
        try:
            single_bill = Bill.get(qb=self.client, id=bill_id)
            self.single_bill_data = single_bill
        except Exception as e:
            raise RuntimeError('Accounting provider request failed.') from None

    def get_vendors(self, num=50):
        try:
            # Implement this method to retrieve a list of vendors
            all_vendors = Vendor.all(qb=self.client, max_results=min(50, max(1, int(num))))
            self.list_vendors = [vendor_summary(vendor) for vendor in all_vendors]
        except Exception as e:
            raise RuntimeError('Accounting provider request failed.') from None

    def get_vendor(self, vendor_id):
        try:
            single_vendor = Vendor.get(qb=self.client, id=vendor_id)
            self.single_vendor_data = single_vendor
        except Exception as e:
            raise RuntimeError('Accounting provider request failed.') from None


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
