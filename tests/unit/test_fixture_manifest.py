import json
from pathlib import Path


def test_golden_fixture_manifest_has_unique_required_cases() -> None:
    path = Path(__file__).parents[1] / "fixtures" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    fixture_ids = [fixture["id"] for fixture in manifest["fixtures"]]
    assert manifest["network"]["chain_id"] == 1
    assert len(fixture_ids) == len(set(fixture_ids))
    assert {
        "erc721_direct_paid_public",
        "erc1155_transfer_batch",
        "erc2309_consecutive",
        "seadrop_public",
        "seadrop_allowlist_rejection",
        "erc4337_bundler",
        "reorganized_log",
    }.issubset(fixture_ids)
    assert all(fixture["required_evidence"] for fixture in manifest["fixtures"])
