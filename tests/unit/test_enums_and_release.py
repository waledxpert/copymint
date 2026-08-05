from app.domain.enums import (
    AttemptStatus,
    ExecutionMode,
    MintClassification,
    SimulationEvidenceLevel,
    TokenStandard,
)
from app.domain.release import (
    ALLOWED_EXECUTION_MODES,
    RELEASE_EXECUTION_CEILING,
    broadcasting_is_available,
    mode_is_available,
    signing_is_available,
)


def test_specification_enums_keep_stable_wire_values() -> None:
    assert TokenStandard.ERC721.value == "erc721"
    assert MintClassification.PUBLIC_PAID_MINT.value == "public_paid_mint"
    assert AttemptStatus.REORGED.value == "reorged"
    assert SimulationEvidenceLevel.INCONCLUSIVE.value == "inconclusive"


def test_release_one_stops_at_paper_mode() -> None:
    assert RELEASE_EXECUTION_CEILING is ExecutionMode.PAPER
    assert ALLOWED_EXECUTION_MODES == {ExecutionMode.ALERT, ExecutionMode.PAPER}
    assert mode_is_available(ExecutionMode.ALERT)
    assert mode_is_available(ExecutionMode.PAPER)
    assert not mode_is_available(ExecutionMode.MANUAL)
    assert not mode_is_available(ExecutionMode.AUTO)
    assert not signing_is_available()
    assert not broadcasting_is_available()
