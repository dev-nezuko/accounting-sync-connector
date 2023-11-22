import os
import runpy
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from .ledger import LedgerClient
class OAuthFlowTests(TestCase):
    callback='/accounts/quickbooks/login/callback/'
    def setUp(self):
        self.user=get_user_model().objects.create_user('synthetic-staff',password='Synthetic!456',is_staff=True)
        self.client.force_login(self.user)
    def pending(self,state='synthetic-state',issued=None):
        session=self.client.session;session['qbo_oauth_state']={'value':state,'issued':time.time() if issued is None else issued};session.save()
    def test_anonymous_cannot_start_flow(self):
        self.client.logout()
        with patch('api.views.LedgerClient') as client:
            self.assertEqual(self.client.get('/initiate_ledger_process/').status_code,302)
        client.assert_not_called()
    def test_nonstaff_cannot_start_flow(self):
        self.user.is_staff=False;self.user.save();self.assertEqual(self.client.get('/initiate_ledger_process/').status_code,302)
    def test_start_saves_generated_state_and_passes_it_to_sdk(self):
        with patch('api.views.LedgerClient') as client:
            client.return_value._get_connection.return_value='https://example.invalid/authorize'
            self.assertEqual(self.client.get('/initiate_ledger_process/').status_code,302)
            state=self.client.session['qbo_oauth_state']['value']
            self.assertGreaterEqual(len(state),32);client.return_value._get_connection.assert_called_once_with(state_token=state)
    def test_missing_mismatched_and_expired_state_never_exchange_tokens(self):
        for state,age in [('wrong',0),('synthetic-state',601)]:
            self.pending(issued=time.time()-age)
            with patch('api.views.LedgerClient') as client:
                response=self.client.get(self.callback,{'state':state,'code':'synthetic-code','realmId':'synthetic-realm'})
            self.assertEqual(response.status_code,400);client.assert_not_called()
    def test_valid_callback_is_single_use_and_does_not_store_auth_code(self):
        self.pending()
        with patch('api.views.LedgerClient') as factory:
            client=factory.return_value;client.single_bill_data=None;client.single_vendor_data=None;client.list_bills=[];client.list_vendors=[]
            response=self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'synthetic-realm'})
            self.assertEqual(response.status_code,200);self.assertEqual(response['Cache-Control'],'no-store')
            client.initiate_quick_book.assert_called_once()
            self.assertNotIn('qbo_auth_code',self.client.session)
            self.assertEqual(self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'synthetic-realm'}).status_code,400)
    def test_configured_company_mismatch_never_exchanges_token(self):
        self.pending()
        with patch('api.views.LedgerClient') as client,patch.dict('django.conf.settings.QUICKBOOKS',company_id='approved-realm'):
            self.assertEqual(self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'other-realm'}).status_code,400)
        client.assert_not_called()
    def test_provider_error_does_not_expose_details(self):
        self.pending()
        with patch('api.views.LedgerClient',side_effect=RuntimeError('synthetic-private-provider-error')):
            response=self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'synthetic-realm'})
        self.assertEqual(response.status_code,502);self.assertNotIn('synthetic-private',response.content.decode())
    def test_requested_bill_id_reaches_sdk(self):
        client=LedgerClient.__new__(LedgerClient);client.client=object()
        with patch('api.ledger.Bill.get',return_value=SimpleNamespace(Id='sample')) as get:
            client.get_bill('requested-id');get.assert_called_once_with(qb=client.client,id='requested-id')
    def test_repeated_list_reads_replace_previous_results(self):
        client=LedgerClient.__new__(LedgerClient);client.client=object()
        bills=[SimpleNamespace(Id='b1',Balance=10,VendorRef=SimpleNamespace(name='Sample Vendor'))]
        with patch('api.ledger.Bill.all',return_value=bills):
            client.get_bills();client.get_bills()
        self.assertEqual(client.list_bills,[{'id':'b1','balance':10,'vendor_name':'Sample Vendor'}])
    def test_bill_without_vendor_ref_is_still_summarised(self):
        client=LedgerClient.__new__(LedgerClient);client.client=object()
        with patch('api.ledger.Bill.all',return_value=[SimpleNamespace(Id='b2',Balance=0,VendorRef=None)]):
            client.get_bills()
        self.assertEqual(client.list_bills,[{'id':'b2','balance':0,'vendor_name':None}])
    def test_quickbooks_client_requests_a_supported_minor_version(self):
        client=LedgerClient.__new__(LedgerClient);client.auth_client=SimpleNamespace(get_bearer_token=lambda **kw:None,refresh_token='synthetic-refresh')
        with patch('api.ledger.QuickBooks') as qb:
            client.initiate_quick_book(None,'synthetic-code','synthetic-realm')
        self.assertGreaterEqual(qb.call_args.kwargs['minorversion'],75)
        self.assertEqual(qb.call_args.kwargs['company_id'],'synthetic-realm')
    @override_settings(QUICKBOOKS={'client_id':'','secret_key':'','redirect_uri':'','qbook_env':'sandbox','company_id':''})
    def test_missing_credentials_stop_the_flow_before_redirecting(self):
        response=self.client.get('/initiate_ledger_process/')
        self.assertEqual(response.status_code,502);self.assertNotIn('qbo_oauth_state',self.client.session)
    def test_unknown_environment_is_rejected(self):
        with patch.dict('django.conf.settings.QUICKBOOKS',qbook_env='staging'),self.assertRaises(ImproperlyConfigured):
            LedgerClient()
    def test_auth_client_receives_configured_credentials(self):
        with patch('api.ledger.AuthClient') as auth:
            LedgerClient()
        auth.assert_called_once_with(client_id='synthetic-client',client_secret='synthetic-secret',environment='sandbox',redirect_uri='http://testserver/accounts/quickbooks/login/callback/')
class SettingsTests(TestCase):
    def load(self,**env):
        with patch.dict(os.environ,env,clear=True):
            return runpy.run_path(str(Path(__file__).resolve().parent.parent/'routeable_app'/'settings.py'))
    def test_debug_is_off_and_signing_key_required_by_default(self):
        with self.assertRaises(ImproperlyConfigured):
            self.load()
    def test_debug_opt_in_uses_random_key_and_relaxed_cookies(self):
        loaded=self.load(DJANGO_DEBUG='True')
        self.assertTrue(loaded['DEBUG']);self.assertGreaterEqual(len(loaded['SECRET_KEY']),40);self.assertFalse(loaded['SESSION_COOKIE_SECURE'])
    def test_production_settings_use_secure_cookies_and_trimmed_hosts(self):
        loaded=self.load(DJANGO_SECRET_KEY='synthetic-signing-key',DJANGO_ALLOWED_HOSTS='example.test, api.example.test')
        self.assertFalse(loaded['DEBUG']);self.assertTrue(loaded['SESSION_COOKIE_SECURE']);self.assertTrue(loaded['CSRF_COOKIE_SECURE'])
        self.assertEqual(loaded['ALLOWED_HOSTS'],['example.test','api.example.test'])
