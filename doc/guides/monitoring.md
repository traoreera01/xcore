# Monitoring and Observability

XCore provides a comprehensive observability system to monitor your plugins and services in production.

## Overview

The XCore observability system comprises four pillars:

1. **Metrics** — Counters, gauges, and histograms to measure performance
2. **Health Checks** — Verification of service health
3. **Logging** — Structured logging with configurable levels
4. **Tracing** — Distributed tracing for debugging

## Metrics

The metrics registry supports three types of metrics:

- **Counter** — Values that increment (e.g., number of requests)
- **Gauge** — Values that go up or down (e.g., number of connections)
- **Histogram** — Distribution of values (e.g., request latency)

### Basic Usage

```python
from xcore.kernel.observability.metrics import MetricsRegistry
from xcore.sdk import TrustedBase


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        # Create a metrics registry
        self.metrics = MetricsRegistry()

        # Create metrics
        self.request_count = self.metrics.counter("http.requests.total")
        self.active_connections = self.metrics.gauge("connections.active")
        self.request_latency = self.metrics.histogram("http.request.duration")

    def get_router(self):
        from fastapi import APIRouter, Request
        import time

        router = APIRouter()

        @router.get("/api/data")
        async def get_data(request: Request):
            start = time.monotonic()
            self.active_connections.inc()

            try:
                # Your logic here
                data = await self._fetch_data()

                # Increment request counter
                self.request_count.inc()

                return {"data": data}
            finally:
                # Record latency
                latency = time.monotonic() - start
                self.request_latency.observe(latency)
                self.active_connections.dec()

        return router
```

### Metrics with Labels

```python
class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.metrics = MetricsRegistry()

        # Metrics with labels for better granularity
        self.request_count = self.metrics.counter(
            "http.requests.total",
            labels={"plugin": "my_plugin"}
        )
        self.error_count = self.metrics.counter(
            "http.errors.total",
            labels={"plugin": "my_plugin"}
        )

    def get_router(self):
        from fastapi import APIRouter, Request

        router = APIRouter()

        @router.get("/items/{item_id}")
        async def get_item(item_id: str, request: Request):
            try:
                # Increment with dynamic label
                self.metrics.counter(
                    "http.requests.total",
                    labels={"endpoint": "get_item", "method": "GET"}
                ).inc()

                item = await self._get_item(item_id)
                return item

            except Exception as e:
                # Count errors by type
                self.metrics.counter(
                    "http.errors.total",
                    labels={"endpoint": "get_item", "error_type": type(e).__name__}
                ).inc()
                raise

        return router
```

### Exposing Metrics

```python
def get_router(self):
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/metrics")
    async def get_metrics():
        """Expose metrics in JSON format."""
        return self.metrics.snapshot()

    return router
```

### Example Output

```json
{
  "counters": {
    "http.requests.total:{\"plugin\": \"my_plugin\"}": 42,
    "http.requests.total:{\"endpoint\": \"get_item\", \"method\": \"GET\"}": 15
  },
  "gauges": {
    "connections.active:{}": 5,
    "memory.usage_mb:{}": 128.5
  },
  "histograms": {
    "http.request.duration": {
      "count": 42,
      "sum": 0.840,
      "mean": 0.020
    }
  }
}
```

## Health Checks

The health check system allows verifying the health status of components.

### Creating Checks

```python
from xcore.kernel.observability.health import HealthChecker, HealthStatus
from xcore.sdk import TrustedBase


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.db = self.get_service("db")
        self.cache = self.get_service("cache")

        # Create health checker
        self.health = HealthChecker()

        # Register checks
        @self.health.register("database")
        async def check_database():
            try:
                with self.db.session() as session:
                    session.execute("SELECT 1")
                return True, "Database connection OK"
            except Exception as e:
                return False, str(e)

        @self.health.register("cache")
        def check_cache():
            try:
                self.cache.set("health_check", "ok", ttl=1)
                return True, "Cache connection OK"
            except Exception as e:
                return False, str(e)

        @self.health.register("external_api")
        async def check_external_api():
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        "https://api.example.com/health",
                        timeout=5.0
                    )
                return response.status_code == 200, f"Status: {response.status_code}"
            except Exception as e:
                return False, str(e)

    def get_router(self):
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/health")
        async def health_check():
            """Health check endpoint."""
            report = await self.health.run_all(timeout=5.0)

            status_code = 200
            if report["status"] == "unhealthy":
                status_code = 503
            elif report["status"] == "degraded":
                status_code = 200  # or 429 according to your needs

            return JSONResponse(
                content=report,
                status_code=status_code
            )

        return router
```

