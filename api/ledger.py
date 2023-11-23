from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.bill import Bill
from quickbooks.objects.vendor import Vendor
from decouple import config


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
        self.auth_client = AuthClient(
            client_id=config("QBOOK_CLIENT_ID", None),
            client_secret=config("QBOOK_CLIENT_SECRET", None),
            environment=config("QBOOK_ENVIRONMENT", None),
            redirect_uri=config("QBOOK_REDIRECT_URI", None),
        )
        self.client = None
        self.bill_id = bill_id
        self.vendor_id = vendor_id
        self.single_bill_data = None
        self.single_vendor_data = None
        self.list_bills = []
        self.list_vendors = []
        super().__init__()

    def _get_connection(self):
        authorization_url = self.auth_client.get_authorization_url([Scopes.ACCOUNTING])
        return authorization_url

    def get_code(self, request):
        auth_code = request.session.get('qbo_auth_code')
        return auth_code

    def initiate_quick_book(self, request, auth_code):
        request.session['qbo_auth_code'] = auth_code
        self.auth_client.get_bearer_token(auth_code)

        # Initialize and return your QuickBooks connection
        self.client = QuickBooks(
            auth_client=self.auth_client,
            refresh_token=self.auth_client.refresh_token,
            company_id=config("QBOOK_COMPANY_ID", None),
            minorversion=1
        )

    def get_bills(self, num=50, vendor_id=None):
        # Implement this method to retrieve a list of bills
        all_bills = Bill.all(qb=self.client, max_results=50)
        self.list_bills = all_bills

    def get_bill(self, bill_id):
        single_bill = Bill.get(qb=self.client, id=self.bill_id)
        self.single_bill_data = single_bill

    def get_vendors(self, num=50):
        # Implement this method to retrieve a list of vendors
        all_vendors = Vendor.all(qb=self.client, max_results=50)
        self.list_vendors = all_vendors

    def get_vendor(self, vendor_id):
        single_vendor = Vendor.get(qb=self.client, id=self.vendor_id)
        self.single_vendor_data = single_vendor
