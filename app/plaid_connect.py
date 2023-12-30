import requests
from flask import current_app, jsonify, flash
from flask_babel import _
from flask_login import current_user
import plaid
import json
from plaid.model.products import Products
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transfer_authorization_create_request import TransferAuthorizationCreateRequest
from plaid.model.transfer_type import TransferType
from plaid.model.transfer_network import TransferNetwork
from plaid.model.ach_class import ACHClass
from plaid.model.transfer_user_in_request import TransferUserInRequest
from plaid.model.transfer_user_address_in_request import TransferUserAddressInRequest
from plaid.model.transfer_create_request import TransferCreateRequest
from plaid.model.transfer_create_idempotency_key import TransferCreateIdempotencyKey
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest


def configure():
  if not current_app.config['PLAID_ENV'] or \
    not current_app.config['PLAID_CLIENT_ID'] or \
      not current_app.config['PLAID_SECRET'] :
      return _('Error: The plaid service is not configured')
  
  # Configure Plaid host
  if current_app.config['PLAID_ENV'] == 'sandbox':
    host = plaid.Environment.Sandbox
  if current_app.config['PLAID_ENV'] == 'development':
    host = plaid.Environment.Development
  if current_app.config['PLAID_ENV'] == 'production':
    host = plaid.Environment.Production

  # Set plaid client using .env credentials
  configuration = None
  configuration = plaid.Configuration(
    host=host,
    api_key={
      'clientId': current_app.config['PLAID_CLIENT_ID'],
      'secret': current_app.config['PLAID_SECRET'],
      'plaidVersion': '2020-09-14'
      }
      )
  api_client = plaid.ApiClient(configuration)
  client = plaid_api.PlaidApi(api_client)
  return client

def get_products():
  products = []
  for product in current_app.config['PLAID_PRODUCTS']:
    products.append(Products(product))
  return products

def pretty_print_response(response):
  print(json.dumps(response, indent=2, sort_keys=True, default=str))

def format_error(e):
  return {'error': {'display_message': e.display_message, 'error_code': e.code, 'error_type': e.type, 'error_message': e.message } }

def check_institution(ins_id):
  items = current_user.linked_items()
  existing_institution = ""
  for i in items:
    if i.ins_id == ins_id:
      existing_institution = "exists"
  return existing_institution

def get_institution(ins_id):
  client = configure()
  try:
      request = InstitutionsGetByIdRequest(
          institution_id=ins_id,
          country_codes=list(map(lambda x: CountryCode(x), current_app.config['PLAID_COUNTRY_CODES'])),
      )
      response = client.institutions_get_by_id(request)
      return response['institution']['name']

  except plaid.ApiException as e:
      error_response = format_error(e)
      return jsonify(error_response)

    
def authorize_and_create_transfer(access_token):
    client = configure()
    try:
        # We call /accounts/get to obtain first account_id - in production,
        # account_id's should be persisted in a data store and retrieved
        # from there.
        request = AccountsGetRequest(access_token=access_token)
        response = client.accounts_get(request)
        account_id = response['accounts'][0]['account_id']

        request = TransferAuthorizationCreateRequest(
            access_token=access_token,
            account_id=account_id,
            type=TransferType('credit'),
            network=TransferNetwork('ach'),
            amount='1.34',
            ach_class=ACHClass('ppd'),
            user=TransferUserInRequest(
                legal_name='FirstName LastName',
                email_address='foobar@email.com',
                address=TransferUserAddressInRequest(
                    street='123 Main St.',
                    city='San Francisco',
                    region='CA',
                    postal_code='94053',
                    country='US'
                ),
            ),
        )
        response = client.transfer_authorization_create(request)
        pretty_print_response(response)
        authorization_id = response['authorization']['id']

        request = TransferCreateRequest(
            idempotency_key=TransferCreateIdempotencyKey('1223abc456xyz7890001'),
            access_token=access_token,
            account_id=account_id,
            authorization_id=authorization_id,
            type=TransferType('credit'),
            network=TransferNetwork('ach'),
            amount='1.34',
            description='Payment',
            ach_class=ACHClass('ppd'),
            user=TransferUserInRequest(
                legal_name='FirstName LastName',
                email_address='foobar@email.com',
                address=TransferUserAddressInRequest(
                    street='123 Main St.',
                    city='San Francisco',
                    region='CA',
                    postal_code='94053',
                    country='US'
                ),
            ),
        )
        response = client.transfer_create(request)
        pretty_print_response(response)
        return response['transfer']['id']
    except plaid.ApiException as e:
        error_response = format_error(e)
        return jsonify(error_response)

### This works using basic methods

# def get_balance():
#     headers = {
#         'Content-Type': 'application/json', 
#         'Accept':'application/json'
#         }
#     body = {
#         'client_id': '5f18ff51b89a9900124d8bfc',
#         'secret': 'e90d996c11e61e53df3407f93955cd',
#         'access_token': 'access-production-444483d5-bafb-4d3c-a554-8965ac1a092b',
#         'start_date': '2022-05-01',
#         'end_date': '2022-05-01'
#         }
#     r = requests.post(
#         'https://{}.plaid.com/transactions/get'.format(
#             environment), headers=headers, json=body)
#     if r.status_code != 200:
#         return r.json()['error_message']
#     return r.json()['accounts'][0]['balances']['current'] # update the 0 to the item ID, or figure out how to index on account ID