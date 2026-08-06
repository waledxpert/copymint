"""Evidence-driven mint route and classification decisions."""

from dataclasses import dataclass

from app.domain.enums import MintClassification, MintRoute


@dataclass(frozen=True, slots=True)
class SaleStateEvidence:
    route: MintRoute
    source: str
    public_sale_active: bool | None = None
    unit_price_wei: int | None = None
    allowlist_required: bool = False
    token_gate_required: bool = False
    server_signature_required: bool = False
    admin_mint: bool = False
    airdrop: bool = False
    bridge: bool = False
    migration: bool = False
    lazy_marketplace: bool = False

    def __post_init__(self) -> None:
        if self.unit_price_wei is not None and self.unit_price_wei < 0:
            raise ValueError("mint unit price cannot be negative")
        if not self.source or len(self.source) > 64:
            raise ValueError("classification evidence source is required")


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    route: MintRoute
    classification: MintClassification
    reason_code: str


def classify_mint(evidence: SaleStateEvidence | None) -> ClassificationDecision:
    if evidence is None:
        return ClassificationDecision(
            MintRoute.UNKNOWN,
            MintClassification.UNKNOWN_MINT,
            "sale_state_evidence_missing",
        )
    route = evidence.route
    if evidence.bridge:
        return ClassificationDecision(route, MintClassification.BRIDGE_MINT, "bridge_evidence")
    if evidence.migration:
        return ClassificationDecision(
            route, MintClassification.MIGRATION_MINT, "migration_evidence"
        )
    if evidence.lazy_marketplace:
        return ClassificationDecision(
            MintRoute.MARKETPLACE,
            MintClassification.LAZY_MARKETPLACE_MINT,
            "lazy_marketplace_evidence",
        )
    if evidence.airdrop:
        return ClassificationDecision(route, MintClassification.AIRDROP, "airdrop_evidence")
    if evidence.admin_mint:
        return ClassificationDecision(route, MintClassification.ADMIN_MINT, "admin_call_evidence")
    if evidence.server_signature_required:
        return ClassificationDecision(
            route,
            MintClassification.SERVER_SIGNED_MINT,
            "server_signature_required",
        )
    if evidence.token_gate_required:
        return ClassificationDecision(
            route, MintClassification.TOKEN_GATED_MINT, "token_gate_required"
        )
    if evidence.allowlist_required:
        return ClassificationDecision(
            route, MintClassification.ALLOWLIST_MINT, "allowlist_required"
        )
    if evidence.public_sale_active is True and evidence.unit_price_wei is not None:
        classification = (
            MintClassification.PUBLIC_FREE_MINT
            if evidence.unit_price_wei == 0
            else MintClassification.PUBLIC_PAID_MINT
        )
        reason = "public_sale_free" if evidence.unit_price_wei == 0 else "public_sale_paid"
        return ClassificationDecision(route, classification, reason)
    return ClassificationDecision(route, MintClassification.UNKNOWN_MINT, "sale_state_inconclusive")
