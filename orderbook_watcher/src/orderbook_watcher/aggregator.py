"""
Orderbook aggregation logic across multiple directory nodes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import datetime
from typing import Any

from jmcore.bond_calc import calculate_timelocked_fidelity_bond_value
from jmcore.mempool_api import MempoolAPI
from jmcore.models import FidelityBond, Offer, OrderBook
from loguru import logger

from orderbook_watcher.directory_client import DirectoryClient


class OrderbookAggregator:
    def __init__(
        self,
        directory_nodes: list[tuple[str, int]],
        network: str,
        socks_host: str = "127.0.0.1",
        socks_port: int = 9050,
        timeout: float = 30.0,
        mempool_api_url: str = "https://mempool.space/api",
    ) -> None:
        self.directory_nodes = directory_nodes
        self.network = network
        self.socks_host = socks_host
        self.socks_port = socks_port
        self.timeout = timeout
        self.mempool_api_url = mempool_api_url
        socks_proxy = f"socks5://{socks_host}:{socks_port}"
        logger.info(f"Configuring MempoolAPI with SOCKS proxy: {socks_proxy}")
        # Use longer timeout for SOCKS proxy connections
        mempool_timeout = 60.0
        self.mempool_api = MempoolAPI(
            base_url=mempool_api_url, socks_proxy=socks_proxy, timeout=mempool_timeout
        )

        self._socks_test_task = asyncio.create_task(self._test_socks_connection())
        self.current_orderbook: OrderBook = OrderBook()
        self._lock = asyncio.Lock()
        self.clients: dict[str, DirectoryClient] = {}
        self.listener_tasks: list[asyncio.Task] = []
        self._bond_calculation_task: asyncio.Task[Any] | None = None
        self._bond_queue: asyncio.Queue[OrderBook] = asyncio.Queue()
        self._bond_cache: dict[str, FidelityBond] = {}
        self._last_offers_hash: int = 0
        self._mempool_semaphore = asyncio.Semaphore(5)

    async def fetch_from_directory(
        self, onion_address: str, port: int
    ) -> tuple[list[Offer], list[FidelityBond], str]:
        node_id = f"{onion_address}:{port}"
        client = DirectoryClient(
            onion_address, port, self.network, self.socks_host, self.socks_port, self.timeout
        )
        try:
            await client.connect()
            offers, bonds = await client.fetch_orderbooks()

            for offer in offers:
                offer.directory_node = node_id
            for bond in bonds:
                bond.directory_node = node_id

            return offers, bonds, node_id
        except Exception as e:
            logger.error(f"Failed to fetch from {node_id}: {e}")
            return [], [], node_id
        finally:
            await client.close()

    async def update_orderbook(self) -> OrderBook:
        tasks = [
            self.fetch_from_directory(onion_address, port)
            for onion_address, port in self.directory_nodes
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        new_orderbook = OrderBook(timestamp=datetime.utcnow())

        for result in results:
            if isinstance(result, BaseException):
                logger.error(f"Directory fetch failed: {result}")
                continue

            offers, bonds, node_id = result
            if offers or bonds:
                new_orderbook.add_offers(offers, node_id)
                new_orderbook.add_fidelity_bonds(bonds, node_id)

        await self._calculate_bond_values(new_orderbook)

        async with self._lock:
            self.current_orderbook = new_orderbook

        logger.info(
            f"Updated orderbook: {len(new_orderbook.offers)} offers, "
            f"{len(new_orderbook.fidelity_bonds)} bonds from "
            f"{len(new_orderbook.directory_nodes)} directory nodes"
        )

        return new_orderbook

    async def get_orderbook(self) -> OrderBook:
        async with self._lock:
            return self.current_orderbook

    async def _background_bond_calculator(self) -> None:
        while True:
            try:
                orderbook = await self._bond_queue.get()
                await self._calculate_bond_values(orderbook)
                for offer in orderbook.offers:
                    if offer.fidelity_bond_data:
                        matching_bonds = [
                            b
                            for b in orderbook.fidelity_bonds
                            if b.counterparty == offer.counterparty
                            and b.utxo_txid == offer.fidelity_bond_data.get("utxo_txid")
                        ]
                        if matching_bonds and matching_bonds[0].bond_value is not None:
                            offer.fidelity_bond_value = matching_bonds[0].bond_value
                logger.debug("Background bond calculation completed")
            except Exception as e:
                logger.error(f"Error in background bond calculator: {e}")

    async def start_continuous_listening(self) -> None:
        logger.info("Starting continuous listening on all directory nodes")

        self._bond_calculation_task = asyncio.create_task(self._background_bond_calculator())

        for onion_address, port in self.directory_nodes:
            node_id = f"{onion_address}:{port}"
            client = DirectoryClient(
                onion_address, port, self.network, self.socks_host, self.socks_port, self.timeout
            )

            try:
                await client.connect()
                await client.get_peerlist()

                pubmsg = {
                    "type": 687,
                    "line": f"{client.nick}!PUBLIC!!orderbook",
                }

                if not client.connection:
                    raise RuntimeError("Client not connected")
                await client.connection.send(json.dumps(pubmsg).encode("utf-8"))
                logger.info(f"Initial !orderbook request sent to {node_id}")

                self.clients[node_id] = client

                task = asyncio.create_task(client.listen_continuously())
                self.listener_tasks.append(task)
                logger.info(f"Started listener task for {node_id}")

            except Exception as e:
                logger.error(f"Failed to start listener for {node_id}: {e}")

    async def stop_listening(self) -> None:
        logger.info("Stopping all directory listeners")

        if self._bond_calculation_task:
            self._bond_calculation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._bond_calculation_task

        for client in self.clients.values():
            client.stop()

        for task in self.listener_tasks:
            task.cancel()

        if self.listener_tasks:
            await asyncio.gather(*self.listener_tasks, return_exceptions=True)

        for client in self.clients.values():
            await client.close()

        self.clients.clear()
        self.listener_tasks.clear()

    async def get_live_orderbook(self, calculate_bonds: bool = True) -> OrderBook:
        orderbook = OrderBook(timestamp=datetime.utcnow())

        for node_id, client in self.clients.items():
            offers = client.get_current_offers()
            bonds = client.get_current_bonds()
            for offer in offers:
                offer.directory_node = node_id
            for bond in bonds:
                bond.directory_node = node_id
            orderbook.add_offers(offers, node_id)
            orderbook.add_fidelity_bonds(bonds, node_id)

        unique_bonds: dict[str, FidelityBond] = {}
        for bond in orderbook.fidelity_bonds:
            cache_key = f"{bond.utxo_txid}:{bond.utxo_vout}"
            if cache_key not in unique_bonds:
                unique_bonds[cache_key] = bond
        orderbook.fidelity_bonds = list(unique_bonds.values())

        if calculate_bonds:
            cached_count = 0
            for bond in orderbook.fidelity_bonds:
                cache_key = f"{bond.utxo_txid}:{bond.utxo_vout}"
                if cache_key in self._bond_cache:
                    cached_bond = self._bond_cache[cache_key]
                    bond.bond_value = cached_bond.bond_value
                    bond.amount = cached_bond.amount
                    bond.utxo_confirmation_timestamp = cached_bond.utxo_confirmation_timestamp
                    cached_count += 1

            if cached_count > 0:
                logger.debug(
                    f"Loaded {cached_count}/{len(orderbook.fidelity_bonds)} bonds from cache"
                )

            await self._calculate_bond_values(orderbook)

            for bond in orderbook.fidelity_bonds:
                if bond.bond_value is not None:
                    cache_key = f"{bond.utxo_txid}:{bond.utxo_vout}"
                    self._bond_cache[cache_key] = bond

            for offer in orderbook.offers:
                if offer.fidelity_bond_data:
                    matching_bonds = [
                        b
                        for b in orderbook.fidelity_bonds
                        if b.counterparty == offer.counterparty
                        and b.utxo_txid == offer.fidelity_bond_data.get("utxo_txid")
                    ]
                    if matching_bonds and matching_bonds[0].bond_value is not None:
                        offer.fidelity_bond_value = matching_bonds[0].bond_value

        return orderbook

    async def _calculate_bond_value_single(
        self, bond: FidelityBond, current_time: int
    ) -> FidelityBond:
        if bond.bond_value is not None:
            return bond

        async with self._mempool_semaphore:
            try:
                tx_data = await self.mempool_api.get_transaction(bond.utxo_txid)
                if not tx_data or not tx_data.status.confirmed:
                    logger.debug(f"Bond {bond.utxo_txid}:{bond.utxo_vout} not confirmed")
                    return bond

                if bond.utxo_vout >= len(tx_data.vout):
                    logger.warning(
                        f"Invalid vout {bond.utxo_vout} for tx {bond.utxo_txid} "
                        f"(only {len(tx_data.vout)} outputs)"
                    )
                    return bond

                utxo = tx_data.vout[bond.utxo_vout]
                amount = utxo.value
                confirmation_time = tx_data.status.block_time or current_time

                bond_value = calculate_timelocked_fidelity_bond_value(
                    amount, confirmation_time, bond.locktime, current_time
                )

                bond.bond_value = bond_value
                bond.amount = amount
                bond.utxo_confirmation_timestamp = confirmation_time

                logger.debug(
                    f"Bond {bond.counterparty}: value={bond_value}, "
                    f"amount={amount}, locktime={datetime.utcfromtimestamp(bond.locktime)}, "
                    f"confirmed={datetime.utcfromtimestamp(confirmation_time)}"
                )

            except Exception as e:
                logger.error(f"Failed to calculate bond value for {bond.utxo_txid}: {e}")
                logger.debug(
                    f"Bond data: txid={bond.utxo_txid}, vout={bond.utxo_vout}, amount={bond.amount}"
                )

        return bond

    async def _calculate_bond_values(self, orderbook: OrderBook) -> None:
        current_time = int(datetime.utcnow().timestamp())

        tasks = [
            self._calculate_bond_value_single(bond, current_time)
            for bond in orderbook.fidelity_bonds
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _test_socks_connection(self) -> None:
        """Test SOCKS proxy connection on startup."""
        try:
            success = await self.mempool_api.test_connection()
            if success:
                logger.info("SOCKS proxy connection test successful")
            else:
                logger.warning(
                    "SOCKS proxy connection test failed - bond value calculation may not work"
                )
        except Exception as e:
            logger.error(f"SOCKS proxy connection test error: {e}")
            logger.warning("Bond value calculation may not work without SOCKS proxy")
