import configparser
from tabulate import tabulate
import logging 
import sys
import time
import os
import json

from mospy import Account, Transaction
from mospy.clients import HTTPClient
from mospy.utils import seed_to_private_key
from dotenv import load_dotenv

import aiohttp
import asyncio

from web3.auto import w3
from eth_account import Account as ethAccount
from web3 import Web3, HTTPProvider
from eth_defi.abi import get_deployed_contract
from eth_defi.token import fetch_erc20_details
from eth_defi.confirmation import wait_transactions_to_complete

from decimal import Decimal


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(formatter)

logger.addHandler(stream_handler)

def get_logger():

    return logger
    
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


##ERC20
ERC20_FAUCET          = str(c["ERC20"]["token_faucet_address"])
ERC20_FAUCET_PK       = os.getenv("ERC20_FAUCET_PK")

EXPLORER_URL      = str(c["OPTIONAL"]["explorer_url"])


EIP20_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"anonymous":false,"inputs":[{"indexed":true,"name":"_from","type":"address"},{"indexed":true,"name":"_to","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"_owner","type":"address"},{"indexed":true,"name":"_spender","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Approval","type":"event"}]')  # noqa: 501

faucet_account = Account(
    seed_phrase=FAUCET_SEED,
    hrp="evmos",
    slip44=60,
    eth=True,
)
print(FAUCET_SEED)
logger.info(f"faucet address {faucet_account.address} initialized")


def coins_dict_to_string(coins: dict, table_fmt_: str = "") -> str:
    headers = ["Token", "Amount"]
    hm = []
    """
    :param table_fmt_: grid | pipe | html
    :param coins: {'clink': '100000000000000000000', 'chot': '100000000000000000000'}
    :return: str
    """
    for i in coins:
        hm.append([i, coins[i]])
    d = tabulate(hm, tablefmt=table_fmt_, headers=headers)
    return d

async def async_request(session, url, data: str = ""):
    headers = {"Content-Type": "application/json"}
    try:
        if data == "":
            async with session.get(url=url, headers=headers) as resp:
                data = await resp.text()
        else:
            async with session.post(url=url, data=data, headers=headers) as resp:
                data = await resp.text()

        if type(data) is None or "error" in data:
            return await resp.text()
        else:
            return await resp.json()

    except Exception as err:
        return f'error: in async_request()\n{url} {err}'

async def get_addr_evmos_balance(session, addr: str, denom: str):
    d = ""
    coins = {}
    try:
        d = await async_request(session, url=f'{REST_PROVIDER}/cosmos/bank/v1beta1/balances/{addr}/by_denom?denom={denom}')
        if "balance" in str(d):
            return await aevmos_to_evmos(d["balance"]["amount"])
        else:
            return 0
    except Exception as addr_balancer_err:
        logger.error("not able to query balance", d, addr_balancer_err)

async def get_address_info(session, addr: str):
    try:
        """:returns sequence: int, account_number: int, coins: dict"""
        d = await async_request(session, url=f'{REST_PROVIDER}/cosmos/auth/v1beta1/accounts/{addr}')

        acc_num = int(d['account']['base_account']['account_number'])
        try:
            seq = int(d['account']['base_account']['sequence']) or 0
            
        except:
            seq = 0
        logger.info(f"faucet address {addr} is on sequence {seq}")
        return seq, acc_num

    except Exception as address_info_err:
        if VERBOSE_MODE == "yes":
            logger.error(address_info_err)
        return 0, 0


async def get_node_status(session):
    url = f'{RPC_PROVIDER}/status'
    return await async_request(session, url=url)


async def get_transaction_info(session, trans_id_hex: str):
    url = f'{REST_PROVIDER}/cosmos/tx/v1beta1/txs/{trans_id_hex}'
    time.sleep(6)
    resp = await async_request(session, url=url)
    if 'height' in str(resp):
        return resp
    else:
        return f"error: {trans_id_hex} not found"


async def send_tx(session, recipient: str, amount: int) -> str:
    url_ = f'{REST_PROVIDER}/cosmos/tx/v1beta1/txs'
    try:
        faucet_account.next_sequence, faucet_account.account_number = await get_address_info(session, FAUCET_ADDRESS)
        
        tx = Transaction(
            account=faucet_account,
            gas=GAS_LIMIT,
            memo="Trade on forge.trade - a UniV3 fork on Evmos.",
            chain_id=CHAIN_ID,
        )

        tx.set_fee(
        denom="atevmos",
        amount=GAS_PRICE
        )

        tx.add_msg(
            tx_type="transfer",
            sender=faucet_account,
            receipient=recipient,
            amount=amount,
            denom=MAIN_DENOM,
        )

        client = HTTPClient(api=REST_PROVIDER)
        tx_response =  client.broadcast_transaction(transaction=tx)
        logger.info(tx_response)
        return tx_response

    except Exception as reqErrs:
        if VERBOSE_MODE == "yes":
            print(f'error in send_txs() {REST_PROVIDER}: {reqErrs}')
        return f"error: {reqErrs}"

async def aevmos_to_evmos(aevmos):
    logger.info("hey")
    aevmos_ = float(aevmos)
    amount_evmos = aevmos_/DECIMAL
    logger.info(f"Converted {aevmos_} atevmos to tevmos {amount_evmos}")
    return f'{amount_evmos}'

async def send_erc20_tokens(session, recipient, erc_address, amount):
    web3 = Web3(HTTPProvider(RPC_JSON))
    logger.info(f"Connected to blockchain, chain id is {web3.eth.chain_id}. the latest block is {web3.eth.block_number:,}")

    
    token_details = fetch_erc20_details(web3, erc_address)
    erc_20 = get_deployed_contract(web3, "ERC20MockDecimals.json", erc_address)
    balance = erc_20.functions.balanceOf(ERC20_FAUCET).call()
    eth_balance = web3.eth.getBalance(ERC20_FAUCET)

    
    logger.info(f"Your balance is: {token_details.convert_to_decimals(balance)} {token_details.symbol}")
    logger.info(f"Faucet has {eth_balance/(10**18)} TEVMOS for gas fees")
    
    contract = web3.eth.contract(address=erc_address, abi=EIP20_ABI)
    

    logger.info("preparing unsigned info")
    amount = int(amount)

    nonce = web3.eth.get_transaction_count(ERC20_FAUCET)  
    reciepeint_checksum = Web3.toChecksumAddress(recipient)
    abi_data = contract.encodeABI(fn_name='transfer', args=[reciepeint_checksum, amount])
    
    tx = {
        'from': ERC20_FAUCET,
        'to': contract.address,
        'nonce': nonce,
        'gas': 70000,
        'gasPrice': w3.toWei('1', 'gwei'),
        'data': abi_data,
        'chainId': 9000
    }


    signed_tx = web3.eth.account.signTransaction(tx, ERC20_FAUCET_PK)
    tx_hash = web3.eth.sendRawTransaction(signed_tx.rawTransaction)
    logger.info("tx signed and executed")
    logger.info("Waiting to confirm " + tx_hash.hex())
    time.sleep(5)
    return session