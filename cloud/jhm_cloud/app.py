import hashlib
import json
import os
from datetime import timedelta
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from .auth import SupabaseAuth
from .billing import AppleVerifier, PRODUCTS, TAILOR_COST, apply_purchase
from .models import Account, Entry, Job, Operation, Purchase, now
from .limits import BodyLimit
from .store import Store, entry, lock_account
from .tailoring import Tailor


class ProfileBody(BaseModel):
    name: str = Field(default="", max_length=200)
    headline: str = Field(default="", max_length=300)
    location: str = Field(default="", max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=100)
    experience: str = Field(default="", max_length=20000)
    ai_consent: bool = False

    @field_validator("skills")
    @classmethod
    def skills_length(cls, value):
        if any(len(s) > 100 for s in value):
            raise ValueError("Each skill must be 100 characters or fewer.")
        return [s.strip() for s in value if s.strip()]


class JobBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: str = Field(default="", max_length=200)
    url: str = Field(default="", max_length=2000)
    description: str = Field(min_length=40, max_length=30000)

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        if value:
            HttpUrl(value)
            if not value.startswith("https://"):
                raise ValueError("Use an HTTPS job URL.")
        return value


class StatusBody(BaseModel):
    status: Literal["saved", "applied", "interviewing", "offer", "archived"]


class SignedBody(BaseModel):
    signed_transaction: str = Field(min_length=10, max_length=25000)


class NotificationBody(BaseModel):
    signedPayload: str = Field(min_length=10, max_length=60000)


def job_data(job):
    return {key: getattr(job, key) for key in
            ("id", "title", "company", "location", "url", "description", "status")}


def recover_stale(store):
    """Run every minute. CAS completion prevents a late provider result spending refunded credits."""
    cutoff = now() - timedelta(minutes=10)
    with store.transaction() as session:
        owners = list(session.scalars(select(Operation.account_id).where(
            Operation.status == "pending", Operation.created_at < cutoff).distinct()))
    for owner in owners:
        with store.transaction() as session:
            account = lock_account(session, owner)
            operations = session.scalars(select(Operation).where(
                Operation.account_id == owner, Operation.status == "pending", Operation.created_at < cutoff))
            for operation in operations:
                operation.status = "failed"
                entry(session, account, f"refund:{operation.id}", operation.cost, "Interrupted draft refunded")


