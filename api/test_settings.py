SECRET_KEY = 'offline-accounting-check-key-not-for-deployment'
DEBUG = False
ALLOWED_HOSTS = ['testserver']
ROOT_URLCONF = 'api.test_urls'
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'api']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
QUICKBOOKS = {
    'client_id': 'synthetic-client',
    'secret_key': 'synthetic-secret',
    'redirect_uri': 'http://testserver/accounts/quickbooks/login/callback/',
    'qbook_env': 'sandbox',
    'company_id': '',
}
