"""Strict decoders for standard NFT mint events."""

from dataclasses import dataclass

from eth_abi.abi import decode
from web3 import Web3

from app.application.ethereum.ports import EvmLog
from app.domain.enums import TokenStandard

ZERO_ADDRESS = "0x" + "00" * 20
ERC721_TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()
ERC1155_SINGLE_TOPIC = Web3.keccak(
    text="TransferSingle(address,address,address,uint256,uint256)"
).hex()
ERC1155_BATCH_TOPIC = Web3.keccak(
    text="TransferBatch(address,address,address,uint256[],uint256[])"
).hex()
ERC2309_CONSECUTIVE_TOPIC = Web3.keccak(
    text="ConsecutiveTransfer(uint256,uint256,address,address)"
).hex()


class InvalidMintLog(ValueError):
    pass


class ConsecutiveRangeTooLarge(InvalidMintLog):
    pass


@dataclass(frozen=True, slots=True)
class DecodedMint:
    collection_address: str
    token_standard: TokenStandard
    token_id: int
    quantity: int
    recipient: str
    operator: str | None
    block_number: int
    block_hash: str
    transaction_hash: str
    log_index: int
    sub_index: int


def topic_address(topic: str) -> str:
    raw = bytes.fromhex(topic.removeprefix("0x"))
    if len(raw) != 32 or any(raw[:12]):
        raise InvalidMintLog("indexed address topic is malformed")
    return Web3.to_checksum_address("0x" + raw[-20:].hex())


def topic_uint(topic: str) -> int:
    raw = bytes.fromhex(topic.removeprefix("0x"))
    if len(raw) != 32:
        raise InvalidMintLog("indexed integer topic is malformed")
    return int.from_bytes(raw, "big")


def data_bytes(value: str) -> bytes:
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        raise InvalidMintLog("event data is malformed") from None
    return raw


def decoded(
    log: EvmLog,
    *,
    standard: TokenStandard,
    token_id: int,
    quantity: int,
    recipient: str,
    operator: str | None,
    sub_index: int,
) -> DecodedMint:
    if quantity <= 0:
        raise InvalidMintLog("mint quantity must be positive")
    return DecodedMint(
        collection_address=Web3.to_checksum_address(log.address),
        token_standard=standard,
        token_id=token_id,
        quantity=quantity,
        recipient=recipient,
        operator=operator,
        block_number=log.block_number,
        block_hash=log.block_hash,
        transaction_hash=log.transaction_hash,
        log_index=log.log_index,
        sub_index=sub_index,
    )


def decode_mint_log(log: EvmLog, *, max_erc2309_range: int = 5000) -> list[DecodedMint]:
    if log.removed or not log.topics:
        return []
    signature = log.topics[0].lower()
    if signature == ERC721_TRANSFER_TOPIC:
        if len(log.topics) != 4 or topic_address(log.topics[1]).lower() != ZERO_ADDRESS:
            return []
        return [
            decoded(
                log,
                standard=TokenStandard.ERC721,
                token_id=topic_uint(log.topics[3]),
                quantity=1,
                recipient=topic_address(log.topics[2]),
                operator=None,
                sub_index=0,
            )
        ]
    if signature == ERC1155_SINGLE_TOPIC:
        if len(log.topics) != 4 or topic_address(log.topics[2]).lower() != ZERO_ADDRESS:
            return []
        token_id, quantity = decode(["uint256", "uint256"], data_bytes(log.data))
        return [
            decoded(
                log,
                standard=TokenStandard.ERC1155,
                token_id=int(token_id),
                quantity=int(quantity),
                recipient=topic_address(log.topics[3]),
                operator=topic_address(log.topics[1]),
                sub_index=0,
            )
        ]
    if signature == ERC1155_BATCH_TOPIC:
        if len(log.topics) != 4 or topic_address(log.topics[2]).lower() != ZERO_ADDRESS:
            return []
        token_ids, quantities = decode(["uint256[]", "uint256[]"], data_bytes(log.data))
        if len(token_ids) != len(quantities):
            raise InvalidMintLog("ERC-1155 batch ID and quantity lengths differ")
        recipient = topic_address(log.topics[3])
        operator = topic_address(log.topics[1])
        return [
            decoded(
                log,
                standard=TokenStandard.ERC1155,
                token_id=int(token_id),
                quantity=int(quantity),
                recipient=recipient,
                operator=operator,
                sub_index=sub_index,
            )
            for sub_index, (token_id, quantity) in enumerate(
                zip(token_ids, quantities, strict=True)
            )
        ]
    if signature == ERC2309_CONSECUTIVE_TOPIC:
        if len(log.topics) != 4 or topic_address(log.topics[2]).lower() != ZERO_ADDRESS:
            return []
        (to_token_id,) = decode(["uint256"], data_bytes(log.data))
        from_token_id = topic_uint(log.topics[1])
        count = int(to_token_id) - from_token_id + 1
        if count <= 0:
            raise InvalidMintLog("ERC-2309 token range is invalid")
        if count > max_erc2309_range:
            raise ConsecutiveRangeTooLarge(
                f"ERC-2309 range contains {count} tokens; limit is {max_erc2309_range}"
            )
        recipient = topic_address(log.topics[3])
        return [
            decoded(
                log,
                standard=TokenStandard.ERC2309,
                token_id=from_token_id + sub_index,
                quantity=1,
                recipient=recipient,
                operator=None,
                sub_index=sub_index,
            )
            for sub_index in range(count)
        ]
    return []