def create_app(store=None, auth=None, verifier=None, tailor=None, settings=None):
    settings = os.environ if settings is None else settings
    if store is None:
        url = settings["DATABASE_URL"]
        if not url.startswith("postgresql+psycopg://"):
            raise RuntimeError("Hosted deployments require PostgreSQL; SQLite is test-only.")
        store = Store(url)
    auth = auth or SupabaseAuth(settings["SUPABASE_URL"], settings["SUPABASE_PUBLIC_KEY"],
                                settings["SUPABASE_SERVICE_ROLE_KEY"])
    if verifier is None and settings.get("APPLE_ROOT_CERTIFICATES"):
        verifier = AppleVerifier(settings)
    sandbox_accounts = None
    if settings.get("APPLE_ENVIRONMENT", "Production") == "Production":
        sandbox_accounts = {value.strip() for value in settings.get("APPLE_SANDBOX_ACCOUNT_IDS", "").split(",") if value.strip()}
    if tailor is None and settings.get("ANTHROPIC_API_KEY") and settings.get("ANTHROPIC_MODEL"):
        tailor = Tailor(settings["ANTHROPIC_API_KEY"], settings["ANTHROPIC_MODEL"])
    app = FastAPI(title="JustHireMe Mobile API", version="0.1.0")
    app.add_middleware(BodyLimit)
    security = HTTPBearer()

    @app.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    def identity(credentials: HTTPAuthorizationCredentials = Depends(security)):
        return auth.identify(credentials.credentials)

    def user(account_id=Depends(identity)):
        # Auth service validates every request, including deleted/revoked sessions.
        try:
            with store.transaction() as session:
                account = session.get(Account, account_id)
                if account is None:
                    session.add(Account(id=account_id))
                elif account.deleted:
                    raise HTTPException(403, "Account was deleted.")
        except IntegrityError:
            with store.transaction() as session:
                lock_account(session, account_id)
        return account_id

    @app.get("/health")
    def health():
        with store.transaction() as session:
            session.execute(select(1))
        return {"status": "ok"}

    @app.get("/v1/me")
    def me(account_id=Depends(user)):
        with store.transaction() as session:
            account = lock_account(session, account_id)
            subscriptions = list(session.scalars(select(Purchase).where(
                Purchase.account_id == account_id, Purchase.revoked.is_(False),
                Purchase.expires_ms > int(now().timestamp() * 1000))))
            return {"id": account.id, "purchase_token": account.purchase_token,
                    "balance": account.balance, "profile": ProfileBody(**account.profile).model_dump(),
                    "active_subscriptions": sorted(set(p.product_id for p in subscriptions)),
                    "billing_available": verifier is not None, "tailoring_available": tailor is not None,
                    "tailor_cost": TAILOR_COST}

    @app.get("/v1/products")
    def products(account_id=Depends(user)):
        return [{"id": key, **value} for key, value in PRODUCTS.items()]

    @app.put("/v1/profile")
    def profile(body: ProfileBody, account_id=Depends(user)):
        with store.transaction() as session:
            lock_account(session, account_id).profile = body.model_dump()
        return body

    @app.get("/v1/jobs")
    def jobs(account_id=Depends(user)):
        with store.transaction() as session:
            return [job_data(job) for job in session.scalars(select(Job).where(
                Job.account_id == account_id).order_by(Job.created_at.desc()).limit(500))]

    @app.post("/v1/jobs", status_code=201)
    def add_job(body: JobBody, account_id=Depends(user)):
        with store.transaction() as session:
            lock_account(session, account_id)
            job = Job(account_id=account_id, **body.model_dump())
            session.add(job)
            session.flush()
            return job_data(job)

    @app.patch("/v1/jobs/{job_id}")
    def status(job_id: UUID, body: StatusBody, account_id=Depends(user)):
        with store.transaction() as session:
            lock_account(session, account_id)
            job = session.scalar(select(Job).where(Job.id == str(job_id), Job.account_id == account_id))
            if job is None:
                raise HTTPException(404, "Job not found.")
            job.status = body.status
            return job_data(job)

    @app.get("/v1/ledger")
    def ledger(account_id=Depends(user)):
        with store.transaction() as session:
            return [{"id": e.id, "amount": e.amount, "reason": e.reason, "created_at": e.created_at.isoformat()}
                    for e in session.scalars(select(Entry).where(Entry.account_id == account_id)
                                            .order_by(Entry.created_at.desc()).limit(100))]

    @app.post("/v1/billing/transactions")
    def purchase(body: SignedBody, account_id=Depends(user)):
        if verifier is None:
            raise HTTPException(503, "Purchases are not configured yet.")
        apply_purchase(store, verifier.transaction(body.signed_transaction), account_id, sandbox_accounts)
        return {"status": "recorded"}

    @app.post("/v1/billing/apple-notifications")
    def notification(body: NotificationBody):
        if verifier is None:
            raise HTTPException(503, "Purchases are not configured yet.")
        tx = verifier.notification(body.signedPayload)
        if tx:
            apply_purchase(store, tx, sandbox_accounts=sandbox_accounts)
        return {"status": "recorded"}

    @app.get("/v1/drafts")
    def drafts(account_id=Depends(user)):
        with store.transaction() as session:
            return [{"id": o.id, "job_id": o.job_id, "text": o.result} for o in session.scalars(
                select(Operation).where(Operation.account_id == account_id, Operation.status == "complete")
                .order_by(Operation.created_at.desc()).limit(100))]

    @app.post("/v1/jobs/{job_id}/tailor")
    def generate(job_id: UUID, idempotency_key: UUID = Header(), account_id=Depends(user)):
        if tailor is None:
            raise HTTPException(503, "Draft generation is not configured yet. You have not been charged.")
        fingerprint = hashlib.sha256(f"tailor:{job_id}".encode()).hexdigest()
        with store.transaction() as session:
            account = lock_account(session, account_id)
            previous = session.scalar(select(Operation).where(Operation.account_id == account_id,
                                                              Operation.request_key == str(idempotency_key)))
            if previous:
                if previous.fingerprint != fingerprint:
                    raise HTTPException(409, "Request key already used for another job.")
                if previous.status == "complete":
                    return {"id": previous.id, "job_id": previous.job_id, "text": previous.result}
                raise HTTPException(409, "Draft is processing. Refresh drafts shortly." if previous.status == "pending"
                                    else "Draft failed and credits were returned. Start a new request.")
            job = session.scalar(select(Job).where(Job.id == str(job_id), Job.account_id == account_id))
            if job is None:
                raise HTTPException(404, "Job not found.")
            candidate = dict(account.profile)
            if not candidate.get("ai_consent"):
                raise HTTPException(403, "Allow sharing your profile and job with Anthropic in Profile first.")
            if not candidate.get("name") or not candidate.get("experience"):
                raise HTTPException(422, "Add your name and experience to your profile first.")
            if account.balance < TAILOR_COST:
                raise HTTPException(402, "You need more credits to create this draft.")
            if session.scalar(select(Operation.id).where(Operation.account_id == account_id,
                                                         Operation.status == "pending")):
                raise HTTPException(409, "Wait for your current draft to finish.")
            operation = Operation(account_id=account_id, request_key=str(idempotency_key), fingerprint=fingerprint,
                                  job_id=str(job_id), cost=TAILOR_COST)
            session.add(operation)
            session.flush()
            operation_id = operation.id
            entry(session, account, f"spend:{operation_id}", -TAILOR_COST, "Application draft")
            job_input = job_data(job)
        try:
            result = tailor(candidate, job_input)
            if not isinstance(result, str) or not result.strip() or len(result) > 100000:
                raise ValueError("Empty or oversized draft.")
        except Exception:
            with store.transaction() as session:
                account = session.scalar(select(Account).where(Account.id == account_id).with_for_update())
                operation = session.get(Operation, operation_id)
                if operation and operation.status == "pending" and not account.deleted:
                    operation.status = "failed"
                    entry(session, account, f"refund:{operation_id}", TAILOR_COST, "Failed draft refunded")
            raise HTTPException(502, "Draft failed. Reserved credits were returned.") from None
        with store.transaction() as session:
            lock_account(session, account_id)
            changed = session.execute(update(Operation).where(Operation.id == operation_id,
                Operation.status == "pending").values(result=result, status="complete")).rowcount
            if not changed:
                raise HTTPException(409, "Draft was cancelled and credits were returned.")
        return {"id": operation_id, "job_id": str(job_id), "text": result}

    @app.get("/v1/export")
    def export(account_id=Depends(user)):
        payload = {"account": me(account_id), "jobs": jobs(account_id),
                   "drafts": drafts(account_id), "ledger": ledger(account_id)}
        return Response(json.dumps(payload), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="justhireme-export.json"'})

    @app.delete("/v1/account", status_code=204)
    def delete_account(account_id=Depends(identity)):
        with store.transaction() as session:
            account = session.scalar(select(Account).where(Account.id == account_id).with_for_update())
            if account:
                account.deleted = True
                account.deleted_at = account.deleted_at or now()
                account.profile = {}
                account.balance = 0
                session.execute(delete(Job).where(Job.account_id == account_id))
                session.execute(delete(Operation).where(Operation.account_id == account_id))
        # Tombstone commits before deleting external auth. Retries are safe after partial failure.
        auth.delete(account_id)
        with store.transaction() as session:
            account = session.get(Account, account_id)
            if account and account.deleted:
                account.auth_deleted = True
        return Response(status_code=204)

    return app
