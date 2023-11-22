import os
import runpy
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from intuitlib.exceptions import AuthClientError
from quickbooks.exceptions import ObjectNotFoundException, QuickbooksException

from .ledger import LedgerClient

CALLBACK = '/accounts/quickbooks/login/callback/'
START = '/initiate_ledger_process/'
VALID_CALLBACK = {'state': 'synthetic-state', 'code': 'synthetic-code', 'realmId': 'synthetic-realm'}
EMPTY_SNAPSHOT = {'single_bill': None, 'all_bills': [], 'single_vendor': None, 'all_vendors': []}


def offline_client():
    """A LedgerClient with a placeholder SDK connection and no AuthClient."""
    client = LedgerClient.__new__(LedgerClient)
    client.qb = object()
    client.bill_id, client.vendor_id = 1, 56
    return client


def fake_bill(bill_id='b1', balance=10, vendor='Sample Vendor'):
    return SimpleNamespace(Id=bill_id, Balance=balance, VendorRef=None if vendor is None else SimpleNamespace(name=vendor))


class OAuthFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('synthetic-staff', password='Synthetic!456', is_staff=True)
        self.client.force_login(self.user)

    def pending(self, state='synthetic-state', issued=None):
        session = self.client.session
        session['qbo_oauth_state'] = {'value': state, 'issued': time.time() if issued is None else issued}
        session.save()

    def test_anonymous_cannot_start_flow(self):
        self.client.logout()
        with patch('api.views.LedgerClient') as client:
            self.assertEqual(self.client.get(START).status_code, 302)
        client.assert_not_called()

    def test_nonstaff_cannot_start_flow(self):
        self.user.is_staff = False
        self.user.save()
        self.assertEqual(self.client.get(START).status_code, 302)

    def test_nonstaff_cannot_use_callback(self):
        self.user.is_staff = False
        self.user.save()
        self.pending()
        with patch('api.views.LedgerClient') as client:
            self.assertEqual(self.client.get(CALLBACK, VALID_CALLBACK).status_code, 302)
        client.assert_not_called()

    def test_start_rejects_post(self):
        self.assertEqual(self.client.post(START).status_code, 405)

    def test_start_saves_generated_state_and_passes_it_to_sdk(self):
        with patch('api.views.LedgerClient') as client:
            client.return_value.authorization_url.return_value = 'https://example.invalid/authorize'
            response = self.client.get(START)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], 'https://example.invalid/authorize')
        state = self.client.session['qbo_oauth_state']['value']
        self.assertGreaterEqual(len(state), 32)
        client.return_value.authorization_url.assert_called_once_with(state)

    def test_each_start_issues_a_fresh_state(self):
        with patch('api.views.LedgerClient') as client:
            client.return_value.authorization_url.return_value = 'https://example.invalid/authorize'
            self.client.get(START)
            first = self.client.session['qbo_oauth_state']['value']
            self.client.get(START)
        self.assertNotEqual(first, self.client.session['qbo_oauth_state']['value'])

    @override_settings(QUICKBOOKS={'client_id': '', 'secret_key': '', 'redirect_uri': '', 'qbook_env': 'sandbox', 'company_id': ''})
    def test_missing_credentials_stop_the_flow_before_redirecting(self):
        response = self.client.get(START)
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('qbo_oauth_state', self.client.session)

    def test_missing_mismatched_and_expired_state_never_exchange_tokens(self):
        for state, age in [('wrong', 0), ('synthetic-state', 601), ('synthetic-state', -5)]:
            self.pending(issued=time.time() - age)
            with patch('api.views.LedgerClient') as client:
                response = self.client.get(CALLBACK, {**VALID_CALLBACK, 'state': state})
            self.assertEqual(response.status_code, 400)
            client.assert_not_called()

    def test_callback_without_pending_state_is_rejected(self):
        with patch('api.views.LedgerClient') as client:
            self.assertEqual(self.client.get(CALLBACK, VALID_CALLBACK).status_code, 400)
        client.assert_not_called()

    def test_failed_state_check_still_consumes_the_state(self):
        self.pending()
        with patch('api.views.LedgerClient') as client:
            self.assertEqual(self.client.get(CALLBACK, {**VALID_CALLBACK, 'state': 'guess'}).status_code, 400)
            self.assertEqual(self.client.get(CALLBACK, VALID_CALLBACK).status_code, 400)
        client.assert_not_called()

    def test_declined_or_incomplete_authorization_never_exchanges_tokens(self):
        declined = {**VALID_CALLBACK, 'error': 'access_denied'}
        no_code = {'state': 'synthetic-state', 'realmId': 'synthetic-realm'}
        no_realm = {'state': 'synthetic-state', 'code': 'synthetic-code'}
        for params in [declined, no_code, no_realm]:
            self.pending()
            with patch('api.views.LedgerClient') as client:
                self.assertEqual(self.client.get(CALLBACK, params).status_code, 400)
            client.assert_not_called()

    def test_valid_callback_is_single_use_and_does_not_store_auth_code(self):
        self.pending()
        with patch('api.views.LedgerClient') as factory:
            factory.return_value.snapshot.return_value = EMPTY_SNAPSHOT
            response = self.client.get(CALLBACK, VALID_CALLBACK)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), EMPTY_SNAPSHOT)
            self.assertEqual(response['Cache-Control'], 'no-store')
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            factory.return_value.connect.assert_called_once_with('synthetic-code', 'synthetic-realm')
            self.assertNotIn('qbo_auth_code', self.client.session)
            self.assertEqual(self.client.get(CALLBACK, VALID_CALLBACK).status_code, 400)

    def test_configured_company_mismatch_never_exchanges_token(self):
        self.pending()
        with patch('api.views.LedgerClient') as client, patch.dict('django.conf.settings.QUICKBOOKS', company_id='approved-realm'):
            self.assertEqual(self.client.get(CALLBACK, {**VALID_CALLBACK, 'realmId': 'other-realm'}).status_code, 400)
        client.assert_not_called()

    def test_configured_company_match_is_accepted(self):
        self.pending()
        with patch('api.views.LedgerClient') as client, patch.dict('django.conf.settings.QUICKBOOKS', company_id='synthetic-realm'):
            client.return_value.snapshot.return_value = EMPTY_SNAPSHOT
            self.assertEqual(self.client.get(CALLBACK, VALID_CALLBACK).status_code, 200)

    def test_provider_errors_do_not_expose_details(self):
        token_response = SimpleNamespace(status_code=400, text='synthetic-private-detail', content=b'synthetic-private-detail', headers={})
        for error in [AuthClientError(token_response), QuickbooksException('synthetic-private-detail', 500)]:
            self.pending()
            with patch('api.views.LedgerClient') as client:
                client.return_value.connect.side_effect = error
                response = self.client.get(CALLBACK, VALID_CALLBACK)
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('synthetic-private', response.content.decode())


