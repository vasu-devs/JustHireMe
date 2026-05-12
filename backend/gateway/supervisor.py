from __future__ import annotations

import asyncio
import os
import secrets
import socket
import subprocess
import sys
from dataclasses import dataclass, field
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
    enabled: bool = True

    async def start(self) -> ServiceRegistry:
        if not self.enabled:
            set_service_registry(None)
            return self.registry
        for name in self.service_names:
            await self._start_one(name)
        set_service_registry(self.registry)
        return self.registry

    async def _start_one(self, name: str) -> None:
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
        process = subprocess.Popen(
            command,
            cwd=str(self.backend_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self.processes[name] = process
        endpoint = ServiceEndpoint(name=name, base_url=base_url, token=self.internal_token, status="starting")
        self.registry.set(endpoint)
        await self._wait_healthy(name, base_url)
        self.registry.set(ServiceEndpoint(name=name, base_url=base_url, token=self.internal_token, status="healthy"))

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
