from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def load_yaml(name: str) -> dict[str, object]:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_render_topology_keeps_process_secrets_separate() -> None:
    blueprint = load_yaml("render.yaml")
    services = {service["name"]: service for service in blueprint["services"]}

    assert len(services) == len(blueprint["services"])
    assert services["copymint-bot-api"]["type"] == "web"
    assert services["copymint-signer"]["type"] == "pserv"
    assert services["copymint-queue"]["maxmemoryPolicy"] == "noeviction"

    api_keys = {item["key"] for item in services["copymint-bot-api"]["envVars"]}
    worker_keys = {item["key"] for item in services["copymint-indexer-worker"]["envVars"]}
    signer_keys = {item["key"] for item in services["copymint-signer"]["envVars"]}

    assert "TELEGRAM_BOT_TOKEN" in api_keys
    assert "CHAINSTACK_ETHEREUM_HTTP_URL" not in api_keys
    assert "CHAINSTACK_ETHEREUM_HTTP_URL" in worker_keys
    assert "TELEGRAM_BOT_TOKEN" not in worker_keys
    assert "AWS_KMS_KEY_ARN" in signer_keys
    assert "AWS_ACCESS_KEY_ID" in signer_keys
    assert "AWS_SECRET_ACCESS_KEY" in signer_keys
    assert services["copymint-signer"]["preDeployCommand"] == (
        "alembic -c signer_alembic.ini upgrade head"
    )
    assert "TELEGRAM_BOT_TOKEN" not in signer_keys
    assert "CHAINSTACK_ETHEREUM_HTTP_URL" not in signer_keys

    for service in services.values():
        for variable in service.get("envVars", []):
            if variable["key"] == "RELEASE_EXECUTION_CEILING":
                assert variable["value"] == "paper"


def test_local_queue_uses_persistence_and_noeviction() -> None:
    compose = load_yaml("compose.yaml")
    queue = compose["services"]["queue"]
    assert "--appendonly" in queue["command"]
    assert "yes" in queue["command"]
    assert "noeviction" in queue["command"]
    assert queue["volumes"] == ["queue-data:/data"]


def test_local_signer_database_is_physically_separate() -> None:
    compose = load_yaml("compose.yaml")
    app_database = compose["services"]["postgres"]
    signer_database = compose["services"]["signer-postgres"]
    assert app_database["ports"] == ["5432:5432"]
    assert signer_database["ports"] == ["5433:5432"]
    assert app_database["volumes"] == ["postgres-data:/var/lib/postgresql/data"]
    assert signer_database["volumes"] == ["signer-postgres-data:/var/lib/postgresql/data"]
    assert (
        app_database["environment"]["POSTGRES_DB"] != signer_database["environment"]["POSTGRES_DB"]
    )


def test_workspace_rls_uses_the_workspace_primary_key() -> None:
    migration = (
        ROOT / "app/infrastructure/db/migrations/versions/0001_phase1_access_control.py"
    ).read_text(encoding="utf-8")
    assert '"workspaces", workspace_column="id", user_column="personal_owner_user_id"' in migration
