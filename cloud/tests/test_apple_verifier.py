from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from jhm_cloud.billing import AppleVerifier


def test_real_apple_library_rejects_a_forged_jws():
    from appstoreserverlibrary.models.Environment import Environment
    from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
    verifier = AppleVerifier.__new__(AppleVerifier)
    verifier.verifier = SignedDataVerifier([], False, Environment.SANDBOX, "com.justhireme.mobile")
    verifier.sandbox_verifier = None
    verifier.environment = "Sandbox"
    with pytest.raises(HTTPException) as error:
        verifier.transaction("eyJhbGciOiJub25lIn0.eyJwcm9kdWN0SWQiOiJqdXN0aGlyZW1lLmNyZWRpdHMuNTAifQ.")
    assert error.value.status_code == 400


@pytest.mark.parametrize("changes", [
    {"appAccountToken": None}, {"quantity": 2}, {"inAppOwnershipType": "FAMILY_SHARED"},
    {"productId": "justhireme.focus.weekly", "expiresDate": None},
])
def test_verified_payload_must_satisfy_account_and_catalog_policy(changes):
    fields = dict(transactionId="1", appAccountToken="07cac18d-85f4-4638-b138-c4d4f9bc6e3d", signedDate=100,
                  quantity=1, inAppOwnershipType="PURCHASED", productId="justhireme.credits.50",
                  expiresDate=None, revocationDate=None)
    fields.update(changes)
    verifier = AppleVerifier.__new__(AppleVerifier)
    verifier._decode = lambda *_: (SimpleNamespace(**fields), "Sandbox")
    with pytest.raises(HTTPException) as error:
        verifier.transaction("already-verified-in-this-policy-test")
    assert error.value.status_code == 400
