# Thread & Streaming Techniques Reference

Extracted from CodexMonitor + PlanningTreeMain before legacy cleanup.
Use this to rebuild thread system from scratch.

---

## 1. Subprocess JSON-RPC Transport

### 1.1 Startup — line buffering is critical

```python
self._process = subprocess.Popen(
    self._command_args(),
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,          # LINE BUFFERING — without this, streaming stalls
    encoding="utf-8",
)
# Two daemon reader threads: stdout for JSON-RPC, stderr for diagnostics
self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
self._stderr_thread = threading.Thread(target=self._read_stderr_loop, daemon=True)
```

**Why `bufsize=1`:** Without line buffering, the OS buffers subprocess output in 4KB chunks. Streaming deltas arrive as 10–50 byte fragments — they'd sit in the buffer for seconds before flushing. Line buffering forces a flush on every `\n`, which JSON-RPC messages end with.

### 1.2 Crash detection — non-blocking

```python
def is_alive(self) -> bool:
    return self._process is not None and self._process.poll() is None
```

`poll()` returns `None` while alive, exit code when dead. Non-blocking — use this before any send.

### 1.3 Shutdown — graceful escalation

```python
proc.terminate()           # SIGTERM
try:
    proc.wait(timeout=5)   # Give 5 seconds to clean up
except subprocess.TimeoutExpired:
    proc.kill()            # SIGKILL if still alive

# CRITICAL: Fail all pending futures
with self._lock:
    for future in self._pending.values():
        future.set_exception(CodexTransportError("Transport stopped"))
    self._pending.clear()
    # Also fail all turn states
    for state in self._turn_states.values():
        state.error_message = "Transport stopped"
        state.event.set()
    self._turn_states.clear()
```

**Why fail pending futures:** Without this, caller threads block forever on `future.result()`.

---

## 2. JSON-RPC Request/Response Correlation

### 2.1 Monotonic IDs + Future dict

```python
# Send side
with self._lock:
    self._next_id += 1
    request_id = self._next_id

future: Future[dict] = Future()
with self._lock:
    self._pending[request_id] = future

self._send_json({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})

try:
    return future.result(timeout=timeout)
except FutureTimeoutError:
    with self._lock:
        self._pending.pop(request_id, None)  # Clean up on timeout
    raise CodexTransportTimeout(...)
```

### 2.2 Reader-side resolution

```python
# In reader loop, on response message:
message_id = message.get("id")
with self._lock:
    future = self._pending.pop(message_id, None)  # Atomic get+remove

if future is None:
    return  # Orphaned response — ignore

if "error" in message:
    future.set_exception(CodexTransportError(message["error"]))
else:
    future.set_result(message.get("result", {}))
```

**Key:** `pop()` atomically retrieves and removes. Prevents double-resolution.

---

## 3. Streaming Turn State Machine

### 3.1 Per-turn state

```python
@dataclass
class _TurnState:
    event: threading.Event          # Signals turn completion
    stdout_parts: list[str]         # Accumulated text deltas
    final_text: str | None = None
    error_message: str | None = None
    thread_id: str | None = None
    tool_calls: list[dict] = field(default_factory=list)

    # Callbacks — all optional, all guarded
    on_delta: Callable[[str], None] | None = None
    on_tool_call: Callable[[str, dict], None] | None = None
    on_request_user_input: Callable[[dict], None] | None = None
    on_request_resolved: Callable[[dict], None] | None = None
    on_thread_status: Callable[[dict], None] | None = None
```

Each active turn gets its own `_TurnState`. The `threading.Event` is the synchronization primitive — caller blocks on `event.wait(timeout)`, reader thread calls `event.set()` when turn completes.

### 3.2 Delta accumulation + immediate emission

```python
# In notification handler for "item/agentMessage/delta":
state.stdout_parts.append(delta)   # Accumulate for final capture
self._emit_delta(state, delta)      # Stream immediately to callback
```

**Both** accumulate AND stream. Accumulation gives you the final text. Streaming gives you real-time UI.

### 3.3 Safe callback emission

```python
def _emit_delta(self, state: _TurnState, delta: str) -> None:
    callback = state.on_delta
    if callback is None:
        return
    try:
        callback(delta)
    except Exception:
        logger.debug("delta callback failed", exc_info=True)
```

