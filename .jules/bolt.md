## 2025-03-04 - [Optimization of EventBus dispatch overhead]
**Learning:** `inspect.iscoroutinefunction` is surprisingly expensive when called in hot paths like event emission or permission checks (~30x slower than a boolean check). Furthermore, creating per-emission wrapper coroutines for synchronous handlers significantly increases dispatch latency and GC pressure.
**Action:** Always pre-calculate and cache the `is_async` status of callable handlers during the registration/subscription phase. In emission loops, use this cached flag to branch between direct calls and `await` calls to minimize overhead.

## 2025-03-05 - [Optimization of AutoDispatchMixin lookup overhead]
**Learning:** Using `dir(self)` and `getattr()` in a loop to find methods with specific attributes (like `_xcore_action`) during every request/dispatch is an O(N*M) operation that scales poorly with the number of methods (N) and attribute count (M). In a plugin with 1000 methods, this can take ~370us per dispatch.
**Action:** Implement lazy instance-level caching for metadata-based method lookups. Store the mapping in an internal attribute (e.g., `_xcore_action_cache`) on the first call to reduce subsequent lookups to O(1) dictionary access (~1.8us), yielding a ~200x speedup in hot dispatch paths.
