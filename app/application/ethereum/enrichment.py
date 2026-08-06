"""Conservative factual identity and route enrichment."""

from dataclasses import dataclass

from web3 import Web3

from app.application.ethereum.classification import SaleStateEvidence, classify_mint
from app.application.ethereum.decoders import DecodedMint
from app.application.ethereum.ports import EvmReceipt, EvmTransaction
from app.domain.enums import MintClassification, MintRoute


@dataclass(frozen=True, slots=True)
class EnrichedMint:
    mint: DecodedMint
    transaction_sender: str
    payer: str | None
    probable_initiator: str | None
    identity_confidence: int
    identity_reason_code: str
    route: MintRoute
    classification: MintClassification
    classification_reason_code: str


def enrich_mint(
    mint: DecodedMint,
    transaction: EvmTransaction,
    receipt: EvmReceipt,
    *,
    known_relayer: bool = False,
    sale_state: SaleStateEvidence | None = None,
) -> EnrichedMint:
    if receipt.status != 1:
        raise ValueError("failed transaction cannot produce a canonical mint")
    if transaction.transaction_hash.lower() != mint.transaction_hash.lower():
        raise ValueError("transaction evidence does not match mint provenance")
    if receipt.transaction_hash.lower() != mint.transaction_hash.lower():
        raise ValueError("receipt evidence does not match mint provenance")
    if transaction.block_number != mint.block_number or receipt.block_number != mint.block_number:
        raise ValueError("transaction block does not match mint provenance")
    if receipt.block_hash.lower() != mint.block_hash.lower():
        raise ValueError("receipt block hash does not match mint provenance")
    sender = Web3.to_checksum_address(transaction.sender)
    payer = sender if transaction.value_wei > 0 else None
    direct = (
        transaction.recipient is not None
        and transaction.recipient.lower() == mint.collection_address.lower()
    )
    if known_relayer:
        initiator = None
        confidence = 0
        identity_reason = "known_relayer_requires_trace"
    elif not direct:
        initiator = None
        confidence = 0
        identity_reason = "indirect_call_requires_trace"
    else:
        initiator = sender
        confidence = 85
        identity_reason = "direct_transaction_sender"
    decision = classify_mint(sale_state)
    route = decision.route
    if sale_state is None:
        route = MintRoute.DIRECT if direct else MintRoute.UNKNOWN
    return EnrichedMint(
        mint=mint,
        transaction_sender=sender,
        payer=payer,
        probable_initiator=initiator,
        identity_confidence=confidence,
        identity_reason_code=identity_reason,
        route=route,
        classification=decision.classification,
        classification_reason_code=decision.reason_code,
    )
