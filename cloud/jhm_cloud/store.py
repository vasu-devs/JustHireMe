from contextlib import contextmanager

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from .models import Account, Base, Entry


class Store:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def sqlite_options(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=10000")

    def initialize(self):
        # Run as a deployment migration, never automatically in an API worker.
        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "postgresql":
            # Hosted auth clients must never read/write these tables through a data API.
            # The server connects as their owner; its endpoints enforce account ownership.
            with self.engine.begin() as connection:
                for table in Base.metadata.sorted_tables:
                    connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY')
                    connection.exec_driver_sql(f'REVOKE ALL ON "{table.name}" FROM PUBLIC')
                    for role in ("anon", "authenticated"):
                        exists = connection.exec_driver_sql(
                            "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).scalar()
                        if exists:
                            connection.exec_driver_sql(f'REVOKE ALL ON "{table.name}" FROM "{role}"')

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session:
            if self.engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise


def lock_account(session, account_id):
    # Every balance-changing path takes this lock first, including deletion.
    account = session.scalar(select(Account).where(Account.id == account_id).with_for_update()
                             .execution_options(populate_existing=True))
    if not account or account.deleted:
        from fastapi import HTTPException
        raise HTTPException(403, "Account is unavailable.")
    return account


def entry(session, account, key, amount, reason):
    session.add(Entry(account_id=account.id, key=key, amount=amount, reason=reason))
    account.balance += amount
