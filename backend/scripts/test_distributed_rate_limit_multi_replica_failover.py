#!/usr/bin/env python3
"""Multi-replica shared-budget and isolated Redis failover gate.

This starts a temporary loopback-only Redis server on a dynamically selected
port. It does not stop, flush, reconfigure, or write to the shared system Redis
service. NWDP runtime lookup remains disabled.
"""

from __future__ import annotations

import json
import multiprocessing
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from queue import Empty
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from redis import Redis


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import settings  # noqa: E402
from app.core.distributed_rate_limit import (  # noqa: E402
    RateLimitPolicy,
    evaluate_rate_limit,
)


SCHEMA_VERSION = (
    "nwdp_runtime_lookup_multi_replica_failover_gate.v1"
)
WORKER_COUNT = 4
ATTEMPTS_PER_WORKER = 20
SHARED_LIMIT = 40
WINDOW_SECONDS = 30


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}", flush=True)


def reserve_port() -> int:
    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def redis_client(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=0.25,
        socket_timeout=0.25,
    )


def start_temporary_redis(
    *,
    port: int,
    directory: Path,
) -> subprocess.Popen[bytes]:
    command = [
        "redis-server",
        "--port",
        str(port),
        "--bind",
        "127.0.0.1",
        "--protected-mode",
        "yes",
        "--save",
        "",
        "--appendonly",
        "no",
        "--dir",
        str(directory),
        "--dbfilename",
        "temporary.rdb",
        "--loglevel",
        "warning",
    ]
    process = subprocess.Popen(
        command,
        cwd=str(directory),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    url = f"redis://127.0.0.1:{port}/0"
    client = redis_client(url)
    try:
        for _ in range(50):
            if process.poll() is not None:
                raise RuntimeError(
                    "Temporary Redis exited during startup"
                )
            try:
                if client.ping():
                    return process
            except Exception:
                time.sleep(0.05)
        raise RuntimeError(
            "Temporary Redis did not become ready"
        )
    finally:
        client.close()


def stop_temporary_redis(
    process: subprocess.Popen[bytes],
) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_until_unavailable(url: str) -> None:
    client = redis_client(url)
    try:
        for _ in range(50):
            try:
                client.ping()
            except Exception:
                return
            time.sleep(0.05)
    finally:
        client.close()
    raise RuntimeError(
        "Temporary Redis remained reachable after termination"
    )


def replica_worker(
    redis_url: str,
    namespace: str,
    actor_id: str,
    tenant_id: str,
    worker_index: int,
    start_event: multiprocessing.synchronize.Event,
    result_queue: multiprocessing.queues.Queue,
) -> None:
    from app.core import distributed_rate_limit as limiter

    limiter.settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
        namespace
    )

    client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )
    policy = limiter.RateLimitPolicy(
        tier="PRO",
        window_seconds=WINDOW_SECONDS,
        actor_requests=SHARED_LIMIT,
        tenant_requests=SHARED_LIMIT,
        global_requests=SHARED_LIMIT,
    )
    principal = SimpleNamespace(
        user_id=actor_id,
        tenant_id=tenant_id,
    )

    allowed = 0
    rejected = 0
    dimensions: dict[str, int] = {}
    errors: list[str] = []

    try:
        if not start_event.wait(timeout=10):
            raise RuntimeError("Worker start barrier timed out")

        for _ in range(ATTEMPTS_PER_WORKER):
            try:
                decision = limiter.evaluate_rate_limit(
                    client,
                    policy,
                    principal,
                )
                if decision.allowed:
                    allowed += 1
                else:
                    rejected += 1
                    dimension = decision.dimension or "none"
                    dimensions[dimension] = (
                        dimensions.get(dimension, 0) + 1
                    )
            except Exception as exc:
                errors.append(type(exc).__name__)
    finally:
        client.close()

    result_queue.put({
        "worker_index": worker_index,
        "allowed": allowed,
        "rejected": rejected,
        "dimensions": dimensions,
        "errors": errors,
    })