### Report Structure

```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "status": "healthy",
      "message": "Database connection OK",
      "duration_ms": 12.34
    },
    "cache": {
      "status": "healthy",
      "message": "Cache connection OK",
      "duration_ms": 2.15
    },
    "external_api": {
      "status": "degraded",
      "message": "Timeout after 5s",
      "duration_ms": 5001.42
    }
  }
}
```

## Logging

XCore provides a centralized logging configuration.

### Configuration

```yaml
# integration.yaml
logging:
  level: INFO                    # DEBUG, INFO, WARNING, ERROR, CRITICAL
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/xcore.log"          # Optional: log file
  max_bytes: 10485760             # 10 MB rotation
  backup_count: 5                 # Number of backup files
```

### Usage in Plugins

```python
from xcore.kernel.observability.logging import get_logger
from xcore.sdk import TrustedBase

# Create a logger for your plugin
logger = get_logger("my_plugin")


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        logger.info("Plugin my_plugin loaded successfully")

        try:
            self.db = self.get_service("db")
            logger.debug("Database service connected")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def handle(self, action: str, payload: dict) -> dict:
        logger.debug(f"Handling action: {action}", extra={"payload": payload})

        try:
            result = await self._process_action(action, payload)
            logger.info(f"Action {action} completed successfully")
            return ok(result=result)
        except ValueError as e:
            logger.warning(f"Validation error in action {action}: {e}")
            return error(str(e), code="validation_error")
        except Exception as e:
            logger.exception(f"Unexpected error in action {action}")
            return error("Internal error", code="internal_error")
```

### Best Practices for Logging

```python
# ❌ Bad
logger.info("User " + user_id + " logged in")
logger.info(f"Request took {end - start} seconds")

# ✅ Good
logger.info("User logged in", extra={"user_id": user_id})
logger.info("Request completed", extra={"duration_ms": (end - start) * 1000})

# ❌ Bad
try:
    risky_operation()
except Exception as e:
    logger.error(f"Error: {e}")  # Stack trace lost

# ✅ Good
try:
    risky_operation()
except Exception:
    logger.exception("Operation failed")  # Captures the stack trace
```

## Tracing

The tracing system allows tracking requests across different components.

### Basic Usage

```python
from xcore.kernel.observability.tracing import Tracer
from xcore.sdk import TrustedBase


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        self.tracer = Tracer(service_name="my_plugin")

    async def handle(self, action: str, payload: dict) -> dict:
        with self.tracer.span("handle_action", action=action) as span:
            span.set_attribute("payload_size", len(str(payload)))

            # Sub-operation 1
            with self.tracer.span("validate_input") as val_span:
                validated = await self._validate(payload)
                val_span.set_attribute("validation_time_ms", validated.duration)

            # Sub-operation 2
            with self.tracer.span("process_request") as proc_span:
                try:
                    result = await self._process(validated)
                    proc_span.set_attribute("result_size", len(str(result)))
                except Exception as e:
                    proc_span.set_status("error")
                    proc_span.set_attribute("error.message", str(e))
                    raise

            return ok(result=result)
```

### Exporting Traces

```python
def get_router(self):
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/traces")
    async def get_traces():
        """Export collected traces."""
        return {"spans": self.tracer.export()}

    return router
```

### Example Trace

```json
{
  "spans": [
    {
      "name": "handle_action",
      "trace_id": "a1b2c3d4e5f6...",
      "span_id": "1234567890abcd",
      "duration_ms": 45.2,
      "status": "ok",
      "attributes": {
        "action": "create_user",
        "payload_size": 256
      }
    },
    {
      "name": "validate_input",
      "trace_id": "a1b2c3d4e5f6...",
      "span_id": "fedcba098765...",
      "duration_ms": 2.1,
      "status": "ok",
      "attributes": {
        "validation_time_ms": 1.8
      }
    }
  ]
}
```

## Complete Example

