import configparser
from tabulate import tabulate
import logging 
import sys
import time
import os
import json
import datetime


from mospy import Account, Transaction
from mospy.clients import HTTPClient
from mospy.utils import seed_to_private_key
from dotenv import load_dotenv

import aiohttp
import asyncio

from web3.auto import w3
from eth_account import Account
from web3 import Web3, HTTPProvider
from eth_defi.abi import get_deployed_contract
from eth_defi.token import fetch_erc20_details
from eth_defi.confirmation import wait_transactions_to_complete

from decimal import Decimal

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

c = configparser.ConfigParser()
c.read("config_testnet.ini", encoding='utf-8')

load_dotenv()
# Load data from config
VERBOSE_MODE          = str(c["DEFAULT"]["verbose"])
DECIMAL               = float(c["CHAIN"]["decimal"])
REST_PROVIDER         = str(c["REST"]["provider"])
RPC_JSON              = str(c["RPC"]["json_rpc"])
MAIN_DENOM            = str(c["CHAIN"]["denomination"])
RPC_PROVIDER          = str(c["RPC"]["provider"])
CHAIN_ID              = str(c["CHAIN"]["id"])
BECH32_HRP            = str(c["CHAIN"]["BECH32_HRP"])
GAS_PRICE             = int(c["TX"]["gas_price"])
GAS_LIMIT             = int(c["TX"]["gas_limit"])
FAUCET_PRIVKEY        = os.getenv("PRIVATE_KEY")
FAUCET_SEED           = os.getenv("FAUCET_SEED")
if FAUCET_PRIVKEY == "":
    FAUCET_PRIVKEY = str(seed_to_private_key(FAUCET_SEED).hex())

FAUCET_ADDRESS    = str(c["FAUCET"]["faucet_address"])
FORGE_BOT_ADDRESS = str(c["ERC20"]["token_faucet_address"])
FORGE_BOT_PK      = os.getenv("UNI_V3_FAUCET")
EXPLORER_URL      = str(c["OPTIONAL"]["explorer_url"])

EIP20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"name":"_from","type":"address"},{"indexed":true,"name":"_to","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"_owner","type":"address"},{"indexed":true,"name":"_spender","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Approval","type":"event"}]')  # noqa: 501


token_from = "0x38d4819e935FF05B422820952BA0C993e84fC4B6"
token_to = "0x0286fFC971136854cccCb6Bbb4B5AD023C43bf48"
token_to_private_key = "588fbe82040bf232a30ff3e5dbe42dc8aab630871463742c674fc8528545125e"

ERC_20_TOKEN_ADDRESS = "0xA83C23914Ab58B4A19C510f1A46FFB4fFcDa3c95"

account = w3.eth.account.from_key(token_to_private_key)

web3 = Web3(HTTPProvider(RPC_JSON))
print(f"Connected to blockchain, chain id is {web3.eth.chain_id}. the latest block is {web3.eth.block_number:,}")

#token_contract = web3.eth.contract(abi=EIP20_ABI, address=ERC_20_TOKEN_ADDRESS)
token_details = fetch_erc20_details(web3, ERC_20_TOKEN_ADDRESS)
erc_20 = get_deployed_contract(web3, "ERC20MockDecimals.json", ERC_20_TOKEN_ADDRESS)
balance = erc_20.functions.balanceOf(account.address).call()
eth_balance = web3.eth.getBalance(account.address)
print(f"Your balance is: {token_details.convert_to_decimals(balance)} {token_details.symbol}")
print(f"Your have {eth_balance/(10**18)} ETH for gas fees")


contract = web3.eth.contract(address=ERC_20_TOKEN_ADDRESS, abi=EIP20_ABI)
print(type(token_to))
abi_data = contract.encodeABI(fn_name='transfer', args=[token_to, 10000000000000000000])
nonce = web3.eth.get_transaction_count(token_from)  
tx = {
    'from': token_from,
    'to': contract.address,
    'nonce': nonce,
    'gas': 70000,
    'gasPrice': w3.toWei('1', 'gwei'),
    'data': contract.encodeABI(fn_name='transfer', args=[token_to, 10000000000000000000]),
    'chainId': 9000
}

signed_tx = web3.eth.account.signTransaction(tx, token_to_private_key)
tx_hash = web3.eth.sendRawTransaction(signed_tx.rawTransaction)

print(tx_hash.hex())