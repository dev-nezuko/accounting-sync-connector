import secrets
import time

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET

from .ledger import PROVIDER_ERRORS, LedgerClient

STATE_SESSION_KEY = 'qbo_oauth_state'
STATE_MAX_AGE_SECONDS = 600


@staff_member_required(login_url='/admin/login/')
@require_GET
def initiate_ledger_process(request):
    state = secrets.token_urlsafe(32)
    try:
        url = LedgerClient().authorization_url(state)
    except (ImproperlyConfigured, *PROVIDER_ERRORS):
        return JsonResponse({'error': 'Accounting authorization could not be started.'}, status=502)
    request.session[STATE_SESSION_KEY] = {'value': state, 'issued': time.time()}
    return redirect(url)


@staff_member_required(login_url='/admin/login/')
@require_GET
def quickbooks_callback_handler(request):
    # Popping before any comparison makes every state single-use, even when the check fails.
    pending = request.session.pop(STATE_SESSION_KEY, None)
    supplied = request.GET.get('state', '')
    if not isinstance(pending, dict) or not isinstance(pending.get('value'), str) or not isinstance(pending.get('issued'), (int, float)):
        return JsonResponse({'error': 'Missing or expired authorization state.'}, status=400)
    age = time.time() - pending['issued']
    if age < 0 or age > STATE_MAX_AGE_SECONDS or not secrets.compare_digest(pending['value'], supplied):
        return JsonResponse({'error': 'Invalid or expired authorization state.'}, status=400)
    code, realm = request.GET.get('code'), request.GET.get('realmId')
    if request.GET.get('error') or not code or not realm:
        return JsonResponse({'error': 'Authorization was declined or incomplete.'}, status=400)
    expected = settings.QUICKBOOKS.get('company_id', '')
    if expected and realm != expected:
        return JsonResponse({'error': 'This company is not configured for this demo.'}, status=400)
    try:
        client = LedgerClient()
        client.connect(code, realm)
        data = client.snapshot()
    except (ImproperlyConfigured, *PROVIDER_ERRORS):
        return JsonResponse({'error': 'Accounting data could not be retrieved.'}, status=502)
    response = JsonResponse(data)
    response['Cache-Control'] = 'no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response
