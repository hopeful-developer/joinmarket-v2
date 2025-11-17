"""
Fidelity bond validation using mempool.space API.
"""

from __future__ import annotations

import asyncio

from jmcore.mempool_api import MempoolAPI
from jmcore.models import FidelityBond
from loguru import logger


class BondValidator:
    def __init__(self, mempool_api_url: str, socks_proxy: str | None = None) -> None:
        self.mempool_api = MempoolAPI(base_url=mempool_api_url, socks_proxy=socks_proxy)

    async def close(self) -> None:
        await self.mempool_api.close()

    async def validate_bond(self, bond: FidelityBond) -> bool:
        try:
            confirmations = await self.mempool_api.get_utxo_confirmations(
                bond.utxo_txid, bond.utxo_vout
            )
            if confirmations is None:
                logger.warning(
                    f"Could not get confirmations for bond {bond.counterparty} "
                    f"UTXO {bond.utxo_txid}:{bond.utxo_vout}"
                )
                return False

            if confirmations < 1:
                logger.warning(
                    f"Bond {bond.counterparty} UTXO {bond.utxo_txid}:{bond.utxo_vout} "
                    f"is unconfirmed"
                )
                return False

            value = await self.mempool_api.get_utxo_value(bond.utxo_txid, bond.utxo_vout)
            if value is None:
                logger.warning(
                    f"Could not get value for bond {bond.counterparty} "
                    f"UTXO {bond.utxo_txid}:{bond.utxo_vout}"
                )
                return False

            if value != bond.amount:
                logger.warning(
                    f"Bond {bond.counterparty} value mismatch: expected {bond.amount}, got {value}"
                )
                return False

            logger.debug(
                f"Validated bond {bond.counterparty} UTXO {bond.utxo_txid}:{bond.utxo_vout}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to validate bond {bond.counterparty}: {e}")
            return False

    async def validate_bonds(self, bonds: list[FidelityBond]) -> list[FidelityBond]:
        tasks = [self.validate_bond(bond) for bond in bonds]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_bonds = []
        for bond, result in zip(bonds, results, strict=False):
            if isinstance(result, Exception):
                logger.error(f"Bond validation failed for {bond.counterparty}: {result}")
                continue
            if result:
                valid_bonds.append(bond)

        logger.info(f"Validated {len(valid_bonds)}/{len(bonds)} fidelity bonds")
        return valid_bonds
