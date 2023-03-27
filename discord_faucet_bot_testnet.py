from asyncio import sleep
from unittest.main import MAIN_EXAMPLES
import aiofiles as aiof
import aiohttp
import discord
import configparser
import datetime
import time
import sys
import cosmos_api_testnet as api
import evmospy.pyevmosaddressconverter as converter
import json
import os
from discord.ext import commands
import discord_faucet_bot_testnet

from dotenv import load_dotenv
load_dotenv()

# Turn Down Discord Logging


# Configure Logging

logger = api.get_logger()

# Load config
c = configparser.ConfigParser()
c.read("config_testnet.ini")
FAUCET_EMOJI = "🚰"

VERBOSE_MODE                = str(c["DEFAULT"]["verbose"])
BECH32_HRP                  = str(c["CHAIN"]["BECH32_HRP"])
MAIN_DENOM                  = str(c["CHAIN"]["denomination"])
DECIMAL                     = float(c["CHAIN"]["decimal"])
DENOMINATION_LST            = c["TX"]["denomination_list"].split(",")
AMOUNT_TO_SEND              = c["TX"]["amount_to_send"]
FAUCET_ADDRESS              = str(c["FAUCET"]["faucet_address"])
EXPLORER_URL                = str(c["OPTIONAL"]["explorer_url"])
if EXPLORER_URL             != "":
    EXPLORER_URL            = f'{EXPLORER_URL}'
REQUEST_TIMEOUT             = int(c["FAUCET"]["request_timeout"])
TOKEN                       = os.getenv("TOKEN")
CHANNEL                     = str(c["FAUCET"]["channels_to_listen"])

ERC20_AMOUNT_TO_SEND        = str(c["ERC20"]["erc20_token_to_send"])
TOKENS_TO_SEND = {
    'ETH': ["0x43bDe47a34801f6aB2d66016Aef723Ba1b3A62b3", 100000000000000000000, 18],
    'USDC': ["0xBf6942D20D1460334B9b147199c4f03c97b70d02", 180000000, 6],   
    'LFG': ["0xE7bbbEE8Fc04F93d5D07029754D2345684A9a28B", 800000000000000000000, 18],
    }
APPROVE_EMOJI = "✅"
REJECT_EMOJI = "🚫"
ACTIVE_REQUESTS = {}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(intents=discord.Intents.all() , command_prefix= "$" , description='Funded by the community for the community')

with open("info-msg-testnet.txt", "r", encoding="utf-8") as help_file:
    help_msg = help_file.read()


##FUNCTION
async def save_transaction_statistics(some_string: str):
    # with open("transactions.csv", "a") as csv_file:
    async with aiof.open("transactions.csv", "a") as csv_file:
        await csv_file.write(f'{some_string}\n')
        await csv_file.flush()


async def submit_tx_info(session, message, requester, txhash = ""):
    if message.content.startswith('$tx_info') and txhash == "":
        txhash = str(message.content).replace("$tx_info", "").replace(" ", "")
    try:
        if len(txhash) == 64:

            tx = await api.get_transaction_info(session, txhash)
            logger.info(f"requested txhash {txhash} details")
            if "amount" and "fee" in str(tx):
                from_   = tx['tx']['body']['messages'][0]['from_address']
                to_     = tx['tx']['body']['messages'][0]['to_address']
                amount_ = tx['tx']['body']['messages'][0]['amount'][0]['amount']

                tx = f'🚀 - {requester}\n' \
                    f'{await api.aevmos_to_evmos(amount_)} TESTNET Evmos successfully transfered to {to_}' \
                    '```' \
                    f'From:         {from_}\n' \
                    f'To (BECH32):  {to_}\n' \
                    f'To (HEX):     {converter.evmos_to_eth(to_)}\n' \
                    f'Amount:       {await api.aevmos_to_evmos(amount_)} TESTNET Evmos ```' \
                    f'{EXPLORER_URL}/txs/{txhash}'

                await message.channel.send(tx)
                await session.close()
            else:
                await message.channel.send(f'{requester}, `{tx}`')
                await session.close()
        else:
            await message.channel.send(f'Incorrect length for tx_hash: {len(txhash)} instead 64')
            await session.close()

    except Exception as e: 
            logger.error(f"Can't get transaction info {e}")
            await message.channel.send(f"Can't get transaction info of your request {message.content}")
    

