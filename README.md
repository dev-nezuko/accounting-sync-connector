# Routable
Routable code for Fintech App

# Steps and Guides for Quick Book Connection

Start from these steps to get head around that how we can work with postman api calls and get OAuth2
for authentication.
https://developer.intuit.com/app/developer/qbo/docs/develop/sandboxes/postman#get-collection.


### Create a Sandbox on QuickBook

https://developer.intuit.com/app/developer/sandbox

### Create Keys in Dev Settings

https://developer.intuit.com/app/developer/appdetail/test/keys?appId=djQuMTo6OGQzYmJlYTI3Yg:0760ebfa-3caf-40b1-b896-3437c333b822

By Setting keys you will provide the OAuth2 redirect URL for you application to get access token and refresh token

Install the main package for quickbook SDK

https://pypi.org/project/python-quickbooks/

Use this repo to setup the OAuth2.0 for python adn follow docs guideline.

https://github.com/intuit/oauth-pythonclient
https://oauth-pythonclient.readthedocs.io/en/latest/user-guide.html#authorize-your-app


After Following all guide lines.

### Make a virtual ENV on your machine with Python 3.11

Then run these commands 
- pip install -r requirements.txt
- python manage.py runserver localhost:8003
- on browser call localhost:8003/initiate_ledger_process/

Use the example.env file to make .env to get desired variables


