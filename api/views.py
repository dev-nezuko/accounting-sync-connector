from django.shortcuts import redirect
from .ledger import LedgerClient
from django.http import JsonResponse


def initiate_ledger_process(request):
    try:
        ledger_client = LedgerClient()
        authorization_url = ledger_client._get_connection()
        return redirect(authorization_url)
    except Exception as e:
        raise e


# This view handles the callback from QuickBooks
def quickbooks_callback_handler(request):
    try:
        auth_code = request.GET.get('code')
        realm_id = request.GET.get('realmId')

        # Retrieve all data by sending auth code
        ledger_client = LedgerClient()
        ledger_client.initiate_quick_book(request, auth_code, realm_id)

        # Retrieve all functional data
        single_bill_data = get_single_bill_data(ledger_client)
        all_bills_data = get_all_bills_data(ledger_client)
        single_vendor_data = get_single_vendor_data(ledger_client)
        all_vendors_data = get_all_vendors_data(ledger_client)

        data = {
            "single_bill": single_bill_data,
            "all_bills": all_bills_data,
            "single_vendor": single_vendor_data,
            "all_vendors": all_vendors_data,
        }
        return JsonResponse(data)
    except Exception as e:
        raise e


def get_single_bill_data(ledger_client):
    ledger_client.get_bill(ledger_client)
    return {
        "id": ledger_client.single_bill_data.Id,
        "balance": ledger_client.single_bill_data.Balance,
        "vendor_name": ledger_client.single_bill_data.VendorRef.name,
     }


def get_all_bills_data(ledger_client):
    ledger_client.get_bills(ledger_client)
    return ledger_client.list_bills


def get_single_vendor_data(ledger_client):
    ledger_client.get_vendor(ledger_client)
    return {
        "id": ledger_client.single_vendor_data.Id,
        "balance": ledger_client.single_vendor_data.Balance,
        "vendor_name": ledger_client.single_vendor_data.DisplayName,
    }


def get_all_vendors_data(ledger_client):
    ledger_client.get_vendors(ledger_client)
    return ledger_client.list_vendors