```python
from xcore.kernel.observability.health import HealthChecker
from xcore.kernel.observability.logging import get_logger
from xcore.kernel.observability.metrics import MetricsRegistry
from xcore.kernel.observability.tracing import Tracer
from xcore.sdk import TrustedBase, ok, error


logger = get_logger("api_plugin")


class Plugin(TrustedBase):

    async def on_load(self) -> None:
        # Initialize services
        self.db = self.get_service("db")
        self.cache = self.get_service("cache")

        # Initialize observability
        self.metrics = MetricsRegistry()
        self.health = HealthChecker()
        self.tracer = Tracer(service_name="api_plugin")

        # Metrics
        self.request_count = self.metrics.counter(
            "api.requests.total",
            labels={"plugin": "api_plugin"}
        )
        self.request_latency = self.metrics.histogram("api.request.duration")

        # Health checks
        @self.health.register("database")
        async def check_db():
            try:
                with self.db.session() as session:
                    session.execute("SELECT 1")
                return True, "Database OK"
            except Exception as e:
                return False, str(e)

        @self.health.register("cache")
        def check_cache():
            try:
                self.cache.set("health_check", "ok", ttl=1)
                return True, "Cache OK"
            except Exception as e:
                return False, str(e)

        logger.info("API plugin initialized")

    def get_router(self):
        from fastapi import APIRouter, Request, HTTPException
        import time

        router = APIRouter()

        @router.get("/users/{user_id}")
        async def get_user(user_id: str, request: Request):
            """Fetch a user with full monitoring."""
            start_time = time.monotonic()

            with self.tracer.span("get_user", user_id=user_id) as span:
                try:
                    # Metrics
                    self.request_count.inc()

                    # Cache lookup
                    with self.tracer.span("cache_lookup"):
                        cached = await self.cache.get(f"user:{user_id}")
                        if cached:
                            span.set_attribute("cache_hit", True)
                            return {"user": cached, "cached": True}

                        span.set_attribute("cache_hit", False)

                    # Database lookup
                    with self.tracer.span("db_query") as db_span:
                        with self.db.session() as session:
                            result = session.execute(
                                "SELECT * FROM users WHERE id = :id",
                                {"id": user_id}
                            )
                            user = result.fetchone()

                            if not user:
                                raise HTTPException(404, "User not found")

                            db_span.set_attribute("rows_returned", 1)

                    # Cache result
                    await self.cache.set(f"user:{user_id}", dict(user), ttl=300)

                    # Latency
                    latency = time.monotonic() - start_time
                    self.request_latency.observe(latency)

                    return {"user": dict(user), "cached": False}

                except HTTPException:
                    raise
                except Exception as e:
                    logger.exception(f"Error fetching user {user_id}")
                    span.set_status("error")
                    span.set_attribute("error.message", str(e))
                    raise HTTPException(500, "Internal error")

        @router.get("/health")
        async def health():
            """Health check endpoint."""
            return await self.health.run_all()

        @router.get("/metrics")
        async def metrics():
            """Metrics endpoint."""
            return self.metrics.snapshot()

        return router
```

## Monitoring Dashboard

Here is a simple HTML dashboard example to visualize metrics:

```python
@router.get("/dashboard")
async def dashboard():
    """Simple monitoring dashboard."""
    health = await self.health.run_all()
    metrics = self.metrics.snapshot()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Monitoring Dashboard</title>
        <style>
            body {{ font-family: system-ui, sans-serif; padding: 20px; }}
            .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 20px; margin: 10px 0; }}
            .healthy {{ border-left: 4px solid #22c55e; }}
            .degraded {{ border-left: 4px solid #f59e0b; }}
            .unhealthy {{ border-left: 4px solid #ef4444; }}
            pre {{ background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <h1>Monitoring Dashboard</h1>

        <div class="card {health['status']}">
            <h2>Health Status: {health['status'].upper()}</h2>
            <pre>{json.dumps(health, indent=2)}</pre>
        </div>

        <div class="card">
            <h2>Metrics</h2>
            <pre>{json.dumps(metrics, indent=2)}</pre>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
```

## Alerting

Example of basic alert implementation:

