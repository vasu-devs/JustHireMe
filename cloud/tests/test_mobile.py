import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from jhm_cloud.app import create_app, recover_stale
from jhm_cloud.billing import VerifiedPurchase, apply_purchase
from jhm_cloud.models import Account, Entry, Operation, now
from jhm_cloud.store import Store, entry, lock_account


class Auth:
    def __init__(self):
        self.deleted = set()

    def identify(self, token):
        if token not in ("alice", "bob") or token in self.deleted:
            raise HTTPException(401, "Invalid session")
        return token

    def delete(self, account_id):
        self.deleted.add(account_id)


class Verifier:
    def __init__(self):
        self.purchase = None

    def transaction(self, signed):
        if signed != "verified-test-transaction":
            raise HTTPException(400, "Invalid signature")
        return self.purchase

    def notification(self, signed):
        return self.transaction(signed)


@pytest.fixture
def setup(tmp_path):
    # Set TEST_DATABASE_URL to a disposable PostgreSQL DB to test real row locking.
    url = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{(tmp_path / 'mobile.db').as_posix()}")
    store = Store(url)
    if os.environ.get("TEST_DATABASE_URL"):
        from jhm_cloud.models import Base
        Base.metadata.drop_all(store.engine)
    store.initialize()
    auth = Auth()
    verifier = Verifier()
    calls = []

    def tailor(profile, job):
        calls.append((profile, job))
        return "# Application\nA grounded application draft."

    app = create_app(store, auth, verifier, tailor, settings={"APPLE_ENVIRONMENT": "Sandbox"})
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer alice"
        account = client.get("/v1/me").json()
        verifier.purchase = VerifiedPurchase("tx-1", account["purchase_token"], "justhireme.credits.50",
                                             None, 100, False, "Sandbox")
        yield client, store, verifier, auth, calls
    store.engine.dispose()


def buy(client):
    return client.post("/v1/billing/transactions", json={"signed_transaction": "verified-test-transaction"})


def profile(client, consent=True):
    return client.put("/v1/profile", json={"name": "Alice", "experience": "Designed accessible products.",
                                          "skills": ["Figma"], "ai_consent": consent})


def job(client):
    result = client.post("/v1/jobs", json={"title": "Designer", "company": "Example",
        "description": "Work with Figma to design accessible products for a small team."})
    assert result.status_code == 201
    return result.json()["id"]


def test_auth_required_and_cache_disabled(setup):
    client, *_ = setup
    assert client.get("/v1/me", headers={"Authorization": "Bearer forged"}).status_code == 401
    del client.headers["Authorization"]
    assert client.get("/v1/jobs").status_code in (401, 403)
    assert client.get("/health").headers["cache-control"] == "no-store"


def test_zero_balance_and_replay_safe_purchase(setup):
    client, store, *_ = setup
    assert client.get("/v1/me").json()["balance"] == 0
    for _ in range(3):
        assert buy(client).status_code == 200
    assert client.get("/v1/me").json()["balance"] == 50
    with store.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Entry)) == 1


def test_forged_unknown_and_cross_account_purchase(setup):
    client, store, verifier, *_ = setup
    assert client.post("/v1/billing/transactions", json={"signed_transaction": "forged-payload"}).status_code == 400
    verifier.purchase = replace(verifier.purchase, product_id="unknown")
    assert buy(client).status_code == 400
    verifier.purchase = replace(verifier.purchase, product_id="justhireme.credits.50")
    client.headers["Authorization"] = "Bearer bob"
    assert buy(client).status_code == 403
    assert client.get("/v1/me").json()["balance"] == 0


def test_concurrent_purchase_delivery_grants_once(setup):
    _, store, verifier, *_ = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: apply_purchase(store, verifier.purchase, "alice"), range(20)))
    with store.transaction() as session:
        assert session.get(Account, "alice").balance == 50