def run_replicas(
    *,
    redis_url: str,
    namespace: str,
) -> list[dict[str, Any]]:
    context = multiprocessing.get_context("spawn")
    start_event = context.Event()
    result_queue = context.Queue()
    actor_id = str(uuid.uuid4())
    tenant_id = f"replica-gate-{uuid.uuid4()}"

    workers = [
        context.Process(
            target=replica_worker,
            args=(
                redis_url,
                namespace,
                actor_id,
                tenant_id,
                index,
                start_event,
                result_queue,
            ),
        )
        for index in range(WORKER_COUNT)
    ]

    for worker in workers:
        worker.start()
    start_event.set()

    results: list[dict[str, Any]] = []
    try:
        for _ in workers:
            try:
                results.append(
                    result_queue.get(timeout=20)
                )
            except Empty as exc:
                raise RuntimeError(
                    "Timed out waiting for replica result"
                ) from exc
    finally:
        for worker in workers:
            worker.join(timeout=10)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)

    for worker in workers:
        check(
            worker.exitcode == 0,
            "Replica worker exits cleanly",
        )

    return sorted(
        results,
        key=lambda item: item["worker_index"],
    )


def evaluate_once(
    *,
    redis_url: str,
    namespace: str,
    actor_id: str,
    tenant_id: str,
) -> Any:
    from app.core import distributed_rate_limit as limiter

    original_namespace = (
        limiter.settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE
    )
    limiter.settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
        namespace
    )

    client = redis_client(redis_url)
    try:
        return limiter.evaluate_rate_limit(
            client,
            RateLimitPolicy(
                tier="PRO",
                window_seconds=WINDOW_SECONDS,
                actor_requests=5,
                tenant_requests=5,
                global_requests=5,
            ),
            SimpleNamespace(
                user_id=actor_id,
                tenant_id=tenant_id,
            ),
        )
    finally:
        client.close()
        limiter.settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_NAMESPACE = (
            original_namespace
        )


