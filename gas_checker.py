import threading
import time

from web3 import Web3
from settings import CHECK_GWEI, MAX_GWEI, ETHEREUM_RPC
from loguru import logger


last_check = None
last_gas = None
lock = threading.Lock()


def get_gas():
    try:
        w3 = Web3(Web3.HTTPProvider(ETHEREUM_RPC))
        gas_price = w3.eth.gas_price
        gwei = w3.from_wei(gas_price, "gwei")
        return gwei
    except Exception as error:
        logger.error(error)
    return float("inf")


def wait_gas():
    global last_check, last_gas

    if not CHECK_GWEI:
        return

    with lock:
        while True:
            if last_check is not None and time.time() - last_check < 60:
                if last_gas <= MAX_GWEI:
                    return
                continue

            gas = get_gas()

            last_check = time.time()
            last_gas = gas

            if last_gas <= MAX_GWEI:
                return

            logger.info(f"Current GWEI: {gas} > {MAX_GWEI}")
            time.sleep(60)
