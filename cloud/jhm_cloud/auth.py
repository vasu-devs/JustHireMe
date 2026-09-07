from uuid import UUID

import httpx
from fastapi import HTTPException


class SupabaseAuth:
    def __init__(self, url, public_key, admin_key):
        if not url.startswith("https://"):
            raise RuntimeError("Supabase authentication requires HTTPS.")
        self.url = url.rstrip("/")
        self.public_key = public_key
        self.admin_key = admin_key

    def identify(self, token):
        try:
            response = httpx.get(f"{self.url}/auth/v1/user", timeout=10,
                                 headers={"apikey": self.public_key, "Authorization": f"Bearer {token}"})
            if response.status_code >= 500 or response.status_code == 429:
                raise HTTPException(503, "Sign-in service is temporarily unavailable.")
            if response.status_code != 200:
                raise HTTPException(401, "Please sign in again.")
            return str(UUID(response.json()["id"]))
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(503, "Sign-in service is temporarily unavailable.") from exc

    def delete(self, account_id):
        try:
            response = httpx.delete(f"{self.url}/auth/v1/admin/users/{account_id}", timeout=15,
                                    headers={"apikey": self.admin_key,
                                             "Authorization": f"Bearer {self.admin_key}"})
            if response.status_code not in (200, 204, 404):
                raise HTTPException(503, "Your data was removed. Retry to finish deleting your sign-in.")
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Your data was removed. Retry to finish deleting your sign-in.") from exc
