from __future__ import annotations
import logging

from dataclasses import dataclass
from threading import RLock

import httpx


@dataclass(frozen=True)
class ServiceEndpoint:
    name: str
    base_url: str
    token: str
    status: str = "starting"
    pid: int | None = None
    port: int | None = None
    started_at: str = ""
    last_healthy_at: str = ""
    last_error: str = ""
    restart_count: int = 0


class ServiceRegistry:
    def __init__(self, endpoints: dict[str, ServiceEndpoint] | None = None):
        self._endpoints = endpoints or {}
        self._lock = RLock()

    def set(self, endpoint: ServiceEndpoint) -> None:
        with self._lock:
            self._endpoints[endpoint.name] = endpoint

    def get(self, name: str) -> ServiceEndpoint | None:
        with self._lock:
            return self._endpoints.get(name)

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            endpoints = dict(self._endpoints)
        return {
            name: {
                "name": endpoint.name,
                "base_url": endpoint.base_url,
                "status": endpoint.status,
                "pid": endpoint.pid,
                "port": endpoint.port,
                "started_at": endpoint.started_at,
                "last_healthy_at": endpoint.last_healthy_at,
                "last_error": endpoint.last_error,
                "restart_count": endpoint.restart_count,
            }
            for name, endpoint in endpoints.items()
        }


# STABILITY: thread-safe gateway service registry
_registry: ServiceRegistry | None = None
_registry_lock = RLock()


def set_service_registry(registry: ServiceRegistry | None) -> None:
    global _registry
    with _registry_lock:
        _registry = registry


def get_service_registry() -> ServiceRegistry | None:
    with _registry_lock:
        return _registry


class ServiceRequestError(RuntimeError):
    pass


class ServiceTimeout(ServiceRequestError):
    pass


class ServiceUnavailable(ServiceRequestError):
    pass


class ServiceNotFound(ServiceRequestError):
    pass


class ServiceConflict(ServiceRequestError):
    pass


class ServiceValidationError(ServiceRequestError):
    pass


class ServiceFailed(ServiceRequestError):
    pass


class BaseServiceClient:
    service_name = ""
    timeout = 60.0

    def __init__(self, endpoint: ServiceEndpoint):
        self.endpoint = endpoint

    async def _request(self, method: str, path: str, *, json: dict | None = None, timeout: float | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.endpoint.token}"}
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                response = await client.request(method, f"{self.endpoint.base_url}{path}", headers=headers, json=json)
        except httpx.TimeoutException as exc:
            raise ServiceTimeout(f"{self.service_name} service timed out: {exc}") from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            raise ServiceUnavailable(f"{self.service_name} service unavailable: {exc}") from exc

        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail", detail)
            except Exception as log_exc:
                logging.getLogger(__name__).warning('suppressed exception in backend/gateway/clients/base.py:_request: %s', log_exc)
                pass
            message = f"{self.service_name} service returned {response.status_code}: {detail}"
            if response.status_code == 404:
                raise ServiceNotFound(message)
            if response.status_code == 409:
                raise ServiceConflict(message)
            if response.status_code == 422:
                raise ServiceValidationError(message)
            if response.status_code >= 500:
                raise ServiceFailed(message)
            raise ServiceRequestError(message)
        return response.json()


def _endpoint(name: str) -> ServiceEndpoint | None:
    registry = get_service_registry()
    return registry.get(name) if registry else None
