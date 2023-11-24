import time
from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
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
        with patch('api.views.LedgerClient') as factory, patch('api.views.config',return_value=''):
            client=factory.return_value;client.single_bill_data=None;client.single_vendor_data=None;client.list_bills=[];client.list_vendors=[]
            response=self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'synthetic-realm'})
            self.assertEqual(response.status_code,200);self.assertEqual(response['Cache-Control'],'no-store')
            client.initiate_quick_book.assert_called_once()
            self.assertNotIn('qbo_auth_code',self.client.session)
            self.assertEqual(self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'synthetic-realm'}).status_code,400)
    def test_configured_company_mismatch_never_exchanges_token(self):
        self.pending()
        with patch('api.views.LedgerClient') as client,patch('api.views.config',return_value='approved-realm'):
            self.assertEqual(self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'other-realm'}).status_code,400)
        client.assert_not_called()
    def test_provider_error_does_not_expose_details(self):
        self.pending()
        with patch('api.views.LedgerClient',side_effect=RuntimeError('synthetic-private-provider-error')),patch('api.views.config',return_value=''):
            response=self.client.get(self.callback,{'state':'synthetic-state','code':'synthetic-code','realmId':'synthetic-realm'})
        self.assertEqual(response.status_code,502);self.assertNotIn('synthetic-private',response.content.decode())
    def test_requested_bill_id_reaches_sdk(self):
        client=LedgerClient.__new__(LedgerClient);client.client=object()
        with patch('api.ledger.Bill.get',return_value=SimpleNamespace(Id='sample')) as get:
            client.get_bill('requested-id');get.assert_called_once_with(qb=client.client,id='requested-id')
