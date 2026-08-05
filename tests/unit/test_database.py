from app.infrastructure.db.session import normalize_database_url


def test_render_database_url_is_normalized_for_psycopg() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )
    assert (
        normalize_database_url("postgres://user:pass@host/db")
        == "postgresql+psycopg://user:pass@host/db"
    )


def test_explicit_driver_url_is_unchanged() -> None:
    url = "postgresql+psycopg://user:pass@host/db"
    assert normalize_database_url(url) == url
