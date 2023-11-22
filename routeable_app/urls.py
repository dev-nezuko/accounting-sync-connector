from django.contrib import admin
from django.urls import path

from api.views import initiate_ledger_process, quickbooks_callback_handler

urlpatterns = [
    path('admin/', admin.site.urls),
    path('initiate_ledger_process/', initiate_ledger_process, name='initiate_ledger_process'),
    path('accounts/quickbooks/login/callback/', quickbooks_callback_handler, name='quickbooks_callback'),
]
