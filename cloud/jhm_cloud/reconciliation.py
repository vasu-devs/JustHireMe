"""Replay Apple's verified history so a missed webhook does not lose renewal credits."""
import logging
from dataclasses import replace
from pathlib import Path
from datetime import timedelta

from sqlalchemy import select

from .billing import AppleVerifier, apply_purchase
from .models import Account, Purchase, now


def reconcile(store, verifier, client_factory, sandbox_accounts=None):
    from appstoreserverlibrary.api_client import GetTransactionHistoryVersion
    from appstoreserverlibrary.models.TransactionHistoryRequest import TransactionHistoryRequest

    # One transaction can anchor the customer's complete app history. Avoid querying per renewal.
    anchors = {}
    with store.transaction() as session:
        for purchase in session.scalars(select(Purchase).join(Account).where(Account.deleted.is_(False))):
            environment, transaction_id = purchase.id.split(":", 1)
            anchors.setdefault((purchase.account_id, environment), transaction_id)
    processed = 0
    failures = 0
    for (account_id, environment), transaction_id in anchors.items():
        try:
            client = client_factory(environment)
            revision = None
            seen = set()
            for _ in range(1000):
                response = client.get_transaction_history(transaction_id, revision, TransactionHistoryRequest(),
                                                          GetTransactionHistoryVersion.V2)
                for signed in response.signedTransactions or []:
                    tx = verifier.transaction(signed)
                    # Current server history is authoritative for a refund reversal, unlike
                    # an old non-revoked receipt supplied by a client. signed_ms still orders it.
                    tx = replace(tx, refund_reversed=not tx.revoked)
                    # Apple history may contain legacy/unbound products. Never transfer ownership.
                    apply_purchase(store, tx, expected_account=account_id, sandbox_accounts=sandbox_accounts)
                    processed += 1
                if not response.hasMore:
                    break
                if not response.revision or response.revision in seen:
                    raise RuntimeError("Apple returned an invalid pagination revision")
                revision = response.revision
                seen.add(revision)
            else:
                raise RuntimeError("History exceeded the per-account pagination limit")
        except Exception:
            failures += 1
            logging.error("Purchase history reconciliation failed for an account; retry and investigate.")
    return {"transactions": processed, "failed_accounts": failures}


def reconcile_notifications(store, verifier, client_factory, environments, sandbox_accounts=None):
    from appstoreserverlibrary.models.NotificationHistoryRequest import NotificationHistoryRequest
    end = now()
    request = NotificationHistoryRequest(startDate=int((end - timedelta(days=30)).timestamp() * 1000),
                                         endDate=int(end.timestamp() * 1000))
    processed = 0
    for environment in environments:
        client = client_factory(environment)
        page = None
        seen = set()
        for _ in range(1000):
            response = client.get_notification_history(page, request)
            for notification in response.notificationHistory or []:
                tx = verifier.notification(notification.signedPayload)
                if tx:
                    apply_purchase(store, tx, sandbox_accounts=sandbox_accounts)
                    processed += 1
            if not response.hasMore:
                break
            if not response.paginationToken or response.paginationToken in seen:
                raise RuntimeError("Invalid notification pagination token")
            page = response.paginationToken
            seen.add(page)
        else:
            raise RuntimeError("Notification replay exceeds the safety limit; partition the time window")
    return processed


def configured_reconcile(store, settings):
    from appstoreserverlibrary.api_client import AppStoreServerAPIClient
    from appstoreserverlibrary.models.Environment import Environment

    verifier = AppleVerifier(settings)
    key = Path(settings["APPLE_API_KEY_PATH"]).read_bytes()
    clients = {}

    def client_factory(environment):
        if environment not in clients:
            clients[environment] = AppStoreServerAPIClient(key, settings["APPLE_API_KEY_ID"],
                settings["APPLE_API_ISSUER_ID"], settings["APPLE_BUNDLE_ID"], Environment(environment))
        return clients[environment]

    allowed = None if settings.get("APPLE_ENVIRONMENT") == "Sandbox" else {
        item.strip() for item in settings.get("APPLE_SANDBOX_ACCOUNT_IDS", "").split(",") if item.strip()}
    report = reconcile(store, verifier, client_factory, allowed)
    environments = [settings.get("APPLE_ENVIRONMENT", "Production")]
    if environments == ["Production"] and allowed:
        environments.append("Sandbox")
    report["notifications"] = reconcile_notifications(store, verifier, client_factory, environments, allowed)
    return report