async def eval_transaction(session, ctx, transaction):
    if "'code': 0" in str(transaction) and "hash" in str(transaction):
        await submit_tx_info(session, ctx.message, ctx.author.mention ,transaction["hash"])
        logger.info("successfully send tx info to discord")

    else:
        await ctx.send(
            f'{REJECT_EMOJI} - {ctx.author.mention}, Can\'t send transaction. Try making another request'
            f'\n{transaction}'
            )
        logger.error(f"Couldn't process tx {transaction}")
            
    now = datetime.datetime.now()
    await save_transaction_statistics(f'{transaction};{now.strftime("%Y-%m-%d %H:%M:%S")}')
    await session.close()

async def requester_basic_requirements(session, ctx, address, amount):
    faucet_address_length = len(FAUCET_ADDRESS)
    if len(address) != faucet_address_length or address[:len(BECH32_HRP)] != BECH32_HRP:
        await ctx.send(
            f'{ctx.author.mention}, Invalid address format `{address}`\n'
            f'Address must be in BECH32 "evmos1zwr06uz8vrwkcnd05e5yddamvghn93a467tf0q" or HEX "0x1386fD704760dd6C4DAfa66846b7BB622F32C7b5"'
            )
        return False

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')

@bot.event
async def on_message(message):
    # Check if the message was sent in a specific channel
    logger.info(f'message from channel {message.channel.name}')
    logger.info(CHANNEL)
    if CHANNEL in message.channel.name:
        # Handle the message here
        await bot.process_commands(message)
    else: 
        logger.info(f"request came from {message.channel.name} but this bots only listens to {CHANNEL}")
        return

@bot.event
async def on_command_error(ctx, error):
	if isinstance(error, commands.CommandOnCooldown):
		await ctx.send(
            f'{REJECT_EMOJI} - {ctx.author.mention}\n'
            f'You already executed the request command. As a security measure, users can only execute this command all {error.cooldown.per/60} minutes. \n'
            f'Please retry in {round((error.retry_after/60), 0)} minutes.'
            )

@bot.command(name='balance')
async def balance(ctx):
    session = aiohttp.ClientSession()
    address = str(ctx.message.content).replace("$balance", "").replace(" ", "").lower()
    if address.startswith("0x") and len(address)== 42: 
        address = converter.eth_to_evmos(address)

    if address[:len(BECH32_HRP)] == BECH32_HRP:
        amount = await api.get_addr_evmos_balance(session, address, MAIN_DENOM)
        if float(amount) > 0:
            await ctx.channel.send(
                f'⚖️ - {ctx.author.mention}\nYour current Evmos balance\n'
                f'```{api.coins_dict_to_string({"TEVMOS": amount}, "grid")}```\n'
                f'Additionally, you can check your token balance on the block explorer: {EXPLORER_URL}/account/{address}')
            await session.close()

        else:
            await ctx.channel.send(f'{ctx.author.mention} your account is not initialized with evmos (balance is empty)')
            await session.close()

@bot.command(name='info')
async def info(ctx):
    session = aiohttp.ClientSession()
    await ctx.send(help_msg)
    await session.close()


@bot.command(name='faucet_status')
async def status(ctx):
    session = aiohttp.ClientSession()
    logger.info(f"status request by {ctx.author.name}")
    balance = await api.get_addr_evmos_balance(session, FAUCET_ADDRESS, MAIN_DENOM )
    try:
        s = await api.get_node_status(session)
        if "node_info" in str(s) and "error" not in str(s):
            s = f'```' \
                        f'Moniker:       {s["result"]["node_info"]["moniker"]}\n' \
                        f'Address:       {FAUCET_ADDRESS}\n' \
                        f'OutOfSync:     {s["result"]["sync_info"]["catching_up"]}\n' \
                        f'Last block:    {s["result"]["sync_info"]["latest_block_height"]}\n' \
                        f'Faucet balance: {balance} {DENOMINATION_LST}```'
            await ctx.send(s)
            await session.close()
    except Exception as statusErr:
        logger.error(statusErr)


