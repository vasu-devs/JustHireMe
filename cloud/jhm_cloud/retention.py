from datetime import timedelta

from sqlalchemy import delete, select

from .models import Account, Entry, Job, Operation, Purchase, now


def clean_deleted_accounts(store, auth, retention_days=None):
    """Retry identity deletion, then purge financial tombstones under the operator's policy."""
    with store.transaction() as session:
        pending = list(session.scalars(select(Account.id).where(Account.deleted.is_(True),
                                                                Account.auth_deleted.is_(False))))
    for account_id in pending:
        try:
            auth.delete(account_id)
        except Exception:
            continue  # Try again on the next recovery tick; no identity/content is logged.
        with store.transaction() as session:
            account = session.get(Account, account_id)
            if account and account.deleted:
                account.auth_deleted = True
    if retention_days is None:
        return
    if retention_days < 1:
        raise ValueError("Financial retention must be an explicitly chosen positive number of days.")
    cutoff = now() - timedelta(days=retention_days)
    with store.transaction() as session:
        accounts = list(session.scalars(select(Account).where(Account.deleted.is_(True),
            Account.auth_deleted.is_(True), Account.deleted_at < cutoff).with_for_update()))
        for account in accounts:
            for table in (Operation, Job, Entry, Purchase):
                session.execute(delete(table).where(table.account_id == account.id))
            session.delete(account)