**Three guards on every callback:**
1. Null-check the callback
2. Try-catch to prevent callback errors from crashing the reader thread
3. Log at debug (non-fatal)

This pattern is repeated for ALL callback types. The reader thread must never crash.

### 3.4 Callback replay for late registration

```python
# After installing callbacks on turn state:
state.on_delta = on_delta

# Replay any deltas that arrived before callback was installed
if on_delta is not None and state.stdout_parts:
    for chunk in list(state.stdout_parts):
        self._emit_delta(state, chunk)
```

**Race condition fix:** Between calling `turn/start` RPC and registering the callback, deltas may arrive. Replay them.

---

## 4. Notification Routing — Collect-Under-Lock Pattern

```python
# In notification handler for "thread/status/changed":
with self._lock:
    self._thread_statuses[thread_id] = status_payload
    # Collect matching turn states while locked
    matching_states = [
        state for state in self._turn_states.values()
        if state.thread_id == thread_id
    ]

# Emit AFTER releasing lock — callbacks may be slow, must not block
for state in matching_states:
    self._emit_thread_status(state, status_payload)
```

**Why:** If you emit inside the lock, and the callback tries to call another method that acquires the lock → deadlock. Always collect under lock, emit outside.

---

## 5. Runtime Request Tracking (User Input Requests)

### 5.1 Request lifecycle

```
Codex sends "item/tool/requestUserInput"
  → Create RuntimeRequestRecord (status: "pending")
  → Store in _runtime_request_registry[request_id]
  → Emit on_request_user_input callback
  → Turn PAUSES (waits for resolution)

User provides answers
  → resolve_runtime_request_user_input(request_id, answers)
  → Lock, get RPC request_id, unlock
  → Send JSON-RPC response (CANNOT hold lock during I/O)
  → Lock again, update status="resolved", set timestamp, unlock

Server confirms "serverRequest/resolved"
  → Mark status="stale" (distinguish from client-side "resolved")
  → Emit on_request_resolved callback
```

### 5.2 Lock-release-lock pattern

```python
def resolve_runtime_request_user_input(self, request_id, *, answers):
    # Phase 1: Read under lock
    with self._lock:
        record = self._runtime_request_registry.get(request_id)
        if record is None or record.status != "pending":
            return record
        rpc_request_id = record.rpc_request_id

    # Phase 2: I/O without lock (can't block other threads)
    self._send_response(rpc_request_id, {"answers": answers})

    # Phase 3: Update under lock
    with self._lock:
        record = self._runtime_request_registry.get(request_id)
        record.status = "resolved"
        record.answer_payload = {"answers": answers}
        record.resolved_at = _iso_now()
        return RuntimeRequestRecord(**record.__dict__)  # Defensive copy
```

**Why three phases:** Holding a lock during network I/O is a deadlock risk and blocks all other threads. Extract what you need, release, do I/O, re-acquire, update.

---

## 6. Chat Service — Stale Turn Recovery

### 6.1 The problem

Server crashes while assistant is streaming. On restart, `active_turn_id` is set in persisted state but no background thread is running. Without recovery, the session appears permanently "busy."

### 6.2 Detection: in-memory set vs persisted state

```python
class ChatService:
    _live_turns: set[tuple[str, str, str]]  # (project_id, node_id, turn_id)
```

Background thread adds to `_live_turns` when spawned, removes in `finally` block. If `active_turn_id` is in persisted state but NOT in `_live_turns`, the turn is stale.

### 6.3 Recovery

```python
def _recover_stale_turn(self, project_id, node_id, session) -> bool:
    active_turn_id = session.get("active_turn_id")
    if not active_turn_id:
        return False
    if (project_id, node_id, str(active_turn_id)) in self._live_turns:
        return False  # Still running, don't touch

    # Find the last incomplete assistant message
    for message in reversed(session.get("messages", [])):
        if message.get("role") != "assistant":
            continue
        if message.get("status") not in ("pending", "streaming"):
            continue
        message["status"] = "error"
        message["error"] = "Session interrupted - server restarted before response completed."
        message["updated_at"] = utc_now()
        break  # Only fix the FIRST one found (most recent)

    session["active_turn_id"] = None
    return True  # Caller saves
```