def test_renewals_grant_per_transaction_and_credits_do_not_expire(setup):
    client, store, verifier, *_ = setup
    verifier.purchase = replace(verifier.purchase, product_id="justhireme.focus.weekly", expires_ms=1)
    assert buy(client).status_code == 200
    verifier.purchase = replace(verifier.purchase, transaction_id="renewal-2", expires_ms=2)
    assert buy(client).status_code == 200
    me = client.get("/v1/me").json()
    assert me["balance"] == 60
    assert me["active_subscriptions"] == []


def test_refund_preserves_debt_and_cannot_be_replayed(setup):
    client, store, verifier, *_ = setup
    buy(client)
    with store.transaction() as session:
        entry(session, lock_account(session, "alice"), "spent-all", -50, "Test usage")
    original = verifier.purchase
    verifier.purchase = replace(original, revoked=True, signed_ms=200)
    for _ in range(2):
        assert buy(client).status_code == 200
    verifier.purchase = original
    buy(client)
    assert client.get("/v1/me").json()["balance"] == -50


def test_refund_arriving_before_purchase_never_grants(setup):
    client, _, verifier, *_ = setup
    original = verifier.purchase
    verifier.purchase = replace(original, revoked=True, signed_ms=200)
    buy(client)
    verifier.purchase = original
    buy(client)
    assert client.get("/v1/me").json()["balance"] == 0


def test_account_isolation_for_jobs_profile_drafts_and_export(setup):
    client, *_ = setup
    profile(client)
    job_id = job(client)
    client.headers["Authorization"] = "Bearer bob"
    assert client.get("/v1/jobs").json() == []
    assert client.get("/v1/me").json()["profile"]["name"] == ""
    assert client.patch(f"/v1/jobs/{job_id}", json={"status": "applied"}).status_code == 404
    assert client.post(f"/v1/jobs/{job_id}/tailor", headers={"Idempotency-Key": str(uuid4())}).status_code == 404
    exported = client.get("/v1/export").json()
    assert exported["jobs"] == [] and exported["drafts"] == [] and exported["ledger"] == []


def test_consent_and_credits_are_required_before_generation(setup):
    client, _, _, _, calls = setup
    job_id = job(client)
    headers = {"Idempotency-Key": str(uuid4())}
    assert client.post(f"/v1/jobs/{job_id}/tailor", headers=headers).status_code == 403
    profile(client)
    assert client.post(f"/v1/jobs/{job_id}/tailor", headers=headers).status_code == 402
    assert calls == []


def test_generation_retry_returns_persisted_result_and_charges_once(setup):
    client, _, _, _, calls = setup
    buy(client)
    profile(client)
    job_id = job(client)
    headers = {"Idempotency-Key": str(uuid4())}
    first = client.post(f"/v1/jobs/{job_id}/tailor", headers=headers)
    second = client.post(f"/v1/jobs/{job_id}/tailor", headers=headers)
    assert first.status_code == 200 and first.json() == second.json()
    assert len(calls) == 1
    assert client.get("/v1/me").json()["balance"] == 45
    assert len(client.get("/v1/drafts").json()) == 1
    other_job = job(client)
    assert client.post(f"/v1/jobs/{other_job}/tailor", headers=headers).status_code == 409


def test_provider_failure_refunds_once(setup):
    client, store, verifier, auth, _ = setup
    buy(client)
    profile(client)
    job_id = job(client)

    def failing(*_):
        raise RuntimeError("secret API key must never escape")

    with TestClient(create_app(store, auth, verifier, failing, settings={})) as other:
        headers = {"Authorization": "Bearer alice", "Idempotency-Key": str(uuid4())}
        failed = other.post(f"/v1/jobs/{job_id}/tailor", headers=headers)
        assert failed.status_code == 502 and "secret" not in failed.text
        assert other.post(f"/v1/jobs/{job_id}/tailor", headers=headers).status_code == 409
    assert client.get("/v1/me").json()["balance"] == 50