def main() -> int:
    started = time.perf_counter()

    check(
        settings.NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
        is False,
        "Runtime lookup starts disabled",
    )
    check(
        settings
        .NWDP_BOUNDARY_RUNTIME_LOOKUP_RATE_LIMIT_ENABLED
        is True,
        "Configured limiter starts enabled",
    )

    shared_redis_ping_before = subprocess.run(
        [
            "redis-cli",
            "-h",
            "127.0.0.1",
            "-p",
            "6379",
            "--raw",
            "PING",
        ],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    check(
        shared_redis_ping_before == "PONG",
        "Shared system Redis starts healthy",
    )

    port = reserve_port()
    check(
        port != 6379,
        "Temporary Redis uses a non-system port",
    )

    namespace = (
        "agrios:test:nwdp-multi-replica:"
        f"{uuid.uuid4()}"
    )
    redis_url = f"redis://127.0.0.1:{port}/0"
    temporary_process: subprocess.Popen[bytes] | None = None

    with tempfile.TemporaryDirectory(
        prefix="nwdp-redis-failover-"
    ) as temporary_directory:
        directory = Path(temporary_directory)

        try:
            temporary_process = start_temporary_redis(
                port=port,
                directory=directory,
            )
            check(
                redis_client(redis_url).ping() is True,
                "Temporary Redis starts healthy",
            )

            results = run_replicas(
                redis_url=redis_url,
                namespace=namespace,
            )

            allowed = sum(
                item["allowed"] for item in results
            )
            rejected = sum(
                item["rejected"] for item in results
            )
            errors = [
                error
                for item in results
                for error in item["errors"]
            ]
            rejection_dimensions: dict[str, int] = {}
            for item in results:
                for dimension, count in (
                    item["dimensions"].items()
                ):
                    rejection_dimensions[dimension] = (
                        rejection_dimensions.get(
                            dimension,
                            0,
                        )
                        + count
                    )

            check(
                allowed == SHARED_LIMIT,
                "Four replicas share one exact global budget",
            )
            check(
                rejected
                == (
                    WORKER_COUNT * ATTEMPTS_PER_WORKER
                    - SHARED_LIMIT
                ),
                "Excess multi-replica requests are rejected",
            )
            check(
                not errors,
                "Multi-replica execution has no backend errors",
            )
            check(
                rejection_dimensions.get("actor", 0)
                == rejected,
                "Shared actor exhaustion is distinguished",
            )

            failure_actor = str(uuid.uuid4())
            failure_tenant = f"failover-{uuid.uuid4()}"
            failover_namespace = f"{namespace}:failover"

            pre_failure = evaluate_once(
                redis_url=redis_url,
                namespace=failover_namespace,
                actor_id=failure_actor,
                tenant_id=failure_tenant,
            )
            check(
                pre_failure.allowed,
                "Limiter allows before isolated outage",
            )

            stop_temporary_redis(temporary_process)
            temporary_process = None
            wait_until_unavailable(redis_url)

            failure_status = None
            failure_code = None
            try:
                evaluate_once(
                    redis_url=redis_url,
                    namespace=failover_namespace,
                    actor_id=failure_actor,
                    tenant_id=failure_tenant,
                )
            except HTTPException as exc:
                failure_status = exc.status_code
                if isinstance(exc.detail, dict):
                    failure_code = exc.detail.get("code")

            check(
                failure_status == 503,
                "Isolated Redis outage fails closed",
            )
            check(
                failure_code
                == "NWDP_RUNTIME_LOOKUP_RATE_LIMIT_UNAVAILABLE",
                "Outage returns stable unavailable code",
            )

            temporary_process = start_temporary_redis(
                port=port,
                directory=directory,
            )
            recovered = evaluate_once(
                redis_url=redis_url,
                namespace=failover_namespace,
                actor_id=failure_actor,
                tenant_id=failure_tenant,
            )
            check(
                recovered.allowed,
                "Limiter recovers after Redis restart",
            )

            cleanup_client = redis_client(redis_url)
            try:
                keys = list(
                    cleanup_client.scan_iter(
                        match=f"{namespace}:*"
                    )
                )
                if keys:
                    cleanup_client.delete(*keys)
                remaining_keys = list(
                    cleanup_client.scan_iter(
                        match=f"{namespace}:*"
                    )
                )
            finally:
                cleanup_client.close()

            check(
                not remaining_keys,
                "Temporary limiter keys are cleaned",
            )

            shared_redis_ping_after = subprocess.run(
                [
                    "redis-cli",
                    "-h",
                    "127.0.0.1",
                    "-p",
                    "6379",
                    "--raw",
                    "PING",
                ],
                check=True,
                text=True,
                capture_output=True,
            ).stdout.strip()
            check(
                shared_redis_ping_after == "PONG",
                "Shared system Redis remains healthy",
            )
            check(
                settings
                .NWDP_BOUNDARY_RUNTIME_LOOKUP_ENABLED
                is False,
                "Runtime lookup remains disabled",
            )

            report = {
                "schema_version": SCHEMA_VERSION,
                "status":
                    "MULTI_REPLICA_FAILOVER_GATE_PASSED_LOOKUP_DISABLED",
                "healthy": True,
                "replicas": {
                    "worker_count": WORKER_COUNT,
                    "attempts_per_worker":
                        ATTEMPTS_PER_WORKER,
                    "total_attempts":
                        WORKER_COUNT
                        * ATTEMPTS_PER_WORKER,
                    "allowed": allowed,
                    "rejected": rejected,
                    "shared_limit": SHARED_LIMIT,
                    "rejection_dimensions":
                        rejection_dimensions,
                },
                "failover": {
                    "pre_failure_allowed":
                        pre_failure.allowed,
                    "outage_status": failure_status,
                    "outage_code": failure_code,
                    "post_restart_allowed":
                        recovered.allowed,
                    "temporary_redis_persistence":
                        "DISABLED",
                    "budget_state_after_restart":
                        "RESET_EXPECTED_FOR_ISOLATED_TEST",
                },
                "isolation": {
                    "temporary_port": port,
                    "system_port": 6379,
                    "temporary_namespace": namespace,
                    "failover_namespace": failover_namespace,
                    "temporary_keys_cleaned": True,
                    "shared_system_redis_untouched": True,
                    "shared_system_redis_ping_before":
                        shared_redis_ping_before,
                    "shared_system_redis_ping_after":
                        shared_redis_ping_after,
                },
                "policy": {
                    "lookup_enablement_authorized": False,
                    "lookup_exposure_changed": False,
                    "shared_redis_stopped": False,
                    "shared_redis_flushed": False,
                    "application_configuration_changed": False,
                    "database_writes_attempted": False,
                    "project_changes_attempted": False,
                    "android_changes_attempted": False,
                },
                "remaining_production_gates": [
                    "production Redis secret and TLS configuration",
                    "production persistence and failover policy",
                    "external log collection and alert routing",
                    "separate lookup-enablement authorization",
                ],
                "elapsed_ms": round(
                    (time.perf_counter() - started)
                    * 1000,
                    3,
                ),
            }
            print(json.dumps(report, indent=2, sort_keys=True))
            print(
                "NWDP MULTI-REPLICA REDIS FAILOVER GATE PASSED; "
                "LOOKUP REMAINS DISABLED"
            )
        finally:
            if temporary_process is not None:
                stop_temporary_redis(temporary_process)

    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