**When to call:** On `GET /chat/session`. Lazy recovery — don't scan all sessions on startup, fix when accessed.

---

## 7. Chat Service — Conflict Prevention

### 7.1 Single active turn per node

```python
def create_message(self, project_id, node_id, content):
    with self._lock:
        # Reject if turn already active
        session = self._load_session(project_id, node_id)
        if session.get("active_turn_id"):
            raise ChatConflictError("chat_turn_in_progress")

        # Create messages and set active_turn_id atomically
        turn_id = new_id("turn")
        user_msg = self._make_user_message(content)
        assistant_msg = self._make_assistant_message(status="pending")
        session["messages"].extend([user_msg, assistant_msg])
        session["active_turn_id"] = turn_id
        self._save_session(project_id, node_id, session)

        # Track in memory
        self._live_turns.add((project_id, node_id, turn_id))

    # Start background thread AFTER releasing lock
    self._start_background_turn(project_id, node_id, turn_id, content, session)
```

**Critical sequence:**
1. Check conflict under lock
2. Write both messages + active_turn_id atomically under lock
3. Add to `_live_turns` under lock
4. Release lock
5. Start daemon thread (never under lock — it runs indefinitely)

### 7.2 Config update blocked during active turn

```python
def update_config(self, project_id, node_id, config_patch):
    with self._lock:
        session = self._load_session(project_id, node_id)
        if session.get("active_turn_id"):
            raise ChatConflictError("chat_turn_in_progress")  # 409
        # Apply config...
```

---

## 8. Background Turn Lifecycle

```python
def _run_background_turn(self, project_id, node_id, turn_id, content, session):
    try:
        # Build prompt with full context
        prompt = self._build_prompt(project_id, node_id, content, session)

        # Resolve thread: reuse or create
        thread_id = session.get("thread_id")
        writable_roots = self._extract_writable_roots(session)

        # Stream response
        result = self._codex_client.send_prompt_streaming(
            prompt,
            thread_id=thread_id,
            timeout_sec=session["config"]["timeout_sec"],
            writable_roots=writable_roots,
            on_delta=lambda delta: self._handle_delta(project_id, node_id, turn_id, delta),
        )

        # SUCCESS: update message and persist thread_id
        with self._lock:
            session = self._load_session(project_id, node_id)
            msg = self._find_assistant_message(session, turn_id)
            msg["content"] = result["stdout"]
            msg["status"] = "completed"
            msg["updated_at"] = utc_now()
            session["thread_id"] = result["thread_id"]  # ONLY persist on success
            session["active_turn_id"] = None
            self._save_session(project_id, node_id, session)

        self._publish_event(project_id, node_id, {
            "type": "assistant_completed",
            "message_id": msg["message_id"],
            "content": result["stdout"],
            "thread_id": result["thread_id"],
        })

    except Exception as exc:
        # ERROR: mark message as error, DON'T update thread_id
        with self._lock:
            session = self._load_session(project_id, node_id)
            msg = self._find_assistant_message(session, turn_id)
            msg["status"] = "error"
            msg["error"] = str(exc)
            msg["updated_at"] = utc_now()
            session["active_turn_id"] = None
            # thread_id NOT updated — preserve last good thread
            self._save_session(project_id, node_id, session)

        self._publish_event(project_id, node_id, {
            "type": "assistant_error",
            "message_id": msg["message_id"],
            "error": str(exc),
        })

    finally:
        # ALWAYS remove from live turns
        self._live_turns.discard((project_id, node_id, turn_id))
```

**Three critical details:**
1. **`thread_id` only persisted on success** — failed turn doesn't corrupt the thread reference
2. **`active_turn_id` cleared in both success and error** — prevents permanent busy state
3. **`_live_turns.discard()` in finally** — guarantees cleanup even on unexpected exceptions

### Delta handling during streaming

```python
def _handle_delta(self, project_id, node_id, turn_id, delta):
    with self._lock:
        session = self._load_session(project_id, node_id)
        msg = self._find_assistant_message(session, turn_id)
        msg["content"] = (msg.get("content") or "") + delta
        msg["status"] = "streaming"
        msg["updated_at"] = utc_now()
        self._save_session(project_id, node_id, session)

    self._publish_event(project_id, node_id, {
        "type": "assistant_delta",
        "message_id": msg["message_id"],
        "delta": delta,
        "content": msg["content"],
    })
```

