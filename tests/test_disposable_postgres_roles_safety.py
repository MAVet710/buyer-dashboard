"""Role preparation cannot reach a hosted or accidental non-test database."""
import pytest

from scripts.acceptance import prepare_disposable_postgres_roles as setup


@pytest.mark.parametrize("opt,url", [
    (None, "postgresql://127.0.0.1/doobielogic_release_test"),
    ("0", "postgresql://127.0.0.1/doobielogic_release_test"),
    ("1", "postgresql://example.com/doobielogic_release_test"),
    ("1", "postgresql://127.0.0.1/postgres"),
    ("1", "postgresql://127.0.0.1/doobielogic_release_test?host=example.com"),
    ("1", "postgresql:///doobielogic_release_test"),
    ("1", "sqlite:///doobielogic_release_test"),
    ("1", ""),
])
def test_role_preparation_rejects_unsafe_target_before_engine(monkeypatch, opt, url):
    monkeypatch.setenv("DOOBIELOGIC_PG_RELEASE_TEST", opt or "")
    monkeypatch.setenv("DOOBIELOGIC_TEST_POSTGRES_URL", url)
    def unexpected_engine(*args, **kwargs):
        pytest.fail("Database engine constructed before scope validation")
    monkeypatch.setattr(setup, "create_engine", unexpected_engine)
    with pytest.raises(ValueError):
        setup.main()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_role_preparation_accepts_explicit_loopback_contract(host):
    url = setup.test_url({"DOOBIELOGIC_PG_RELEASE_TEST": "1", "DOOBIELOGIC_TEST_POSTGRES_URL": f"postgresql://{host}/doobielogic_release_test"})
    assert url.database == "doobielogic_release_test"
