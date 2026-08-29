"""Print a throwaway anonymous Appwrite JWT for the production smoke."""
from appwrite.client import Client
from appwrite.services.account import Account

client = Client()
client.set_endpoint("https://sfo.cloud.appwrite.io/v1")
client.set_project("6a6f9133001ed182210d")
client.set_self_signed(False)
account = Account(client)
session = account.create_anonymous_session()
jwt_doc = account.create_jwt()
print(jwt_doc["jwt"])