def test_crashed_generation_recovered_once(setup):
    client, store, *_ = setup
    buy(client)
    with store.transaction() as session:
        operation = Operation(account_id="alice", request_key=str(uuid4()), fingerprint="x", job_id="job",
                              cost=5, created_at=now() - timedelta(minutes=11))
        session.add(operation)
        session.flush()
        entry(session, lock_account(session, "alice"), f"spend:{operation.id}", -5, "Draft")
    recover_stale(store)
    recover_stale(store)
    assert client.get("/v1/me").json()["balance"] == 50


def test_concurrent_requests_cannot_overspend(setup):
    client, store, verifier, auth, _ = setup
    profile(client)
    job_id = job(client)
    with store.transaction() as session:
        entry(session, lock_account(session, "alice"), "test-grant", 5, "Test")

    def request(_):
        with TestClient(create_app(store, auth, verifier, lambda *_: "A draft", settings={})) as other:
            return other.post(f"/v1/jobs/{job_id}/tailor", headers={"Authorization": "Bearer alice",
                "Idempotency-Key": str(uuid4())}).status_code

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(request, range(6)))
    assert results.count(200) == 1
    assert all(status in (200, 402, 409) for status in results)
    assert client.get("/v1/me").json()["balance"] == 0


def test_delete_erases_content_blocks_access_and_ignores_webhooks(setup):
    client, store, verifier, auth, _ = setup
    profile(client)
    buy(client)
    job(client)
    assert client.delete("/v1/account").status_code == 204
    assert client.get("/v1/me").status_code == 401
    # A still-valid cached identity must also be rejected by the account tombstone.
    auth.deleted.clear()
    assert client.get("/v1/me").status_code == 403
    assert client.delete("/v1/account").status_code == 204
    apply_purchase(store, replace(verifier.purchase, transaction_id="after-deletion"))
    with store.transaction() as session:
        account = session.get(Account, "alice")
        assert account.deleted and account.profile == {} and account.balance == 0
        from jhm_cloud.models import Job
        assert session.scalar(select(func.count()).select_from(Job)) == 0


def test_input_validation_prevents_unsafe_url_and_status(setup):
    client, *_ = setup
    assert client.post("/v1/jobs", json={"title": "x", "company": "y", "url": "file:///etc/passwd",
                                        "description": "A description of sufficient length to be considered a job."}).status_code == 422
    assert client.patch(f"/v1/jobs/{job(client)}", json={"status": "paid"}).status_code == 422
    assert client.put("/v1/profile", json={"skills": ["x" * 101]}).status_code == 422


def test_missing_providers_fail_closed(setup):
    client, store, _, auth, _ = setup
    job_id = job(client)
    with TestClient(create_app(store, auth, settings={})) as other:
        other.headers["Authorization"] = "Bearer alice"
        assert other.get("/v1/me").json()["billing_available"] is False
        assert buy(other).status_code == 503
        assert other.post(f"/v1/jobs/{job_id}/tailor", headers={"Idempotency-Key": str(uuid4())}).status_code == 503


def test_refund_reversal_restores_once_and_ignores_older_refund(setup):
    client, store, verifier, *_ = setup
    buy(client)
    refund = replace(verifier.purchase, revoked=True, signed_ms=200)
    apply_purchase(store, refund)
    restored = replace(refund, revoked=False, refund_reversed=True, signed_ms=300)
    apply_purchase(store, restored)
    apply_purchase(store, restored)
    apply_purchase(store, refund)
    assert client.get("/v1/me").json()["balance"] == 50


def test_production_restricts_sandbox_grants(setup):
    _, store, verifier, *_ = setup
    with pytest.raises(HTTPException) as error:
        apply_purchase(store, verifier.purchase, "alice", sandbox_accounts=set())
    assert error.value.status_code == 403
    apply_purchase(store, verifier.purchase, "alice", sandbox_accounts={"alice"})