```python
import asyncio
from datetime import datetime


class MonitoringAlerts:

    def __init__(self, metrics: MetricsRegistry, health: HealthChecker):
        self.metrics = metrics
        self.health = health
        self.alerts = []

    async def check_thresholds(self):
        """Check alert thresholds."""
        snapshot = self.metrics.snapshot()

        # Alert: high HTTP errors
        error_count = snapshot["counters"].get("http.errors.total:{}", 0)
        if error_count > 100:
            await self.send_alert(
                "high_error_rate",
                f"Error count is high: {error_count}"
            )

        # Alert: high latency
        latency = snapshot["histograms"].get("http.request.duration", {})
        if latency.get("mean", 0) > 1.0:  # > 1 second
            await self.send_alert(
                "high_latency",
                f"Mean latency is {latency['mean']:.3f}s"
            )

    async def send_alert(self, alert_type: str, message: str):
        """Send an alert."""
        alert = {
            "type": alert_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.alerts.append(alert)

        # Send to Slack, PagerDuty, etc.
        logger.error(f"ALERT [{alert_type}]: {message}")

    async def run_checks(self, interval: int = 60):
        """Run checks periodically."""
        while True:
            await self.check_thresholds()
            await asyncio.sleep(interval)
```

## Prometheus Integration

To export to Prometheus, create a compatible endpoint:

```python
@router.get("/prometheus")
async def prometheus_metrics():
    """Export metrics in Prometheus format."""
    snapshot = self.metrics.snapshot()

    output = []

    # Counters
    for key, value in snapshot["counters"].items():
        name, labels = key.split(":", 1)
        labels_dict = eval(labels) if labels != "{}" else {}
        label_str = ",".join(f'{k}="{v}"' for k, v in labels_dict.items())
        output.append(f"# HELP {name} Counter metric")
        output.append(f"# TYPE {name} counter")
        output.append(f"{name}{{{label_str}}} {value}")

    # Gauges
    for key, value in snapshot["gauges"].items():
        name, labels = key.split(":", 1)
        labels_dict = eval(labels) if labels != "{}" else {}
        label_str = ",".join(f'{k}="{v}"' for k, v in labels_dict.items())
        output.append(f"# HELP {name} Gauge metric")
        output.append(f"# TYPE {name} gauge")
        output.append(f"{name}{{{label_str}}} {value}")

    return Response(content="\n".join(output), media_type="text/plain")
```

## Best Practices

1. **Metrics**
   - Use descriptive names with prefixes (e.g., `http_requests_total`)
   - Add labels to allow aggregation
   - Avoid overly high cardinalities (millions of unique values)

2. **Health Checks**
   - Keep checks fast (< 5 seconds)
   - Verify critical dependencies only
   - Return appropriate HTTP codes

3. **Logging**
   - Use the right log level (DEBUG for dev, INFO/ERROR for prod)
   - Structure your logs with extra fields
   - Avoid logging sensitive data

4. **Tracing**
   - Create spans for slow operations (> 10ms)
   - Add relevant attributes for debugging
   - Propagate trace_ids between services

## Monitoring with EventBus

The EventBus allows monitoring system events in real-time.

### Subscribing to System Events

```python
from xcore.sdk import TrustedBase


class MonitoringPlugin(TrustedBase):
    """Monitoring plugin via EventBus."""

    async def on_load(self) -> None:
        self.events = self.ctx.events
        self.metrics = MetricsRegistry()

        # Create metrics
        self.event_counter = self.metrics.counter("events.total")
        self.event_latency = self.metrics.histogram("event.processing.duration")

        # Subscribe to system events
        self.events.on("plugin.*.loaded", self._on_plugin_loaded)
        self.events.on("plugin.*.error", self._on_plugin_error)
        self.events.on("service.*.error", self._on_service_error)

        # Performance monitoring
        self.events.on("request.start", self._on_request_start, priority=100)
        self.events.on("request.end", self._on_request_end, priority=10)

        self._request_timings = {}

    async def _on_plugin_loaded(self, event):
        """Log plugin loading."""
        logger.info(
            f"Plugin {event.name} loaded",
            extra={"source": event.source, "data": event.data}
        )
        self.event_counter.inc()

    async def _on_plugin_error(self, event):
        """Log plugin errors."""
        logger.error(
            f"Plugin error: {event.data.get('error')}",
            extra={
                "plugin": event.data.get("plugin"),
                "action": event.data.get("action"),
                "error": event.data.get("error")
            }
        )

        # Emit an alert
        await self.events.emit("alert.critical", {
            "type": "plugin_error",
            "message": event.data.get("error"),
            "timestamp": time.time()
        })

    async def _on_service_error(self, event):
        """Log service errors."""
        logger.error(
            f"Service {event.data.get('service')} error",
            extra={"error": event.data.get("error")}
        )

    async def _on_request_start(self, event):
        """Start request timing."""
        request_id = event.data.get("request_id")
        self._request_timings[request_id] = time.monotonic()

    async def _on_request_end(self, event):
        """Finish timing and record metrics."""
        request_id = event.data.get("request_id")
        start_time = self._request_timings.pop(request_id, None)

        if start_time:
            duration = time.monotonic() - start_time
            self.event_latency.observe(duration)

            # Alert if latency is too high
            if duration > 1.0:  # > 1 second
                await self.events.emit("alert.warning", {
                    "type": "high_latency",
                    "duration": duration,
                    "request_id": request_id
                })

    async def on_unload(self) -> None:
        """Clean up subscriptions."""
        self.events.unsubscribe("plugin.*.loaded", self._on_plugin_loaded)
        self.events.unsubscribe("plugin.*.error", self._on_plugin_error)
        self.events.unsubscribe("service.*.error", self._on_service_error)
```

