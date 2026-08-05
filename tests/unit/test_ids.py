from uuid import RFC_4122

from app.domain.ids import uuid7


def test_uuid7_is_versioned_non_repeating_and_rfc_variant() -> None:
    values = {uuid7() for _ in range(1000)}
    assert len(values) == 1000
    assert all(value.version == 7 for value in values)
    assert all(value.variant == RFC_4122 for value in values)
