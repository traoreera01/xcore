## 2025-03-04 - [Optimization of EventBus dispatch overhead]
**Learning:** `inspect.iscoroutinefunction` is surprisingly expensive when called in hot paths like event emission or permission checks (~30x slower than a boolean check). Furthermore, creating per-emission wrapper coroutines for synchronous handlers significantly increases dispatch latency and GC pressure.
**Action:** Always pre-calculate and cache the `is_async` status of callable handlers during the registration/subscription phase. In emission loops, use this cached flag to branch between direct calls and `await` calls to minimize overhead.

## 2025-03-05 - [Optimization of AutoDispatchMixin with lazy handler caching]
**Learning:** Calling `dir(self)` and repeatedly using `getattr()` in a hot path like `AutoDispatchMixin.handle` (invoked for every plugin action call) is extremely expensive, especially as the number of attributes on the plugin instance grows. It turns an $O(1)$ dispatch into an $O(N)$ operation.
**Action:** Implement lazy caching for action handlers. On the first call to `handle`, populate a `_xcore_action_cache` dictionary by scanning `dir(self)` once. Subsequent calls can then perform a fast $O(1)$ lookup.