### Emitting Monitoring Events

```python
class MonitoredPlugin(TrustedBase):
    """Plugin that emits monitoring events."""

    def get_router(self):
        from fastapi import APIRouter, Request
        import uuid

        router = APIRouter()

        @router.get("/items/{item_id}")
        async def get_item(item_id: str, request: Request):
            request_id = str(uuid.uuid4())

            # Emit request start
            await self.ctx.events.emit("request.start", {
                "request_id": request_id,
                "method": "GET",
                "path": f"/items/{item_id}",
                "client_ip": request.client.host
            })

            try:
                item = await self._fetch_item(item_id)

                # Emit request end
                await self.ctx.events.emit("request.end", {
                    "request_id": request_id,
                    "status": "success",
                    "item_found": item is not None
                })

                return {"item": item}

            except Exception as e:
                # Emit error
                await self.ctx.events.emit("request.end", {
                    "request_id": request_id,
                    "status": "error",
                    "error": str(e)
                })
                raise

        return router
```

## Monitoring with HookManager

The HookManager allows creating monitoring points in the execution flow.

### Monitoring Hooks

```python
from xcore.kernel.events.hooks import HookManager
from xcore.sdk import TrustedBase


class HookMonitoringPlugin(TrustedBase):
    """Monitoring plugin via HookManager."""

    async def on_load(self) -> None:
        self.hooks = HookManager()
        self.metrics = MetricsRegistry()

        # Register monitoring hooks
        @self.hooks.on("api.request", priority=100)
        async def track_request(event):
            """Track API requests."""
            self.metrics.counter("api.requests", labels={
                "method": event.data.get("method"),
                "endpoint": event.data.get("endpoint")
            }).inc()

        @self.hooks.on("db.query", priority=50)
        async def track_db_query(event):
            """Track DB queries."""
            start = time.monotonic()

            # The hook runs before the query
            # We can add a callback for after
            event.data["_start_time"] = start

            # Return a callback to be executed after
            return {"start_time": start}

        @self.hooks.on("db.query.complete", priority=50)
        async def track_db_complete(event):
            """Track DB query completion."""
            start_time = event.data.get("start_time")
            if start_time:
                duration = time.monotonic() - start_time
                self.metrics.histogram("db.query.duration").observe(duration)

        @self.hooks.on("cache.miss", priority=10)
        async def track_cache_miss(event):
            """Track cache misses."""
            self.metrics.counter("cache.miss", labels={
                "key": event.data.get("key")
            }).inc()

    async def emit_monitored_event(self, event_name: str, data: dict):
        """Emit an event with monitoring."""
        results = await self.hooks.emit(event_name, data)

        # Analyze hook results
        for result in results:
            if result.error:
                logger.error(f"Hook {result.hook_name} failed: {result.error}")

        return results
```

### Monitoring Interceptors