@bot.command(name='faucet_address')
async def faucet_address(ctx):
    session = aiohttp.ClientSession()
    try:
        await ctx.send(
            f'{FAUCET_EMOJI} - **Bot address** \n \n'
            f'The bots active address is: \n'
            f'`{FAUCET_ADDRESS}`\n \n'
        )         
        await session.close()
    except:
        logger.error("Can't send message $faucet_address. Please report the incident to one of the mods.")

@bot.command(name='tx_info')
async def tx_info(ctx):
    session = aiohttp.ClientSession()
    await submit_tx_info(session, ctx.message, ctx.author.mention)

@commands.cooldown(1, REQUEST_TIMEOUT, commands.BucketType.user)
@bot.command(name='request')
async def request(ctx):
    session = aiohttp.ClientSession()
    requester_address = str(ctx.message.content).replace("$request", "").replace(" ", "").lower()
    if requester_address.startswith("0x") and len(requester_address)== 42: 
        requester_address = converter.eth_to_evmos(requester_address)

    #do basic requirements
    basic_checks = await requester_basic_requirements(session, ctx, requester_address, AMOUNT_TO_SEND)
    if basic_checks == False:
        return

    #send and evaluate tx
    transaction = await api.send_tx(session, recipient=requester_address, amount=AMOUNT_TO_SEND)
    await eval_transaction (session, ctx, transaction)

@commands.cooldown(1, REQUEST_TIMEOUT, commands.BucketType.user)
@bot.command(name='forge')
async def request(ctx):
    session = aiohttp.ClientSession()
    requester_address = str(ctx.message.content).replace("$forge", "").replace(" ", "").lower()

    if requester_address.startswith("0x") and len(requester_address)== 42:
        try:
          await ctx.send(
            f'Gm {ctx.author.mention} 🫡 \nI will send you a couple of ERC-20 tokens to test out Forge! Give me 30 seconds. I have to do multiple transactions... \n\n' \
            )         
        except:
            logger.error("Something is broken. Report this incident.")
            await session.close()
    else: 
        await ctx.send(
        f'Uh-oh, you are ngmi. ForgeDEX only works with Metamask. Submit a Metamask generated HEX address (e.g. 0x38d4819e935FF05B422820952BA0C993e84fC4B6)'
        )         
        await session.close()
    try: 
        #START FINAL REPLY
        string_to_send = f"\n{ctx.author.mention} \nSent tokens to {requester_address}\n"
        #TEVMOS
        requester_address_bech32 = converter.eth_to_evmos(requester_address)
        transaction = await api.send_tx(session, recipient=requester_address_bech32, amount=AMOUNT_TO_SEND)
        if "'code': 0" not in str(transaction) and "hash" in str(transaction):
            raise Exception("Couldn't send TEVMOS")
        amount = int(int(AMOUNT_TO_SEND) / 10**18)
        partial_response = f"💧 {amount} TEVMOS [native]\n"
        string_to_send += partial_response
        logger.info("TEVMOS sent. Waiting to confirm...")
        #TOKENS
        for t in TOKENS_TO_SEND:
            token_data = TOKENS_TO_SEND[t]
            decimals = token_data[2]
            address = token_data[0]
            amount = int(token_data[1] / 10**decimals)
            partial_response = f"💧 {amount} {t} tokens [{address}]\n"
            string_to_send += partial_response
            session = await api.send_erc20_tokens(session, requester_address, address , token_data[1])

    
        end_string = "\nTrade your assets on https://testnet.forge.trade [TESTNET ONLY] 🔥"
        string_to_send += end_string
        await ctx.send(
        string_to_send
        )         
        await session.close()
    except Exception as e: 
        await ctx.send(
        f'Uh-oh, you are ngmi. Something went wrong. Try again.\n' \
        f'Err log: {e}'
        )
        logger.error(f"couldn't send tokens {e}")
        await session.close()
bot.run(TOKEN)
