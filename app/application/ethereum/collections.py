"""Ethereum collection validation and deployment-boundary discovery."""

from dataclasses import dataclass

from web3 import Web3

from app.application.ethereum.ports import EvmProvider
from app.domain.enums import DeploymentConfidence


class InvalidCollection(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CollectionProbe:
    normalized_address: str
    checksum_address: str
    deployment_block_number: int
    deployment_block_hash: str
    deployment_confidence: DeploymentConfidence
    deployment_confidence_value: int


class EthereumCollectionDiscovery:
    def __init__(self, provider: EvmProvider, *, chain_id: int = 1) -> None:
        self._provider = provider
        self._chain_id = chain_id

    async def verify_chain(self) -> None:
        actual = await self._provider.chain_id()
        if actual != self._chain_id:
            raise RuntimeError(
                f"Ethereum provider chain mismatch: expected {self._chain_id}, received {actual}"
            )

    async def probe(self, address: str) -> CollectionProbe:
        if not Web3.is_address(address):
            raise InvalidCollection("collection address is not a valid Ethereum address")
        checksum = Web3.to_checksum_address(address)
        await self.verify_chain()
        finalized = await self._provider.block("finalized")
        if not await self._provider.code(checksum, finalized.number):
            raise InvalidCollection("address has no contract code at the finalized boundary")
        low = 0
        high = finalized.number
        while low < high:
            middle = (low + high) // 2
            if await self._provider.code(checksum, middle):
                high = middle
            else:
                low = middle + 1
        deployment = await self._provider.block(low)
        return CollectionProbe(
            normalized_address=checksum.lower(),
            checksum_address=checksum,
            deployment_block_number=deployment.number,
            deployment_block_hash=deployment.block_hash,
            deployment_confidence=DeploymentConfidence.EXACT,
            deployment_confidence_value=100,
        )