```python
class InterceptorMonitoringPlugin(TrustedBase):
    """Monitoring with interceptors."""

    async def on_load(self) -> None:
        self.hooks = HookManager()
        self.metrics = MetricsRegistry()

        # Pre-execution interceptor
        async def pre_interceptor(event):
            """Executed before hooks."""
            event.data["_monitor_start"] = time.monotonic()
            return InterceptorResult.CONTINUE

        # Post-execution interceptor
        async def post_interceptor(event, results):
            """Executed after hooks."""
            start = event.data.get("_monitor_start")
            if start:
                duration = time.monotonic() - start

                # Record metrics
                self.metrics.histogram("hook.execution.duration").observe(duration)

                # Alert if too slow
                if duration > 0.1:  # > 100ms
                    logger.warning(
                        f"Slow hook execution: {duration:.3f}s",
                        extra={"event": event.name}
                    )

        # Register interceptors
        self.hooks.register_pre_interceptor("api.*", pre_interceptor)
        self.hooks.register_post_interceptor("api.*", post_interceptor)
```

### Pattern: Wildcards for Global Monitoring

```python
class GlobalMonitoringPlugin(TrustedBase):
    """Global monitoring with wildcards."""

    async def on_load(self) -> None:
        self.hooks = HookManager()

        # Intercept all events
        @self.hooks.on("*", priority=1)  # Low priority = runs last
        async def global_monitor(event):
            """Monitor all events."""
            logger.debug(
                f"Event: {event.name}",
                extra={
                    "event_name": event.name,
                    "data_keys": list(event.data.keys()),
                    "cancelled": event.cancelled
                }
            )

        # Monitor errors only
        @self.hooks.on("*.error", priority=100)
        async def error_monitor(event):
            """Monitor all errors."""
            logger.error(
                f"Error event: {event.name}",
                extra={
                    "error": event.data.get("error"),
                    "stack": event.data.get("stack_trace")
                }
            )

            # Send alert if critical error
            if event.data.get("critical"):
                await self._send_alert(event)
```

## EventBus + HookManager Integration

Use both systems together for complete monitoring:

```python
class CompleteMonitoringPlugin(TrustedBase):
    """Complete monitoring plugin."""

    async def on_load(self) -> None:
        self.events = self.ctx.events
        self.hooks = HookManager()
        self.metrics = MetricsRegistry()

        # EventBus for inter-plugin communication
        self.events.on("monitoring.metrics.request", self._on_metrics_request)
        self.events.on("monitoring.health.request", self._on_health_request)

        # HookManager for internal monitoring
        @self.hooks.on("plugin.action")
        async def monitor_plugin_action(event):
            start = time.monotonic()

            # Publish via EventBus
            await self.events.emit("action.started", {
                "plugin": event.data.get("plugin"),
                "action": event.data.get("action")
            })

            # Wait for completion (via callback or other mechanism)
            return {"start_time": start}

    async def _on_metrics_request(self, event):
        """Respond to metrics requests."""
        await self.events.emit("monitoring.metrics.response", {
            "request_id": event.data.get("request_id"),
            "metrics": self.metrics.snapshot()
        })

    async def _on_health_request(self, event):
        """Respond to health check requests."""
        await self.events.emit("monitoring.health.response", {
            "request_id": event.data.get("request_id"),
            "status": await self._check_health()
        })
```

## Real-time Monitoring Dashboard

```python
class MonitoringDashboardPlugin(TrustedBase):
    """Dashboard with SSE for real-time."""

    async def on_load(self) -> None:
        self.events = self.ctx.events
        self.subscribers = []

        # Subscribe to system events
        self.events.on("*", self._broadcast_event)

    async def _broadcast_event(self, event):
        """Broadcast events to subscribers."""
        message = json.dumps({
            "event": event.name,
            "data": event.data,
            "timestamp": time.time()
        })

        for queue in self.subscribers:
            await queue.put(message)

    def get_router(self):
        from fastapi import APIRouter
        from fastapi.responses import StreamingResponse
        import asyncio

        router = APIRouter()

        @router.get("/events/stream")
        async def event_stream():
            """SSE event stream."""
            queue = asyncio.Queue()
            self.subscribers.append(queue)

            async def generate():
                try:
                    while True:
                        message = await queue.get()
                        yield f"data: {message}\n\n"
                finally:
                    self.subscribers.remove(queue)

            return StreamingResponse(
                generate(),
                media_type="text/event-stream"
            )

        return router
```

## Next Steps

- [Services](./services.md) — Use cache and database services
- [Security](./security.md) — Secure your monitoring endpoints
- [Events](./events.md) — Complete event system
- [Deployment](../deployment/guide.md) — Deploy with monitoring in production
