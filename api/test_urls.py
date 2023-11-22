from django.urls import path
from .views import initiate_ledger_process, quickbooks_callback_handler
urlpatterns = [path('initiate_ledger_process/', initiate_ledger_process), path('accounts/quickbooks/login/callback/', quickbooks_callback_handler)]
