# Scaling and High Availability

This guide covers scaling strategies for deploying XCore in production with high availability.

## Overview

XCore supports several deployment modes:

- **Single Instance** — Development and small loads
- **Multi-Instance** — Horizontal scaling with a load balancer
- **Cluster Mode** — Multiple nodes with coordination

## Scaling Architecture

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │ (Nginx/HAProxy) │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
   ┌────▼────┐         ┌────▼────┐         ┌────▼────┐
   │ XCore 1 │         │ XCore 2 │         │ XCore 3 │
   │         │         │         │         │         │
   │ Plugins │         │ Plugins │         │ Plugins │
   └────┬────┘         └────┬────┘         └────┬────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Redis Cluster  │
                    │ (Cache + Queue) │
                    └─────────────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
       ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
       │  PostgreSQL │ │  PostgreSQL │ │  PostgreSQL │
       │   Primary   │ │   Replica   │ │   Replica   │
       └─────────────┘ └─────────────┘ └─────────────┘
```

## Multi-Instance Configuration

### 1. Load Balancer (Nginx)

```nginx
# /etc/nginx/conf.d/xcore.conf
upstream xcore_backend {
    least_conn;  # Load balancing by connection

    server 192.168.1.10:8080 weight=5;
    server 192.168.1.11:8080 weight=5;
    server 192.168.1.12:8080 weight=5 backup;

    keepalive 32;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://xcore_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://xcore_backend/health;
        access_log off;
    }
}
```

### 2. Redis Cluster Configuration

```yaml
# integration.yaml
services:
  cache:
    backend: redis
    url: "redis://redis-cluster:6379"
    cluster:
      enabled: true
      nodes:
        - "redis://192.168.1.20:6379"
        - "redis://192.168.1.21:6379"
        - "redis://192.168.1.22:6379"
      options:
        max_redirects: 5
        skip_full_coverage_check: false

  scheduler:
    enabled: true
    backend: redis
    url: "redis://redis-cluster:6379"
    job_coalesce: false
    max_instances: 3
```

### 3. Database with Replication

```yaml
services:
  databases:
    primary:
      type: postgresql
      url: "${DATABASE_PRIMARY_URL}"
      pool_size: 20
      max_overflow: 10

    replica1:
      type: postgresql
      url: "${DATABASE_REPLICA1_URL}"
      pool_size: 10
      read_only: true

    replica2:
      type: postgresql
      url: "${DATABASE_REPLICA2_URL}"
      pool_size: 10
      read_only: true
```

## Session Distribution

### Redis Sessions

```python
# Distributed sessions configuration
# integration.yaml
plugins:
  session_manager:
    backend: redis
    redis_url: "${REDIS_URL}"
    key_prefix: "session:"
    ttl: 3600  # 1 hour
```

### Session Plugin

```python
# plugins/session_manager/main.py
from xcore.sdk import TrustedBase, ok
import json


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.cache = self.get_service("cache")
        self.prefix = self.config.get("key_prefix", "session:")
        self.ttl = self.config.get("ttl", 3600)

    async def handle(self, action: str, payload: dict) -> dict:
        if action == "get_session":
            session_id = payload["session_id"]
            data = await self.cache.get(f"{self.prefix}{session_id}")
            return ok(session=json.loads(data) if data else None)

        if action == "set_session":
            session_id = payload["session_id"]
            data = payload["data"]
            await self.cache.set(
                f"{self.prefix}{session_id}",
                json.dumps(data),
                ttl=self.ttl
            )
            return ok(saved=True)

        if action == "delete_session":
            session_id = payload["session_id"]
            await self.cache.delete(f"{self.prefix}{session_id}")
            return ok(deleted=True)

        return ok()
```

## Distributed Task Queue

### Celery Configuration with Redis

```python
# myapp/tasks/celery_config.py
from celery import Celery

