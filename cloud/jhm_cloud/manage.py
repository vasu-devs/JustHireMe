import os
import sys

from .app import recover_stale
from .store import Store
from .reconciliation import configured_reconcile


def main():
    store = Store(os.environ["DATABASE_URL"])
    if sys.argv[1:] == ["init-db"]:
        store.initialize()
    elif sys.argv[1:] == ["recover-drafts"]:
        recover_stale(store)
    elif sys.argv[1:] == ["reconcile-purchases"]:
        report = configured_reconcile(store, os.environ)
        print(report)
        if report["failed_accounts"]:
            raise SystemExit(1)
    else:
        raise SystemExit("Usage: python -m jhm_cloud.manage [init-db|recover-drafts|reconcile-purchases]")


if __name__ == "__main__":
    main()
