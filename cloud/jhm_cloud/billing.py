from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from .models import Account, Purchase
from .store import entry, lock_account


# Product IDs are shared with iOS. Prices are obtained from StoreKit, never this table.
PRODUCTS = {
    "justhireme.focus.weekly": {"credits": 30, "kind": "subscription", "period": "week"},
    "justhireme.pro.monthly": {"credits": 150, "kind": "subscription", "period": "month"},
    "justhireme.credits.50": {"credits": 50, "kind": "consumable", "period": None},
}
TAILOR_COST = 5


@dataclass(frozen=True)
class VerifiedPurchase:
    transaction_id: str
    account_token: str
    product_id: str
    expires_ms: int | None
    signed_ms: int
    revoked: bool
    environment: str
    refund_reversed: bool = False


class AppleVerifier:
    def __init__(self, settings):
        from appstoreserverlibrary.models.Environment import Environment
        from appstoreserverlibrary.signed_data_verifier import SignedDataVerifier
        roots = [p.read_bytes() for p in Path(settings["APPLE_ROOT_CERTIFICATES"]).glob("*.cer")]
        if not roots:
            raise RuntimeError("Install Apple PKI root certificates before enabling billing.")
        environment = settings.get("APPLE_ENVIRONMENT", "Production")
        if environment not in ("Production", "Sandbox"):
            raise RuntimeError("Only Apple Production or Sandbox verification is supported.")
        self.environment = environment
        self.verifier = SignedDataVerifier(
            roots, True, Environment(environment), settings["APPLE_BUNDLE_ID"],
            int(settings["APPLE_APP_ID"]) if settings.get("APPLE_APP_ID") else None,
        )
        self.sandbox_verifier = None
        if environment == "Production" and settings.get("APPLE_SANDBOX_ACCOUNT_IDS"):
            self.sandbox_verifier = SignedDataVerifier(roots, True, Environment.SANDBOX,
                                                       settings["APPLE_BUNDLE_ID"])

    def _decode(self, method, signed):
        from appstoreserverlibrary.signed_data_verifier import VerificationException
        try:
            return getattr(self.verifier, method)(signed), self.environment
        except VerificationException:
            if self.sandbox_verifier:
                try:
                    return getattr(self.sandbox_verifier, method)(signed), "Sandbox"
                except VerificationException:
                    pass
        raise HTTPException(400, "Apple signature verification failed.")

    def transaction(self, signed):
        tx, environment = self._decode("verify_and_decode_signed_transaction", signed)
        if not tx.transactionId or not tx.appAccountToken or not tx.signedDate:
            raise HTTPException(400, "Purchase is missing its account binding.")
        if tx.quantity != 1 or str(getattr(tx.inAppOwnershipType, "value", tx.inAppOwnershipType)) != "PURCHASED":
            raise HTTPException(400, "Unsupported purchase ownership or quantity.")
        try:
            token = str(UUID(tx.appAccountToken))
        except ValueError as exc:
            raise HTTPException(400, "Invalid purchase account.") from exc
        product = PRODUCTS.get(tx.productId)
        if not product or (product["kind"] == "subscription" and not tx.expiresDate):
            raise HTTPException(400, "Unknown or incomplete product.")
        return VerifiedPurchase(tx.transactionId, token, tx.productId, tx.expiresDate,
                                tx.signedDate, tx.revocationDate is not None, environment)

    def notification(self, signed):
        from dataclasses import replace
        notification, _ = self._decode("verify_and_decode_notification", signed)
        data = notification.data
        if not data or not data.signedTransactionInfo:
            return None
        tx = self.transaction(data.signedTransactionInfo)
        kind = getattr(notification.notificationType, "value", notification.notificationType)
        return replace(tx, refund_reversed=kind == "REFUND_REVERSED")


def apply_purchase(store, tx, expected_account=None, sandbox_accounts=None):
    product = PRODUCTS.get(tx.product_id)
    if not product:
        raise HTTPException(400, "Unknown product.")
    with store.transaction() as session:
        owner = session.scalar(select(Account).where(Account.purchase_token == tx.account_token))
        if owner is None and expected_account is None:
            return  # Verified orphan/deleted-account notification; never create an owner from a receipt.
        if not owner or (expected_account and owner.id != expected_account):
            raise HTTPException(403, "This purchase belongs to a different account.")
        if tx.environment == "Sandbox" and sandbox_accounts is not None and owner.id not in sandbox_accounts:
            if expected_account is None:
                return
            raise HTTPException(403, "Sandbox purchases are restricted to designated review accounts.")
        # A deleted account remains a minimal billing tombstone. Never recreate it on a webhook.
        if owner.deleted:
            if expected_account:
                raise HTTPException(403, "Account was deleted.")
            return
        account = lock_account(session, owner.id)
        key = f"{tx.environment}:{tx.transaction_id}"
        purchase = session.get(Purchase, key)
        if purchase and (purchase.account_id != account.id or purchase.product_id != tx.product_id):
            raise HTTPException(409, "Transaction identity conflict.")
        if not purchase:
            purchase = Purchase(id=key, account_id=account.id, product_id=tx.product_id,
                                credits=product["credits"], revoked=tx.revoked,
                                expires_ms=tx.expires_ms, signed_ms=tx.signed_ms)
            session.add(purchase)
            if not tx.revoked:
                entry(session, account, f"grant:{key}", product["credits"], "App Store credit purchase")
        elif tx.revoked and not purchase.revoked and tx.signed_ms >= purchase.signed_ms:
            purchase.revoked = True
            entry(session, account, f"revoke:{key}:{tx.signed_ms}", -purchase.credits, "App Store refund")
        elif tx.refund_reversed and not tx.revoked and purchase.revoked and tx.signed_ms > purchase.signed_ms:
            purchase.revoked = False
            entry(session, account, f"restore:{key}:{tx.signed_ms}", purchase.credits, "App Store refund reversed")
        if tx.signed_ms >= purchase.signed_ms:
            purchase.signed_ms = tx.signed_ms
            purchase.expires_ms = tx.expires_ms
