"""System business layer: subsystem health, diagnostics, and optional runtimes.

Backs the health, diagnostics and runtime routers. Everything that probes or
mutates the local runtime (LanceDB pack, ONNX embedding model) lives here rather
than in a router, so the transport layer holds no background jobs or driver
knowledge.
"""

from system.service import SystemService, create_system_service

__all__ = ["SystemService", "create_system_service"]
