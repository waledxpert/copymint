import pytest

from app.application.ethereum.decoders import DecodedMint
from app.application.ethereum.enrichment import enrich_mint
from app.application.ethereum.ports import EvmReceipt, EvmTransaction
from app.domain.enums import MintClassification, MintRoute, TokenStandard


def evidence() -> tuple[DecodedMint, EvmTransaction, EvmReceipt]:
    tx_hash = "0x" + "11" * 32
    collection = "0x" + "22" * 20
    mint = DecodedMint(
        collection_address=collection,
        token_standard=TokenStandard.ERC721,
        token_id=1,
        quantity=1,
        recipient="0x" + "33" * 20,
        operator=None,
        block_number=10,
        block_hash="0x" + "44" * 32,
        transaction_hash=tx_hash,
        log_index=0,
        sub_index=0,
    )
    transaction = EvmTransaction(
        transaction_hash=tx_hash,
        sender="0x" + "55" * 20,
        recipient=collection,
        value_wei=10**18,
        input_data="0x12345678",
        block_number=10,
    )
    receipt = EvmReceipt(tx_hash, 10, mint.block_hash, 1, 100_000, 1_000_000_000)
    return mint, transaction, receipt


def test_enrichment_preserves_facts_and_avoids_premature_classification() -> None:
    mint, transaction, receipt = evidence()
    enriched = enrich_mint(mint, transaction, receipt)
    assert enriched.probable_initiator == transaction.sender
    assert enriched.payer == transaction.sender
    assert enriched.identity_confidence == 85
    assert enriched.route is MintRoute.DIRECT
    assert enriched.classification is MintClassification.UNKNOWN_MINT


def test_known_relayer_remains_unknown_without_trace() -> None:
    mint, transaction, receipt = evidence()
    enriched = enrich_mint(mint, transaction, receipt, known_relayer=True)
    assert enriched.probable_initiator is None
    assert enriched.identity_confidence == 0
    assert enriched.identity_reason_code == "known_relayer_requires_trace"


def test_failed_or_mismatched_transaction_evidence_is_rejected() -> None:
    mint, transaction, receipt = evidence()
    with pytest.raises(ValueError, match="failed transaction"):
        enrich_mint(
            mint,
            transaction,
            EvmReceipt(receipt.transaction_hash, 10, receipt.block_hash, 0, 100, None),
        )
    with pytest.raises(ValueError, match="does not match"):
        enrich_mint(
            mint,
            EvmTransaction(
                "0x" + "ff" * 32,
                transaction.sender,
                transaction.recipient,
                0,
                "0x",
                10,
            ),
            receipt,
        )
