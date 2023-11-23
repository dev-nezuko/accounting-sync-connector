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

        # Save the auth_code in session
        ledger_client = LedgerClient()
        ledger_client.initiate_quick_book(request, auth_code)
        ledger_client.get_bill(ledger_client)
        ledger_client.get_bills(ledger_client)
        ledger_client.get_vendor(ledger_client)
        ledger_client.get_vendors(ledger_client)

        return JsonResponse(
            {
                "auth_code": auth_code,
                "realm_id": realm_id,
            }
        )

    except Exception as e:
        raise e