app = Celery("xcore")
app.conf.update(
    broker_url="redis://redis-cluster:6379/0",
    result_backend="redis://redis-cluster:6379/1",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker configuration
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    # Retry
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
```

### Queue Service

```python
# myapp/services/task_queue.py
from xcore.services.base import BaseService, ServiceStatus
from celery import Celery


class TaskQueueService(BaseService):
    """Task queue service with Celery."""

    name = "task_queue"

    def __init__(self, config: dict) -> None:
        super().__init__()
        self.broker_url = config["broker_url"]
        self.backend_url = config["backend_url"]
        self._app = None

    async def init(self) -> None:
        self._status = ServiceStatus.INITIALIZING

        self._app = Celery("xcore")
        self._app.conf.update(
            broker_url=self.broker_url,
            result_backend=self.backend_url,
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
        )

        self._status = ServiceStatus.READY

    async def shutdown(self) -> None:
        self._status = ServiceStatus.STOPPED

    async def health_check(self) -> tuple[bool, str]:
        try:
            # Check broker connection
            conn = self._app.connection()
            conn.ensure_connection(max_retries=1)
            return True, "Broker connection OK"
        except Exception as e:
            return False, str(e)

    def status(self) -> dict:
        return {
            "name": self.name,
            "status": self._status.value,
            "broker": self.broker_url,
        }

    def send_task(self, name: str, args: tuple = (), kwargs: dict = None, queue: str = "default") -> str:
        """Send a task."""
        result = self._app.send_task(
            name,
            args=args,
            kwargs=kwargs or {},
            queue=queue
        )
        return result.id

    def get_result(self, task_id: str, timeout: int = 10):
        """Get the result of a task."""
        result = self._app.AsyncResult(task_id)
        return result.get(timeout=timeout)
```

## Load Balancing with Health Checks

### Distributed Health Check Plugin

```python
# plugins/health_monitor/main.py
from xcore.sdk import TrustedBase, ok
import asyncio
import time


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.cache = self.get_service("cache")
        self.instance_id = self._generate_instance_id()
        self.heartbeat_task = None

    async def on_unload(self) -> None:
        if self.heartbeat_task:
            self.heartbeat_task.cancel()

    def _generate_instance_id(self) -> str:
        import uuid
        return f"xcore-{uuid.uuid4().hex[:8]}"

    async def _heartbeat_loop(self):
        """Send a heartbeat periodically."""
        while True:
            try:
                await self.cache.set(
                    f"health:{self.instance_id}",
                    {
                        "timestamp": time.time(),
                        "status": "healthy",
                        "load": self._get_load()
                    },
                    ttl=30
                )
            except Exception as e:
                print(f"Heartbeat error: {e}")

            await asyncio.sleep(10)

    def _get_load(self) -> dict:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
        }

    def get_router(self):
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/cluster/health")
        async def cluster_health():
            """Health status of the entire cluster."""
            # Retrieve all heartbeats
            keys = await self.cache.keys("health:*")
            instances = []

            for key in keys:
                data = await self.cache.get(key)
                if data:
                    instance_id = key.split(":")[1]
                    instances.append({
                        "instance_id": instance_id,
                        **data
                    })

            # Check for missing instances
            now = time.time()
            healthy = [i for i in instances if now - i["timestamp"] < 30]

            return {
                "total_instances": len(instances),
                "healthy_instances": len(healthy),
                "instances": healthy
            }

        return router
```

## Distributed Rate Limiting

### Rate Limiter with Redis

```python
# plugins/rate_limiter/main.py
from xcore.sdk import TrustedBase, ok
import time


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.cache = self.get_service("cache")

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, dict]:
        """Check if a request respects the rate limit."""
        now = int(time.time())
        window_start = now - (now % window)
        cache_key = f"ratelimit:{key}:{window_start}"

        # Increment counter
        current = await self.cache.increment(cache_key, 1)

        # Set expiration if new window
        if current == 1:
            await self.cache.expire(cache_key, window)

        remaining = max(0, limit - current)
        reset_time = window_start + window

        return (
            current <= limit,
            {
                "limit": limit,
                "remaining": remaining,
                "reset": reset_time,
                "current": current
            }
        )

    async def handle(self, action: str, payload: dict) -> dict:
        if action == "check":
            allowed, info = await self.check_rate_limit(
                payload["key"],
                payload["limit"],
                payload["window"]
            )
            return ok(allowed=allowed, **info)

        return ok()