class LedgerClientTests(SimpleTestCase):
    def test_auth_client_receives_configured_credentials(self):
        with patch('api.ledger.AuthClient') as auth:
            LedgerClient()
        auth.assert_called_once_with(client_id='synthetic-client', client_secret='synthetic-secret', environment='sandbox',
                                     redirect_uri='http://testserver/accounts/quickbooks/login/callback/')

    def test_unknown_environment_is_rejected(self):
        with patch.dict('django.conf.settings.QUICKBOOKS', qbook_env='staging'), self.assertRaises(ImproperlyConfigured):
            LedgerClient()

    def test_authorization_url_requests_accounting_scope_with_state(self):
        with patch('api.ledger.AuthClient') as auth:
            LedgerClient().authorization_url('synthetic-state')
        scopes = auth.return_value.get_authorization_url.call_args.args[0]
        self.assertEqual([scope.value for scope in scopes], ['com.intuit.quickbooks.accounting'])
        self.assertEqual(auth.return_value.get_authorization_url.call_args.kwargs, {'state_token': 'synthetic-state'})

    def test_connect_requests_a_supported_minor_version(self):
        client = LedgerClient.__new__(LedgerClient)
        client.auth_client = SimpleNamespace(get_bearer_token=lambda **kwargs: None, refresh_token='synthetic-refresh')
        with patch('api.ledger.QuickBooks') as qb:
            client.connect('synthetic-code', 'synthetic-realm')
        self.assertGreaterEqual(qb.call_args.kwargs['minorversion'], 75)
        self.assertEqual(qb.call_args.kwargs['company_id'], 'synthetic-realm')
        self.assertEqual(qb.call_args.kwargs['refresh_token'], 'synthetic-refresh')

    def test_requested_bill_id_reaches_sdk(self):
        client = offline_client()
        with patch('api.ledger.Bill.get', return_value=fake_bill('requested-id')) as get:
            self.assertEqual(client.bill('requested-id')['id'], 'requested-id')
        get.assert_called_once_with('requested-id', qb=client.qb)

    def test_missing_single_records_become_null(self):
        client = offline_client()
        missing = ObjectNotFoundException('Object Not Found', 610)
        with patch('api.ledger.Bill.get', side_effect=missing), patch('api.ledger.Vendor.get', side_effect=missing):
            self.assertIsNone(client.bill(1))
            self.assertIsNone(client.vendor(56))

    def test_other_provider_errors_propagate(self):
        with patch('api.ledger.Bill.get', side_effect=QuickbooksException('boom', 500)), self.assertRaises(QuickbooksException):
            offline_client().bill(1)

    def test_list_reads_are_capped_at_fifty(self):
        client = offline_client()
        with patch('api.ledger.Bill.all', return_value=[]) as bills, patch('api.ledger.Vendor.all', return_value=[]) as vendors:
            client.bills(500)
            client.vendors(0)
        self.assertEqual(bills.call_args.kwargs['max_results'], 50)
        self.assertEqual(vendors.call_args.kwargs['max_results'], 1)

    def test_bill_without_vendor_ref_is_still_summarised(self):
        with patch('api.ledger.Bill.all', return_value=[fake_bill('b2', 0, vendor=None)]):
            self.assertEqual(offline_client().bills(), [{'id': 'b2', 'balance': 0, 'vendor_name': None}])

    def test_snapshot_shape(self):
        client = offline_client()
        vendor = SimpleNamespace(Id='56', Balance=0, DisplayName='Sample Supplies')
        with patch('api.ledger.Bill.get', return_value=fake_bill('1')), patch('api.ledger.Bill.all', return_value=[fake_bill('1')]), \
                patch('api.ledger.Vendor.get', return_value=vendor), patch('api.ledger.Vendor.all', return_value=[vendor]):
            snapshot = client.snapshot()
        self.assertEqual(snapshot['single_bill'], {'id': '1', 'balance': 10, 'vendor_name': 'Sample Vendor'})
        self.assertEqual(snapshot['all_vendors'], [{'id': '56', 'balance': 0, 'vendor_name': 'Sample Supplies'}])


