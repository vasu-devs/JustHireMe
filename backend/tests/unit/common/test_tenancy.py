"""core/tenancy.py + the per-tenant path resolver.

Kùzu and LanceDB have no row-level security, so their isolation is entirely a
function of the directory they open. These tests are that guarantee.
"""

from __future__ import annotations

import pytest

from core.paths import app_data_dir, tenant_data_dir, tenant_data_path
from core.tenancy import (
    LOCAL_TENANT,
    LOCAL_TENANT_ID,
    InvalidTenantError,
    TenantContext,
    local_tenant,
)

TENANT_A = TenantContext("11111111-2222-3333-4444-555555555555")
TENANT_B = TenantContext("99999999-8888-7777-6666-555555555555")


# ------------------------------------------------------------------- identity


def test_a_valid_uuid_is_accepted():
    assert TenantContext("11111111-2222-3333-4444-555555555555").tenant_id


@pytest.mark.parametrize("value", [
    "", "local", "default", "not-a-uuid", "1234", None,
    "11111111-2222-3333-4444-5555555555",     # too short
    "11111111_2222_3333_4444_555555555555",   # wrong separators
    "../../etc/passwd",
    "11111111-2222-3333-4444-555555555555/..",
])
def test_anything_that_is_not_a_uuid_is_rejected(value):
    """A tenant id reaches this from a session; a path fragment must never pass."""
    with pytest.raises(InvalidTenantError):
        TenantContext(value)


def test_the_error_never_echoes_the_offending_value():
    """Session material must not end up in a log line or a client response."""
    with pytest.raises(InvalidTenantError) as caught:
        TenantContext("s3cr3t-session-fragment")
    assert "s3cr3t" not in str(caught.value)


def test_a_context_cannot_be_reassigned_mid_request():
    """Frozen: a request's tenant is fixed the moment it is established."""
    with pytest.raises(AttributeError):
        TENANT_A.tenant_id = TENANT_B.tenant_id  # type: ignore[misc]


def test_the_desktop_tenant_is_recognisable():
    assert LOCAL_TENANT.is_local is True
    assert local_tenant() is LOCAL_TENANT
    assert TENANT_A.is_local is False


def test_the_local_tenant_is_a_real_uuid():
    """So the same column type and RLS predicate work in both builds."""
    assert TenantContext(LOCAL_TENANT_ID).tenant_id == LOCAL_TENANT_ID


def test_two_contexts_with_the_same_id_are_equal():
    assert TenantContext(TENANT_A.tenant_id) == TENANT_A
    assert TENANT_A != TENANT_B


# ------------------------------------------------------------ path isolation


def test_the_desktop_build_keeps_using_the_flat_directory(monkeypatch, tmp_path):
    """Existing installs must not have their data moved by this change."""
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path))
    assert tenant_data_dir(None) == app_data_dir()
    assert tenant_data_dir(LOCAL_TENANT) == app_data_dir()


def test_each_hosted_tenant_gets_its_own_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path))
    assert tenant_data_dir(TENANT_A) != tenant_data_dir(TENANT_B)
    assert tenant_data_dir(TENANT_A).is_relative_to(app_data_dir())


def test_a_tenant_directory_cannot_escape_the_app_data_root(monkeypatch, tmp_path):
    """The UUID guard is what makes this true; assert the consequence directly."""
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path))
    resolved = tenant_data_dir(TENANT_A).resolve()
    assert resolved.is_relative_to(app_data_dir().resolve())
    assert ".." not in resolved.parts


def test_tenant_data_path_joins_below_the_tenant_root(monkeypatch, tmp_path):
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path))
    vectors = tenant_data_path("vectors", tenant=TENANT_A)
    assert vectors.parent == tenant_data_dir(TENANT_A)
    assert vectors.name == "vectors"


def test_one_tenants_store_path_is_never_another_tenants(monkeypatch, tmp_path):
    """The whole namespace-isolation guarantee, stated as one assertion."""
    monkeypatch.setenv("JHM_APP_DATA_DIR", str(tmp_path))
    for store in ("graph", "vectors", "assets"):
        assert tenant_data_path(store, tenant=TENANT_A) != tenant_data_path(store, tenant=TENANT_B)
