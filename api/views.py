import secrets
import time
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from decouple import config
from .ledger import LedgerClient

@staff_member_required(login_url='/admin/login/')
@require_GET
def initiate_ledger_process(request):
    state = secrets.token_urlsafe(32)
    try:
        client = LedgerClient()
        url = client._get_connection(state_token=state)
    except Exception:
        return JsonResponse({'error': 'Accounting authorization could not be started.'}, status=502)
    request.session['qbo_oauth_state'] = {'value': state, 'issued': time.time()}
    return redirect(url)

@staff_member_required(login_url='/admin/login/')
@require_GET
def quickbooks_callback_handler(request):
    pending = request.session.pop('qbo_oauth_state', None)
    supplied = request.GET.get('state', '')
    if not isinstance(pending, dict) or not isinstance(pending.get('value'), str) or not isinstance(pending.get('issued'), (int, float)):
        return JsonResponse({'error': 'Missing or expired authorization state.'}, status=400)
    age = time.time() - pending['issued']
    if age < 0 or age > 600 or not secrets.compare_digest(pending['value'], supplied):
        return JsonResponse({'error': 'Invalid or expired authorization state.'}, status=400)
    code, realm = request.GET.get('code'), request.GET.get('realmId')
    if request.GET.get('error') or not code or not realm:
        return JsonResponse({'error': 'Authorization was declined or incomplete.'}, status=400)
    expected = config('QBOOK_COMPANY_ID', default='')
    if expected and realm != expected:
        return JsonResponse({'error': 'This company is not configured for this demo.'}, status=400)
    try:
        client = LedgerClient()
        client.initiate_quick_book(request, code, realm)
        data = {'single_bill': get_single_bill_data(client), 'all_bills': get_all_bills_data(client),
                'single_vendor': get_single_vendor_data(client), 'all_vendors': get_all_vendors_data(client)}
    except Exception:
        return JsonResponse({'error': 'Accounting data could not be retrieved.'}, status=502)
    response = JsonResponse(data)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response

def get_single_bill_data(client):
    client.get_bill(client.bill_id)
    bill = client.single_bill_data
    return None if bill is None else {'id': bill.Id, 'balance': bill.Balance, 'vendor_name': bill.VendorRef.name}

def get_all_bills_data(client):
    client.get_bills()
    return client.list_bills

def get_single_vendor_data(client):
    client.get_vendor(client.vendor_id)
    vendor = client.single_vendor_data
    return None if vendor is None else {'id': vendor.Id, 'balance': vendor.Balance, 'vendor_name': vendor.DisplayName}

def get_all_vendors_data(client):
    client.get_vendors()
    return client.list_vendors
