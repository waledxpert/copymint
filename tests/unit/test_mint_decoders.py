from eth_abi.abi import encode

from app.application.ethereum.decoders import (
    ERC721_TRANSFER_TOPIC,
    ERC1155_BATCH_TOPIC,
    ERC1155_SINGLE_TOPIC,
    ERC2309_CONSECUTIVE_TOPIC,
    ConsecutiveRangeTooLarge,
    decode_mint_log,
)
from app.application.ethereum.ports import EvmLog
from app.domain.enums import TokenStandard

ZERO_TOPIC = "0x" + "00" * 32
RECIPIENT = "0x" + "11" * 20
OPERATOR = "0x" + "22" * 20


def address_topic(address: str) -> str:
    return "0x" + "00" * 12 + address.removeprefix("0x")


def uint_topic(value: int) -> str:
    return "0x" + value.to_bytes(32, "big").hex()


def log(*, topic: str, topics: tuple[str, ...], data: bytes = b"") -> EvmLog:
    return EvmLog(
        address="0x" + "33" * 20,
        topics=(topic, *topics),
        data="0x" + data.hex(),
        block_number=100,
        block_hash="0x" + "44" * 32,
        transaction_hash="0x" + "55" * 32,
        log_index=3,
        removed=False,
    )


def test_decodes_erc721_and_erc1155_single_mints() -> None:
    erc721 = decode_mint_log(
        log(
            topic=ERC721_TRANSFER_TOPIC,
            topics=(ZERO_TOPIC, address_topic(RECIPIENT), uint_topic(9)),
        )
    )
    assert [(event.token_standard, event.token_id, event.quantity) for event in erc721] == [
        (TokenStandard.ERC721, 9, 1)
    ]

    single = decode_mint_log(
        log(
            topic=ERC1155_SINGLE_TOPIC,
            topics=(address_topic(OPERATOR), ZERO_TOPIC, address_topic(RECIPIENT)),
            data=encode(["uint256", "uint256"], [12, 4]),
        )
    )
    assert [(event.token_id, event.quantity, event.sub_index) for event in single] == [(12, 4, 0)]


def test_erc1155_batch_expansion_has_deterministic_sub_indexes() -> None:
    events = decode_mint_log(
        log(
            topic=ERC1155_BATCH_TOPIC,
            topics=(address_topic(OPERATOR), ZERO_TOPIC, address_topic(RECIPIENT)),
            data=encode(["uint256[]", "uint256[]"], [[8, 2, 5], [1, 3, 2]]),
        )
    )
    assert [(event.token_id, event.quantity, event.sub_index) for event in events] == [
        (8, 1, 0),
        (2, 3, 1),
        (5, 2, 2),
    ]


def test_erc2309_expands_bounded_range_and_rejects_excess() -> None:
    event = log(
        topic=ERC2309_CONSECUTIVE_TOPIC,
        topics=(uint_topic(40), ZERO_TOPIC, address_topic(RECIPIENT)),
        data=encode(["uint256"], [42]),
    )
    decoded = decode_mint_log(event)
    assert [(mint.token_id, mint.sub_index) for mint in decoded] == [(40, 0), (41, 1), (42, 2)]
    try:
        decode_mint_log(event, max_erc2309_range=2)
    except ConsecutiveRangeTooLarge as exc:
        assert "3 tokens" in str(exc)
    else:
        raise AssertionError("oversized ERC-2309 range was accepted")


def test_non_mints_and_removed_logs_are_ignored() -> None:
    transfer = log(
        topic=ERC721_TRANSFER_TOPIC,
        topics=(address_topic(OPERATOR), address_topic(RECIPIENT), uint_topic(1)),
    )
    assert decode_mint_log(transfer) == []
    removed = EvmLog(
        address=transfer.address,
        topics=transfer.topics,
        data=transfer.data,
        block_number=transfer.block_number,
        block_hash=transfer.block_hash,
        transaction_hash=transfer.transaction_hash,
        log_index=transfer.log_index,
        removed=True,
    )
    assert decode_mint_log(removed) == []
