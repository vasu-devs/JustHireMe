from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

from gateway.clients import ServiceEndpoint, ServiceRegistry, set_service_registry

SERVICE_NAMES = ("profile", "discovery", "ranking", "generation", "automation", "graph")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@dataclass
class LocalServiceSupervisor:
    service_names: tuple[str, ...] = SERVICE_NAMES
    backend_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parents[1])
    internal_token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    registry: ServiceRegistry = field(default_factory=ServiceRegistry)
    processes: dict[str, subprocess.Popen] = field(default_factory=dict)
    log_handles: dict[str, tuple] = field(default_factory=dict)
    restart_counts: dict[str, int] = field(default_factory=dict)
    enabled: bool = True
    max_restarts: int = 3

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def start(self) -> ServiceRegistry:
        if not self.enabled:
            set_service_registry(None)
            return self.registry
        for name in self.service_names:
            await self._start_one(name)
        set_service_registry(self.registry)
        return self.registry

    async def _start_one(self, name: str, *, restart_count: int = 0) -> None:
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        command = self._service_command(name, port)
        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "JHM_INTERNAL_SERVICE_TOKEN": self.internal_token,
            "JHM_SERVICE_NAME": name,
        }
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log_dir = Path(os.environ.get("JHM_APP_DATA_DIR") or os.environ.get("LOCALAPPDATA", str(self.backend_dir))) / "JustHireMe" / "logs" / "services"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout = open(log_dir / f"{name}.out.log", "a", encoding="utf-8")
        stderr = open(log_dir / f"{name}.err.log", "a", encoding="utf-8")
        old_handles = self.log_handles.pop(name, None)
        if old_handles:
            for handle in old_handles:
                handle.close()
        process = subprocess.Popen(
            command,
            cwd=str(self.backend_dir),
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
        )
        self.log_handles[name] = (stdout, stderr)
        self.processes[name] = process
        endpoint = ServiceEndpoint(
            name=name,
            base_url=base_url,
            token=self.internal_token,
            status="starting",
            pid=process.pid,
            port=port,
            started_at=self._now(),
            restart_count=restart_count,
        )
        self.registry.set(endpoint)
        await self._wait_healthy(name, base_url)
        self.registry.set(ServiceEndpoint(
            name=name,
            base_url=base_url,
            token=self.internal_token,
            status="healthy",
            pid=process.pid,
            port=port,
            started_at=endpoint.started_at,
            last_healthy_at=self._now(),
            restart_count=restart_count,
        ))

    def _service_command(self, name: str, port: int) -> list[str]:
        executable = Path(sys.executable)
        if executable.name.lower().startswith("python"):
            return [str(executable), "main.py", "--service", name, "--port", str(port), "--token", self.internal_token]
        return [str(executable), "--service", name, "--port", str(port), "--token", self.internal_token]

    async def _wait_healthy(self, name: str, base_url: str) -> None:
        last_error = ""
        for _ in range(80):
            process = self.processes.get(name)
            if process and process.poll() is not None:
                endpoint = self.registry.get(name)
                if endpoint:
                    self.registry.set(ServiceEndpoint(
                        **{**endpoint.__dict__, "status": "error", "last_error": f"{name} service exited during startup"}
                    ))
                raise RuntimeError(f"{name} service exited during startup")
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    response = await client.get(f"{base_url}/health")
                if response.status_code == 200:
                    return
                last_error = response.text
            except Exception as exc:
                last_error = str(exc)
            await asyncio.sleep(0.1)
        raise RuntimeError(f"{name} service failed health check: {last_error}")

    async def refresh_health(self) -> None:
        for name in self.service_names:
            endpoint = self.registry.get(name)
            process = self.processes.get(name)
            if not endpoint or not process:
                continue
            if process.poll() is not None:
                await self._restart_or_mark_degraded(name, endpoint, f"process exited with code {process.returncode}")
                continue
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    response = await client.get(f"{endpoint.base_url}/health")
                if response.status_code == 200:
                    self.registry.set(ServiceEndpoint(**{**endpoint.__dict__, "status": "healthy", "last_healthy_at": self._now(), "last_error": ""}))
                else:
                    self.registry.set(ServiceEndpoint(**{**endpoint.__dict__, "status": "degraded", "last_error": response.text}))
            except Exception as exc:
                self.registry.set(ServiceEndpoint(**{**endpoint.__dict__, "status": "degraded", "last_error": str(exc)}))

    async def _restart_or_mark_degraded(self, name: str, endpoint: ServiceEndpoint, error: str) -> None:
        restart_count = self.restart_counts.get(name, endpoint.restart_count) + 1
        self.restart_counts[name] = restart_count
        if restart_count > self.max_restarts:
            self.registry.set(ServiceEndpoint(**{**endpoint.__dict__, "status": "degraded", "last_error": error, "restart_count": restart_count}))
            return
        self.registry.set(ServiceEndpoint(**{**endpoint.__dict__, "status": "starting", "last_error": error, "restart_count": restart_count}))
        await asyncio.sleep(min(restart_count, 3))
        await self._start_one(name, restart_count=restart_count)

    async def stop(self) -> None:
        set_service_registry(None)
        for process in self.processes.values():
            if process.poll() is None:
                process.terminate()
        await asyncio.sleep(0.2)
        for process in self.processes.values():
            if process.poll() is None:
                process.kill()
        self.processes.clear()
        for handles in self.log_handles.values():
            for handle in handles:
                handle.close()
        self.log_handles.clear()
