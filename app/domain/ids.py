"""Time-sortable, non-guessable UUIDv7 identifiers."""

import secrets
import time
from uuid import UUID


def uuid7() -> UUID:
    """Generate an RFC 9562 UUIDv7 using the OS CSPRNG.

    UUIDv7 is time-sortable. Random bits keep identifiers non-guessable; uniqueness is ultimately
    enforced by database primary keys.
    """
    timestamp_ms = time.time_ns() // 1_000_000
    if timestamp_ms >= 1 << 48:
        raise OverflowError("Unix timestamp does not fit in UUIDv7's 48-bit field")

    random_bits = secrets.randbits(74)
    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)
    value = (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return UUID(int=value)