**Note:** Every delta updates persistent storage. Expensive but crash-safe — if server dies mid-stream, partial content is preserved.

---

## 9. SSE Broker — Async-to-Threading Bridge

### The problem

Codex client callbacks run in a synchronous daemon thread. SSE endpoints are async (FastAPI/Starlette). You need to push events from sync thread → async handler.

### The solution

```python
@dataclass(frozen=True)
class _Subscriber:
    queue: asyncio.Queue[dict]
    loop: asyncio.AbstractEventLoop  # Captured at subscribe time

class EventBroker:
    def __init__(self):
        self._queues: dict[tuple[str, str], set[_Subscriber]] = defaultdict(set)
        self._lock = threading.Lock()

    def subscribe(self, project_id, node_id) -> asyncio.Queue:
        subscriber = _Subscriber(
            queue=asyncio.Queue(),
            loop=asyncio.get_running_loop(),  # Capture current event loop
        )
        with self._lock:
            self._queues[(project_id, node_id)].add(subscriber)
        return subscriber.queue

    def publish(self, project_id, node_id, event):
        with self._lock:
            subscribers = tuple(self._queues.get((project_id, node_id), set()))

        for subscriber in subscribers:
            subscriber.loop.call_soon_threadsafe(  # Thread-safe async enqueue
                self._put_nowait,
                subscriber.queue,
                copy.deepcopy(event),  # Deep copy — event dict shared across subscribers
            )

    @staticmethod
    def _put_nowait(queue, event):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop event on backpressure — don't block publisher
```

**Three key techniques:**
1. **`call_soon_threadsafe()`** — schedules callback on the async event loop from a sync thread
2. **`copy.deepcopy(event)`** — each subscriber gets its own copy (prevents mutation bugs)
3. **`put_nowait` with QueueFull catch** — never block the publishing thread

### SSE endpoint consuming the queue

```python
async def stream_events(request, project_id, node_id):
    queue = broker.subscribe(project_id, node_id)
    try:
        async def event_generator():
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: message\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # Keep connection alive
        return EventSourceResponse(event_generator())
    finally:
        broker.unsubscribe(project_id, node_id, queue)
```

**15-second heartbeat** prevents proxy/browser timeouts.

---

## 10. Node Status Promotion on First Message

```python
def _promote_node_to_running(self, project_id, node_id, session):
    """Called synchronously during create_message, BEFORE background turn starts."""
    snapshot = self._storage.load_snapshot(project_id)
    node = find_node(snapshot, node_id)

    if node["status"] not in ("draft", "ready"):
        return  # Already promoted or done

    node["status"] = "in_progress"
    self._storage.save_snapshot(project_id, snapshot)
    self._publish_project_event(project_id, {
        "type": "node_status_changed",
        "node_id": node_id,
        "status": "in_progress",
    })
```

**Timing matters:** This runs BEFORE the background thread starts, inside the lock. The node is promoted before the first token arrives. If the background turn fails, the node stays `in_progress` — which is correct (the user attempted work).

---

## 11. Prompt Context Assembly

```python
def _build_prompt(self, project_id, node_id, user_content, session):
    project_meta = self._storage.load_project_meta(project_id)
    node_files = self._storage.load_node_files(project_id, node_id)

    context_parts = []

    # Project context
    context_parts.append(f"Project: {project_meta['name']}")
    context_parts.append(f"Root goal: {project_meta['root_goal']}")
    context_parts.append(f"Workspace: {project_meta['workspace_root']}")

    # Node context
    task = node_files.get("task", {})
    context_parts.append(f"Node: {task.get('title', 'Untitled')}")
    if task.get("purpose"):
        context_parts.append(f"Purpose: {task['purpose']}")
    if task.get("responsibility"):
        context_parts.append(f"Responsibility: {task['responsibility']}")

    # Config context
    config = session.get("config", {})
    context_parts.append(f"Access mode: {config.get('access_mode', 'project_write')}")
    context_parts.append(f"Working directory: {config.get('cwd', '')}")
    context_parts.append(f"Timeout: {config.get('timeout_sec', 120)}s")

    # Assemble as hidden system context + user message
    hidden = "\n".join(context_parts)
    return f"{hidden}\n\n---\n\nUser request:\n{user_content}"
```

