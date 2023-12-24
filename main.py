from concurrent.futures import ThreadPoolExecutor
import json
import random
import threading
import requests
import time
import traceback

from web3 import Web3
from web3.exceptions import TransactionNotFound
from loguru import logger
from gas_checker import wait_gas
from settings import (
    SCROLL_RPC,
    MIN_SLEEP,
    MAX_SLEEP,
    SHUFFLE_ACCOUNTS,
    CHECK_GWEI,
    THREADS,
)


class Minter:
    def __init__(self, private_key):
        self.w3 = Web3(Web3.HTTPProvider(SCROLL_RPC))
        self.explorer = "https://scrollscan.com/tx/"

        abi = json.load(open("abi.json"))
        self.mint_cotract = self.w3.eth.contract(
            address="0x74670A3998d9d6622E32D0847fF5977c37E0eC91", abi=abi
        )

        self.private_key = private_key
        self.address = self.w3.eth.account.from_key(private_key).address

    def check_eligibility(self):
        response = requests.get(
            f"https://nft.scroll.io/p/{self.address}.json",
            params={"timestamp": int(time.time())},
        )

        if not response.json():
            logger.error(f"{self.address} not eligible to mint")
            return None

        rarity_data = response.json()["metadata"]["rarityData"]
        if rarity_data.startswith("0x7c"):
            rarity = "Rare"
        elif rarity_data.startswith("0x25"):
            rarity = "Common"
        else:
            rarity = "Legendary"
        logger.success(f"{self.address} is eligible to mint {rarity} NFT")

        return response

    def mint(self):
        try:
            response = self.check_eligibility()
            if not response:
                return False

            meta = tuple(response.json()["metadata"].values())
            mod_tuple = meta[:-1] + (int(meta[-1], 16),)
            proof = response.json()["proof"]

            tx_data = {
                "chainId": self.w3.eth.chain_id,
                "value": 0,
                "from": self.address,
                "gasPrice": self.w3.eth.gas_price,
                "nonce": self.w3.eth.get_transaction_count(self.address),
            }

            tx = self.mint_cotract.functions.mint(
                self.address, mod_tuple, proof
            ).build_transaction(tx_data)

            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)

            if CHECK_GWEI:
                wait_gas()

            signed_tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

            self.wait_until_tx_finished(signed_tx_hash.hex())
            return True
        except Exception as err:
            traceback.print_exc()
            logger.error(f"[{self.address}] ERROR | {err}")
        return False

    def wait_until_tx_finished(self, hash: str, max_wait_time=180) -> None:
        start_time = time.time()
        while True:
            try:
                receipts = self.w3.eth.get_transaction_receipt(hash)
                status = receipts.get("status")
                if status == 1:
                    logger.success(
                        f"[{self.address}] {self.explorer}{hash} successfully!"
                    )
                    return True
                elif status is None:
                    time.sleep(0.3)
                else:
                    logger.error(
                        f"[{self.address}] {self.explorer}{hash} transaction failed!"
                    )
                    return False
            except TransactionNotFound:
                if time.time() - start_time > max_wait_time:
                    logger.error(f"FAILED TX: {hash}")
                    return False
                time.sleep(1)


def run_thread_group(thread_group: list, mode: str):
    for account in thread_group:
        minter = Minter(account)
        logger.info(f"Starting {minter.address}")
        if mode == "1" and CHECK_GWEI:
            wait_gas()

        function = minter.check_eligibility if mode == "2" else minter.mint
        if function() and mode == "1":
            sleep_time = random.randint(MIN_SLEEP, MAX_SLEEP)
            logger.info(f"Sleeping for {sleep_time} seconds")
            time.sleep(sleep_time)


def main(accounts: list):
    global THREADS

    if THREADS > len(accounts):
        THREADS = len(accounts)

    total_accounts = len(accounts)
    group_size = total_accounts // THREADS
    remainder = total_accounts % THREADS

    groups = []
    start = 0
    for i in range(THREADS):
        # Add an extra account to some groups to distribute the remainder
        end = start + group_size + (1 if i < remainder else 0)
        groups.append(accounts[start:end])
        start = end

    threads = []

    mode = input("Enter 1 to Mint, 2 to check eligibility: ")

    for thread_group in groups:
        t = threading.Thread(
            target=run_thread_group,
            kwargs={"thread_group": thread_group, "mode": mode},
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()


if __name__ == "__main__":
    with open("accounts.txt", "r") as f:
        ACCOUNTS = [row.strip() for row in f if row.strip()]

        if SHUFFLE_ACCOUNTS:
            random.shuffle(ACCOUNTS)

    main(ACCOUNTS)