def test_request_body_is_bounded(setup):
    client, *_ = setup
    response = client.put("/v1/profile", content=b"x" * 140000, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_late_provider_result_cannot_overwrite_recovery_refund(setup):
    client, store, verifier, auth, _ = setup
    buy(client)
    profile(client)
    job_id = job(client)

    def late(*_):
        with store.transaction() as session:
            operation = session.scalar(select(Operation).where(Operation.status == "pending"))
            operation.created_at = now() - timedelta(minutes=11)
        recover_stale(store)
        return "Late output must not be saved"

    with TestClient(create_app(store, auth, verifier, late, settings={})) as other:
        response = other.post(f"/v1/jobs/{job_id}/tailor", headers={"Authorization": "Bearer alice",
                              "Idempotency-Key": str(uuid4())})
        assert response.status_code == 409
    assert client.get("/v1/drafts").json() == []
    assert client.get("/v1/me").json()["balance"] == 50


def test_delete_during_generation_never_recreates_private_content(setup):
    client, store, verifier, auth, _ = setup
    buy(client)
    profile(client)
    job_id = job(client)

    def deleting(*_):
        assert client.delete("/v1/account").status_code == 204
        return "Private content"

    with TestClient(create_app(store, auth, verifier, deleting, settings={})) as other:
        response = other.post(f"/v1/jobs/{job_id}/tailor", headers={"Authorization": "Bearer alice",
                              "Idempotency-Key": str(uuid4())})
        assert response.status_code == 403
    with store.transaction() as session:
        assert session.scalar(select(func.count()).select_from(Operation)) == 0


def test_reconciliation_recovers_missed_renewal_without_duplicate_credits(setup):
    from types import SimpleNamespace
    from jhm_cloud.reconciliation import reconcile
    client, store, verifier, *_ = setup
    buy(client)
    verifier.purchase = replace(verifier.purchase, transaction_id="missed-renewal",
                               product_id="justhireme.pro.monthly", expires_ms=1000)

    class History:
        def get_transaction_history(self, transaction, revision, request, version):
            assert transaction in ("tx-1", "missed-renewal")
            return SimpleNamespace(signedTransactions=["verified-test-transaction"], hasMore=False)

    for _ in range(2):
        report = reconcile(store, verifier, lambda _: History())
        assert report == {"transactions": 1, "failed_accounts": 0}
    assert client.get("/v1/me").json()["balance"] == 200


def test_deletion_retry_and_retention_purge(setup):
    from jhm_cloud.retention import clean_deleted_accounts
    client, store, verifier, auth, _ = setup
    buy(client)
    profile(client)
    job(client)
    original_delete = auth.delete

    def unavailable(_):
        raise HTTPException(503, "Try again")

    auth.delete = unavailable
    assert client.delete("/v1/account").status_code == 503
    assert client.get("/v1/me").status_code == 403
    clean_deleted_accounts(store, auth, 30)
    with store.transaction() as session:
        account = session.get(Account, "alice")
        assert account.profile == {} and not account.auth_deleted
        account.deleted_at = now() - timedelta(days=31)
    auth.delete = original_delete
    clean_deleted_accounts(store, auth, 30)
    with store.transaction() as session:
        assert session.get(Account, "alice") is None
        assert session.scalar(select(func.count()).select_from(Entry)) == 0
    # After purging the old token has no owner and cannot recreate a wallet.
    with pytest.raises(HTTPException):
        apply_purchase(store, verifier.purchase, expected_account="alice")


def test_notification_history_recovers_first_purchase_without_an_anchor(setup):
    from types import SimpleNamespace
    from jhm_cloud.reconciliation import reconcile_notifications
    client, store, verifier, *_ = setup

    class History:
        def get_notification_history(self, page, request):
            assert request.startDate < request.endDate
            if page is None:
                return SimpleNamespace(notificationHistory=[SimpleNamespace(signedPayload="verified-test-transaction")],
                                       hasMore=True, paginationToken="next")
            return SimpleNamespace(notificationHistory=[], hasMore=False)

    assert reconcile_notifications(store, verifier, lambda _: History(), ["Sandbox"]) == 1
    assert reconcile_notifications(store, verifier, lambda _: History(), ["Sandbox"]) == 1
    assert client.get("/v1/me").json()["balance"] == 50
