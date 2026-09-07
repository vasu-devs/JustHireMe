import logging
import os
import time

from .app import recover_stale
from .store import Store
from .auth import SupabaseAuth
from .reconciliation import configured_reconcile
from .retention import clean_deleted_accounts


if __name__ == "__main__":
    store = Store(os.environ["DATABASE_URL"])
    auth = SupabaseAuth(os.environ["SUPABASE_URL"], os.environ["SUPABASE_PUBLIC_KEY"],
                        os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    retention = os.environ.get("FINANCIAL_RETENTION_DAYS")
    last_reconcile = -3600
    while True:
        try:
            recover_stale(store)
            clean_deleted_accounts(store, auth, int(retention) if retention else None)
            if os.environ.get("APPLE_API_KEY_PATH") and time.monotonic() - last_reconcile >= 3600:
                report = configured_reconcile(store, os.environ)
                logging.warning("Purchase reconciliation: %s transactions; %s failed accounts",
                                report["transactions"], report["failed_accounts"])
                last_reconcile = time.monotonic()
        except Exception:
            # Do not log database DSNs, user content, or provider exceptions.
            logging.error("Draft recovery failed; inspect database connectivity.")
        time.sleep(60)