```

## Circuit Breaker

### Circuit Breaker Pattern

```python
# myapp/utils/circuit_breaker.py
from enum import Enum
import time
import asyncio
from typing import Callable


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker pattern for resilience."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            # Check if can pass to half-open
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
        return self._state

    async def call(self, func: Callable, *args, **kwargs):
        """Call a function with circuit breaker."""
        current_state = self.state

        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpen(f"Circuit {self.name} is OPEN")

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitBreakerOpen(f"Circuit {self.name} half-open limit reached")
            self._half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_calls:
                self._reset()
        else:
            self._failure_count = 0

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def _reset(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0


class CircuitBreakerOpen(Exception):
    pass
```

### Usage in a Plugin

```python
from xcore.sdk import TrustedBase, ok
from myapp.utils.circuit_breaker import CircuitBreaker
import httpx


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        # Circuit breaker for external API
        self.api_breaker = CircuitBreaker(
            name="external_api",
            failure_threshold=3,
            recovery_timeout=30.0
        )

    async def call_external_api(self, endpoint: str):
        """Call external API with circuit breaker."""
        async def _call():
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.example.com/{endpoint}",
                    timeout=5.0
                )
                response.raise_for_status()
                return response.json()

        return await self.api_breaker.call(_call)
```

## Auto-Scaling

### Scaling Metrics

```python
# plugins/scaling_controller/main.py
from xcore.sdk import TrustedBase, ok
import asyncio
import time


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.cache = self.get_service("cache")
        self.metrics_key = "scaling:metrics"

    def get_router(self):
        from fastapi import APIRouter
        import psutil

        router = APIRouter()

        @router.get("/metrics/scaling")
        async def scaling_metrics():
            """Metrics for auto-scaling."""
            return {
                "timestamp": time.time(),
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory": {
                    "percent": psutil.virtual_memory().percent,
                    "available_mb": psutil.virtual_memory().available // 1024 // 1024,
                },
                "disk": {
                    "percent": psutil.disk_usage("/").percent,
                },
                "connections": len(psutil.net_connections()),
                "load_average": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
            }

        @router.post("/metrics/report")
        async def report_metrics():
            """Report metrics for aggregation."""
            import socket

            hostname = socket.gethostname()
            metrics = {
                "timestamp": time.time(),
                "hostname": hostname,
                "cpu": psutil.cpu_percent(),
                "memory": psutil.virtual_memory().percent,
            }

            # Store in Redis for aggregation
            await self.cache.set(
                f"{self.metrics_key}:{hostname}",
                metrics,
                ttl=60
            )

            return ok(reported=True)

        return router
```

## Kubernetes Deployment

### Deployment

```yaml
# k8s/xcore-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: xcore
  labels:
    app: xcore
spec:
  replicas: 3
  selector:
    matchLabels:
      app: xcore
  template:
    metadata:
      labels:
        app: xcore
    spec:
      containers:
        - name: xcore
          image: xcore:latest
          ports:
            - containerPort: 8080
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: xcore-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: xcore-secrets
                  key: redis-url
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: xcore
spec:
  selector:
    app: xcore
  ports:
    - port: 80
      targetPort: 8080
  type: LoadBalancer
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: xcore-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: xcore
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

## Best Practices

1. **Stateless Design** — Do not store local state in plugins
2. **External Session** — Use Redis for sessions
3. **Health Checks** — Implement comprehensive health checks
4. **Graceful Shutdown** — Handle SIGTERM signals cleanly
5. **Circuit Breaker** — Protect your external calls
6. **Timeouts** — Always set timeouts
7. **Retry Logic** — Implement retry with backoff

```python
class ResilientPlugin(TrustedBase):
    """Resilient plugin for production."""

    async def on_load(self) -> None:
        self.cache = self.get_service("cache")
        self.db = self.get_service("db")

        # Circuit breakers
        self.breakers = {
            "api": CircuitBreaker("api", failure_threshold=5),
            "db": CircuitBreaker("db", failure_threshold=3),
        }

    async def resilient_operation(self, key: str):
        """Operation with retry and circuit breaker."""
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
        async def _operation():
            return await self.breakers["api"].call(
                self._call_external_api,
                key
            )

        try:
            return await _operation()
        except CircuitBreakerOpen:
            # Fallback to cache
            cached = await self.cache.get(f"fallback:{key}")
            if cached:
                return cached
            raise
```

## Next Steps

- [Creating Services](./creating-services.md) — Create scalable services
- [Monitoring](./monitoring.md) — Observe the cluster
- [Deployment](../deployment/guide.md) — Deployment in production
