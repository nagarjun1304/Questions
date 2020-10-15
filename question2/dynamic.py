#!/usr/bin/python

import argparse
import base64
import hvac
import os
import requests
import subprocess
import urllib3
import mysql.connector #This is for mysql services
from mysql.connector import Error

try:
    import json
except ImportError:
    import simplejson as json

DB_SERVER = os.getenv('dbserver_DB_SERVER', 'http://dbserver')
db_type = 'dbserver'
dummy_VAULT_CREDENTIAL_PATH = 'secret/credentials/dummy/{0}/{1}/current-creds'

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class VaultSession:
    """
    HVAC Vault client context manager for automatically managing interactions with the Vault service.

    Can be invoked as follows:
    with VaultSession() as vault_client:
        # We were automatically logged into a Vault client session, now we can do stuff,
        # read/write secrets, etc using the client.
        # For the available API's see: https://hvac.readthedocs.io/en/v0.6.3/index.html

    """

    def __init__(self, base_url=None, login_token=None, username=None, password=None):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.login_token = login_token

        if self.base_url is None:
            self.base_url = os.getenv('VAULT_ADDRESS', 'http://127.0.0.1:8200')

        if self.username is None:
            self.username = os.getenv('VAULT_USERNAME')

        if self.password is None:
            self.password = os.getenv('VAULT_PASSWORD')

        if self.login_token is None:
            self.login_token = os.getenv('VAULT_LOGIN_TOKEN')

        self.vault_client = hvac.Client(url=self.base_url)

    def __enter__(self):
        if self.login_token is not None:
            self.vault_client.token = self.login_token
        elif self.username is not None and self.password is not None:
            self.vault_client.ldap.login(username=self.username, password=self.password)
        else:
            vault_asset_creds_string = subprocess.check_output([
                'kubectl', 'get', 'secret', '-n', 'dummy', 'vault-asset-credentials', '-o', "json"])

            vault_asset_creds_json = json.loads(vault_asset_creds_string)
            vault_asset_creds = json.loads(base64.b64decode(vault_asset_creds_json["data"]["vault-asset-creds.json"]))

            self.vault_client.ldap.login(username=vault_asset_creds['dummy']['username'],
                                              password=vault_asset_creds['dummy']['password'])

        return self.vault_client

    def __exit__(self, *args):
        pass
class DBServerInventory(object):

    def __init__(self):
        self.inventory = {}
        self.read_cli_args()

        # Called with `--list`.
        if self.args.list:
            self.inventory = self.new_inventory()
        # Called with `--host [hostname]`.
        elif self.args.host:
            # Not implemented, since we return _meta info `--list`.
            self.inventory = self.empty_inventory()
        # If no groups or vars are present, return an empty inventory.
        else:
            self.inventory = self.empty_inventory()
        print(json.dumps(self.inventory))

    def new_inventory(self):
        response = requests.get(DB_SERVER + "/api/assets/" + 'Global',
                                headers={"Accept": "application/json"},
                                verify=False)
        global_configuration = {}
        if response.status_code == 200:
           global_data = response.json()
           global_configuration = global_data['assets'][0]['Shared']

        #FOR MDS ASSET
        # http[s]://HOST:PORT/api/assets/DBServer
        response = requests.get(DB_SERVER + "/api/assets/" + db_type,
                                headers={"Accept": "application/json"},
                                verify=False)

        if response.status_code == 200:
            # hosts and vars
            data = response.json()
            hosts = []
            hostvars = {}

            with VaultSession() as vault_client:
                  vault_token = vault_client.token
            connection = mysql.connector.connect(host=DB_SERVER,
                                         database=db_type,
                                         user=self.username,
                                         password=self.username)
            sql_select_Query = "select * from Laptop"
            cursor = connection.cursor()
            cursor.execute(sql_select_Query)
            records = cursor.fetchall()

            return {
                "DBServer": {
                    'hosts': hosts,
                    'vars': {
                    'records': records
                    }
                },
                '_meta': {
                    'hostvars': hostvars
                }
            }
        # If no groups or vars are present, return an empty inventory.
        else:
            return self.empty_inventory()

    def empty_inventory(self):
        return {'_meta': {'hostvars': {}}}

    # Read the command line args passed to the script.
    def read_cli_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('--list', action='store_true')
        parser.add_argument('--config', action='store_true')
        parser.add_argument('--host', action='store')
        self.args = parser.parse_args()


# Get the inventory.
DBServerInventory()

