import pytest

from app.application.ethereum.classification import SaleStateEvidence, classify_mint
from app.domain.enums import MintClassification, MintRoute


@pytest.mark.parametrize(
    ("evidence", "classification", "reason"),
    [
        (
            SaleStateEvidence(MintRoute.DIRECT, "fixture", True, 10**17),
            MintClassification.PUBLIC_PAID_MINT,
            "public_sale_paid",
        ),
        (
            SaleStateEvidence(MintRoute.SEADROP, "fixture", True, 0),
            MintClassification.PUBLIC_FREE_MINT,
            "public_sale_free",
        ),
        (
            SaleStateEvidence(MintRoute.SEADROP, "fixture", allowlist_required=True),
            MintClassification.ALLOWLIST_MINT,
            "allowlist_required",
        ),
        (
            SaleStateEvidence(MintRoute.DIRECT, "fixture", token_gate_required=True),
            MintClassification.TOKEN_GATED_MINT,
            "token_gate_required",
        ),
        (
            SaleStateEvidence(MintRoute.SEADROP, "fixture", server_signature_required=True),
            MintClassification.SERVER_SIGNED_MINT,
            "server_signature_required",
        ),
        (
            SaleStateEvidence(MintRoute.DIRECT, "fixture", admin_mint=True),
            MintClassification.ADMIN_MINT,
            "admin_call_evidence",
        ),
        (
            SaleStateEvidence(MintRoute.DIRECT, "fixture", airdrop=True),
            MintClassification.AIRDROP,
            "airdrop_evidence",
        ),
        (
            SaleStateEvidence(MintRoute.UNKNOWN, "fixture", bridge=True),
            MintClassification.BRIDGE_MINT,
            "bridge_evidence",
        ),
        (
            SaleStateEvidence(MintRoute.UNKNOWN, "fixture", migration=True),
            MintClassification.MIGRATION_MINT,
            "migration_evidence",
        ),
        (
            SaleStateEvidence(MintRoute.MARKETPLACE, "fixture", lazy_marketplace=True),
            MintClassification.LAZY_MARKETPLACE_MINT,
            "lazy_marketplace_evidence",
        ),
    ],
)
def test_classification_requires_explicit_evidence(
    evidence: SaleStateEvidence,
    classification: MintClassification,
    reason: str,
) -> None:
    decision = classify_mint(evidence)
    assert decision.classification is classification
    assert decision.reason_code == reason


def test_missing_or_incomplete_sale_state_remains_unknown() -> None:
    assert classify_mint(None).classification is MintClassification.UNKNOWN_MINT
    incomplete = classify_mint(SaleStateEvidence(MintRoute.DIRECT, "fixture"))
    assert incomplete.classification is MintClassification.UNKNOWN_MINT
    assert incomplete.reason_code == "sale_state_inconclusive"