**Pattern:** Hidden context prepended to user message. Not a system prompt — injected as part of the user turn. This survives thread resumption (system prompts may not persist across `thread/resume`).

---

## 12. Thread Availability Check via Resume

```python
def _thread_is_available(self, thread_id, workspace_root) -> bool:
    try:
        self._codex_client.resume_thread(thread_id, cwd=workspace_root, timeout_sec=15)
        return True
    except CodexTransportError as exc:
        error_msg = str(exc).lower()
        if "not found" in error_msg or "no rollout" in error_msg:
            return False
        raise  # Real error — propagate
```

**Why resume, not a status check:** There is no "is thread alive" RPC. The only way to know is to try resuming it. If it fails with "not found," the thread is gone. Any other error is a real problem.

---

## 13. Atomic File Writes

```python
def atomic_write_json(path: Path, data: dict):
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())  # Force to disk
    tmp_path.replace(path)    # Atomic rename
```

**Why:** If the process crashes during `json.dump()`, you get a corrupt JSON file. With tmp + rename, you either have the old file or the new file — never a partial write. `os.fsync()` forces the OS to flush write buffers before the rename.

---

## 14. Reconciliation on Server Restart

```python
def reconcile_interrupted_turns(self):
    """Called once at server startup. Scans all projects for interrupted turns."""
    for project_id in self._storage.list_project_ids():
        state = self._storage.load_thread_state(project_id)
        did_change = False

        for node_id, node_state in state.items():
            for bucket_name in ("planning", "execution", "ask"):
                bucket = node_state.get(bucket_name, {})
                if bucket.get("status") != "active":
                    continue

                # This turn was active when server died
                did_change = True
                bucket["status"] = "idle"
                bucket["active_turn_id"] = None

                # Optionally append error message to history
                # (for planning turns that need visible error)

        if did_change:
            self._storage.save_thread_state(project_id, state)
```

**Pattern:** On startup, find all "active" states and force them to "idle." The stale turn recovery (§6) handles the per-session cleanup lazily when users access their sessions.

**Two-layer recovery:**
- **Eager (startup):** Reconcile thread state buckets
- **Lazy (on access):** Recover stale chat turns via `_live_turns` set comparison

---

## Summary: Techniques to Preserve

| # | Technique | Why it matters |
|---|-----------|---------------|
| 1 | Line-buffered subprocess | Without it, streaming stalls |
| 2 | Future-based RPC correlation | Clean request/response over stdio |
| 3 | Turn state machine with threading.Event | Synchronizes caller and reader threads |
| 4 | Dual accumulate + emit for deltas | Supports both streaming and final capture |
| 5 | Safe callback emission (null + try-catch) | Reader thread must never crash |
| 6 | Callback replay for late registration | Prevents missed deltas in race window |
| 7 | Collect-under-lock, emit-after-release | Prevents deadlock in notification routing |
| 8 | Lock-release-lock for I/O | Prevents blocking during network calls |
| 9 | `_live_turns` set for stale detection | Asymmetric liveness: memory vs disk |
| 10 | `thread_id` only persisted on success | Failed turn doesn't corrupt thread ref |
| 11 | `finally` block for cleanup | Guarantees `_live_turns` removal |
| 12 | `call_soon_threadsafe` + `put_nowait` | Bridges sync threads to async handlers |
| 13 | Deep copy events to subscribers | Prevents cross-subscriber mutation |
| 14 | 15s heartbeat in SSE | Prevents proxy/browser timeouts |
| 15 | Atomic write (tmp + rename + fsync) | Crash-safe file persistence |
| 16 | Two-layer recovery (eager + lazy) | Handles both thread state and chat sessions |
| 17 | Resume as availability check | No "is thread alive" RPC exists |
| 18 | Node promotion before background turn | Status changes are synchronous and visible |
| 19 | Hidden context in user message | Survives thread resumption |
| 20 | Event sequence numbering | Maintains causal ordering for reconnect |