class SettingsTests(SimpleTestCase):
    def load(self, **env):
        with patch.dict(os.environ, env, clear=True):
            return runpy.run_path(str(Path(__file__).resolve().parent.parent / 'routeable_app' / 'settings.py'))

    def test_debug_is_off_and_signing_key_required_by_default(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load()

    def test_debug_opt_in_uses_random_key_and_relaxed_cookies(self):
        loaded = self.load(DJANGO_DEBUG='True')
        self.assertTrue(loaded['DEBUG'])
        self.assertGreaterEqual(len(loaded['SECRET_KEY']), 40)
        self.assertFalse(loaded['SESSION_COOKIE_SECURE'])

    def test_production_settings_use_secure_cookies_and_trimmed_hosts(self):
        loaded = self.load(DJANGO_SECRET_KEY='synthetic-signing-key', DJANGO_ALLOWED_HOSTS='example.test, api.example.test')
        self.assertFalse(loaded['DEBUG'])
        self.assertTrue(loaded['SESSION_COOKIE_SECURE'])
        self.assertTrue(loaded['CSRF_COOKIE_SECURE'])
        self.assertEqual(loaded['ALLOWED_HOSTS'], ['example.test', 'api.example.test'])
        self.assertEqual(loaded['QUICKBOOKS']['qbook_env'], 'sandbox')
        self.assertNotIn('allauth', ' '.join(loaded['INSTALLED_APPS']))
