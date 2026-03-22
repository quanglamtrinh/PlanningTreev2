# Rich Message Semantics — Techniques Reference

How to convert raw Codex app server events into structured UI blocks.
CodexMonitor never had this. PlanningTreeMain had it but deleted it. This is the blueprint to build it right.

---

## 1. What the Codex App Server Actually Sends

These are the raw JSON-RPC notifications from `codex_client.py:_handle_notification()` and `_handle_server_request()`. This is the ground truth — everything downstream derives from these.

### 1.1 Notifications (server → client, no response expected)

```
item/agentMessage/delta    { turnId, delta: string }              — text chunk
item/plan/delta            { turnId, threadId, itemId, delta }    — plan step text chunk
item/completed             { turnId, threadId, item: { type, text, id } }
                             item.type = "agentMessage" | "plan"
turn/completed             { threadId, turn: { id, status, error } }
                             status = "completed" | "failed" | "interrupted"
thread/status/changed      { threadId, status: { type, activeFlags? } }
                             type = "notLoaded" | "idle" | "running" | ...
serverRequest/resolved     { threadId, requestId }
error                      { turnId, error: { message } }
```

### 1.2 Server Requests (server → client, RESPONSE required)

```
item/tool/requestUserInput { threadId, turnId, itemId, questions: Question[] }
                             Question = { id, header, question, is_other, is_secret, options? }
                             MUST respond with { answers: { [questionId]: value } }

item/tool/call             { turnId, threadId, tool/name/toolName, arguments, callId }
                             MUST respond (auto-responded with default in current code)
```

### 1.3 What's missing from current capture

The Codex app server sends `item/tool/call` but current code auto-responds and only emits `on_tool_call` callback with `(tool_name, arguments)`. It does NOT capture:
- Tool call **results** (the response content)
- Tool call **duration** (start → response timing)
- Tool call **status** (pending → running → completed)

To get tool results, you'd need to intercept the auto-response or listen for subsequent notifications.

---

## 2. Message Part Model

A single assistant message contains multiple **parts** in order. Each part has a type and typed payload.

### 2.1 Part types to implement (priority order)

| Priority | Part type | Source event | UI rendering |
|----------|-----------|-------------|-------------|
| **P0** | `assistant_text` | `item/agentMessage/delta` | Streaming markdown text |
| **P0** | `user_text` | User input | Plain text bubble |
| **P1** | `tool_call` | `item/tool/call` | Collapsible block: tool name + arguments |
| **P1** | `status_block` | `thread/status/changed` | Inline status pill: "Reading files...", "Running tool..." |
| **P2** | `reasoning` | (not directly available*) | Collapsible "thinking" block |
| **P2** | `input_request` | `item/tool/requestUserInput` | Inline form: questions + answer inputs |
| **P3** | `plan_block` | `item/plan/delta` + `item/completed(plan)` | Step list with status indicators |
| **P3** | `diff_summary` | (derived from tool_call arguments) | File change summary with +/- counts |

*Reasoning: Codex app server doesn't send a separate "reasoning" notification. If the model outputs `<thinking>` tags in text, you parse them client-side from `assistant_text` deltas.

### 2.2 Part schema

```typescript
type MessagePart =
  | { type: "user_text";       content: string }
  | { type: "assistant_text";  content: string; is_streaming: boolean }
  | { type: "tool_call";       tool_name: string; arguments: Record<string, any>;
      call_id: string | null; status: "running" | "completed" | "error" }
  | { type: "status_block";    status_type: string; label: string; timestamp: string }
  | { type: "reasoning";       content: string; is_collapsed: boolean }
  | { type: "input_request";   request_id: string; questions: InputQuestion[];
      answers: Record<string, any> | null; resolution: "pending" | "resolved" | "stale" }
  | { type: "plan_block";      plan_id: string; steps: PlanStep[]; is_streaming: boolean }
  | { type: "diff_summary";    files: FileDiff[]; total_added: number; total_removed: number }

type InputQuestion = {
  id: string;
  header: string;
  question: string;
  is_secret: boolean;
  options: string[] | null;
}

type PlanStep = {
  id: string;
  text: string;
  status: "pending" | "in_progress" | "completed";
}

type FileDiff = {
  path: string;
  change_type: "added" | "modified" | "deleted";
  lines_added: number;
  lines_removed: number;
}
```

### 2.3 Message structure

```typescript
type RichMessage = {
  message_id: string;
  role: "user" | "assistant";
  parts: MessagePart[];            // Ordered list of parts
  status: "pending" | "streaming" | "completed" | "error";
  error: string | null;
  created_at: string;
  updated_at: string;
}
```

---

## 3. Backend: Stream → Parts Normalization

### 3.1 The normalizer pattern

The ChatService needs a **part accumulator** that converts raw callbacks into an ordered list of message parts. This runs in the background turn thread.

```python
class PartAccumulator:
    """Converts raw Codex callbacks into ordered message parts."""

    def __init__(self):
        self.parts: list[dict] = []
        self._current_text_part: dict | None = None
        self._current_plan_part: dict | None = None

    def on_delta(self, delta: str):
        """Text delta → append to current assistant_text part, or create new one."""
        if self._current_text_part is None:
            self._current_text_part = {
                "type": "assistant_text",
                "content": "",
                "is_streaming": True,
            }
            self.parts.append(self._current_text_part)
        self._current_text_part["content"] += delta

    def on_tool_call(self, tool_name: str, arguments: dict):
        """Tool call → close current text part, add tool_call part."""
        self._close_text_part()
        self.parts.append({
            "type": "tool_call",
            "tool_name": tool_name,
            "arguments": arguments,
            "call_id": None,
            "status": "running",
        })

    def on_thread_status(self, payload: dict):
        """Thread status change → add status_block part."""
        status = payload.get("status", {})
        status_type = status.get("type", "unknown")

        # Don't add redundant status blocks
        if self.parts and self.parts[-1].get("type") == "status_block":
            self.parts[-1]["status_type"] = status_type
            self.parts[-1]["label"] = self._status_label(status_type)
            self.parts[-1]["timestamp"] = iso_now()
            return

        self._close_text_part()
        self.parts.append({
            "type": "status_block",
            "status_type": status_type,
            "label": self._status_label(status_type),
            "timestamp": iso_now(),
        })

    def on_request_user_input(self, payload: dict):
        """User input request → close text, add input_request part."""
        self._close_text_part()
        self.parts.append({
            "type": "input_request",
            "request_id": payload.get("request_id", ""),
            "questions": payload.get("questions", []),
            "answers": None,
            "resolution": "pending",
        })

    def on_plan_delta(self, delta: str, metadata: dict):
        """Plan delta → accumulate in current plan part."""
        plan_id = metadata.get("id", "")
        if self._current_plan_part is None or self._current_plan_part["plan_id"] != plan_id:
            self._close_text_part()
            self._current_plan_part = {
                "type": "plan_block",
                "plan_id": plan_id,
                "raw_text": "",
                "steps": [],
                "is_streaming": True,
            }
            self.parts.append(self._current_plan_part)
        self._current_plan_part["raw_text"] += delta

    def finalize(self):
        """Called on turn completion. Close all open parts."""
        self._close_text_part()
        if self._current_plan_part:
            self._current_plan_part["is_streaming"] = False
            self._current_plan_part["steps"] = self._parse_plan_steps(
                self._current_plan_part.pop("raw_text", "")
            )
            self._current_plan_part = None

        # Mark all tool_calls as completed
        for part in self.parts:
            if part.get("type") == "tool_call" and part.get("status") == "running":
                part["status"] = "completed"

    def _close_text_part(self):
        if self._current_text_part is not None:
            self._current_text_part["is_streaming"] = False
            self._current_text_part = None

    @staticmethod
    def _status_label(status_type: str) -> str:
        labels = {
            "running": "Working...",
            "idle": "Idle",
            "notLoaded": "Loading...",
        }
        return labels.get(status_type, status_type)

    @staticmethod
    def _parse_plan_steps(raw_text: str) -> list[dict]:
        """Parse plan text into structured steps."""
        steps = []
        for i, line in enumerate(raw_text.strip().split("\n")):
            line = line.strip()
            if not line:
                continue
            steps.append({
                "id": f"step_{i}",
                "text": line.lstrip("0123456789.-) "),
                "status": "pending",
            })
        return steps
```

### 3.2 Wiring into background turn

```python
def _run_background_turn(self, project_id, node_id, turn_id, content, session):
    accumulator = PartAccumulator()

    try:
        result = self._codex_client.run_turn_streaming(
            prompt,
            thread_id=thread_id,
            on_delta=lambda d: self._handle_rich_delta(
                project_id, node_id, turn_id, accumulator, d, "delta"
            ),
            on_tool_call=lambda name, args: self._handle_rich_delta(
                project_id, node_id, turn_id, accumulator, None, "tool_call",
                tool_name=name, arguments=args
            ),
            on_thread_status=lambda p: self._handle_rich_delta(
                project_id, node_id, turn_id, accumulator, None, "status",
                payload=p
            ),
            on_request_user_input=lambda p: self._handle_rich_delta(
                project_id, node_id, turn_id, accumulator, None, "input_request",
                payload=p
            ),
            on_plan_delta=lambda d, m: self._handle_rich_delta(
                project_id, node_id, turn_id, accumulator, d, "plan_delta",
                metadata=m
            ),
        )

        accumulator.finalize()

        # Save with rich parts
        with self._lock:
            session = self._load_session(project_id, node_id)
            msg = self._find_assistant_message(session, turn_id)
            msg["parts"] = accumulator.parts
            msg["content"] = result["stdout"]  # Keep flat text as fallback
            msg["status"] = "completed"
            session["thread_id"] = result["thread_id"]
            session["active_turn_id"] = None
            self._save_session(project_id, node_id, session)

    except Exception as exc:
        accumulator.finalize()
        # ... error handling, same as before but with parts ...
```

### 3.3 SSE events for rich parts

Extend the event vocabulary:

```python
# On tool call:
self._publish_event(project_id, node_id, {
    "type": "assistant_tool_call",
    "message_id": msg_id,
    "tool_name": tool_name,
    "arguments": arguments,
    "part_index": len(accumulator.parts) - 1,
})

# On status change:
self._publish_event(project_id, node_id, {
    "type": "assistant_status",
    "message_id": msg_id,
    "status_type": status_type,
    "label": label,
})

# On input request:
self._publish_event(project_id, node_id, {
    "type": "input_requested",
    "message_id": msg_id,
    "request_id": request_id,
    "questions": questions,
})

# Text delta (unchanged, but now includes part_index):
self._publish_event(project_id, node_id, {
    "type": "assistant_delta",
    "message_id": msg_id,
    "delta": delta,
    "content": full_content,
    "part_index": current_text_part_index,
})
```

---

## 4. Frontend: Rendering Each Part Type

### 4.1 MessageBlock dispatcher

```tsx
function MessageBlock({ part }: { part: MessagePart }) {
  switch (part.type) {
    case "user_text":
      return <UserTextBlock content={part.content} />;
    case "assistant_text":
      return <AssistantTextBlock content={part.content} isStreaming={part.is_streaming} />;
    case "tool_call":
      return <ToolCallBlock name={part.tool_name} args={part.arguments} status={part.status} />;
    case "status_block":
      return <StatusPill label={part.label} />;
    case "reasoning":
      return <ReasoningBlock content={part.content} />;
    case "input_request":
      return <InputRequestBlock questions={part.questions} answers={part.answers}
               resolution={part.resolution} onSubmit={...} />;
    case "plan_block":
      return <PlanBlock steps={part.steps} isStreaming={part.is_streaming} />;
    case "diff_summary":
      return <DiffSummaryBlock files={part.files} />;
    default:
      return null;
  }
}
```

### 4.2 AssistantTextBlock — streaming markdown

```tsx
function AssistantTextBlock({ content, isStreaming }: {
  content: string; isStreaming: boolean
}) {
  return (
    <div className="msg-text">
      <Markdown content={content} />
      {isStreaming && <span className="cursor-blink" />}
    </div>
  );
}
```

Markdown rendering: use a lightweight library (e.g. `marked` + `DOMPurify`, or `react-markdown`).
Streaming cursor: CSS blinking block character at end of text.

**Key technique — incremental markdown:** Don't re-parse the entire markdown string on every delta. Two approaches:
1. **Simple:** Re-render on every delta. Fine for <5KB messages. React's VDOM diff handles it.
2. **Optimized:** Only re-render the last paragraph/block. Split content at last `\n\n`, render prefix as static, suffix as dynamic.

### 4.3 ToolCallBlock — collapsible

```tsx
function ToolCallBlock({ name, args, status }: {
  name: string; args: Record<string, any>; status: string
}) {
  const [expanded, setExpanded] = useState(false);
  const icon = status === "running" ? <Spinner /> : status === "error" ? "✗" : "✓";

  return (
    <div className="msg-tool" onClick={() => setExpanded(!expanded)}>
      <div className="msg-tool__header">
        {icon}
        <span className="msg-tool__name">{formatToolName(name)}</span>
        <span className="msg-tool__chevron">{expanded ? "▾" : "▸"}</span>
      </div>
      {expanded && (
        <pre className="msg-tool__args">{JSON.stringify(args, null, 2)}</pre>
      )}
    </div>
  );
}

function formatToolName(name: string): string {
  // "read_file" → "Read file", "shell" → "Shell"
  return name.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());
}
```

**UX decisions:**
- Collapsed by default — tool calls are noisy, most users don't care about arguments
- Show tool name + status icon even when collapsed
- Expand to see full arguments as JSON
- Spinner while running, checkmark on success

### 4.4 StatusPill — inline activity indicator

```tsx
function StatusPill({ label }: { label: string }) {
  return (
    <div className="msg-status">
      <span className="msg-status__dot" />
      <span className="msg-status__label">{label}</span>
    </div>
  );
}
```

```css
.msg-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  opacity: 0.7;
}
.msg-status__dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-accent);
  animation: pulse 1.5s infinite;
}
```

**UX decision:** Status pills are subtle, not blocks. They indicate what Codex is doing right now. They disappear (visually mute) once the next part arrives. Don't persist them as prominent blocks.

### 4.5 ReasoningBlock — collapsible thinking

```tsx
function ReasoningBlock({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const preview = content.slice(0, 80) + (content.length > 80 ? "..." : "");

  return (
    <div className="msg-reasoning" onClick={() => setExpanded(!expanded)}>
      <div className="msg-reasoning__header">
        <span className="msg-reasoning__icon">💭</span>
        <span className="msg-reasoning__preview">
          {expanded ? "Thinking" : preview}
        </span>
        <span>{expanded ? "▾" : "▸"}</span>
      </div>
      {expanded && (
        <div className="msg-reasoning__content">{content}</div>
      )}
    </div>
  );
}
```

**How to extract reasoning from text deltas:** If Codex outputs `<thinking>...</thinking>` tags in the text stream:

```python
# In PartAccumulator.on_delta():
def on_delta(self, delta: str):
    self._buffer += delta

    # Check for thinking tags
    while "<thinking>" in self._buffer:
        before, _, after = self._buffer.partition("<thinking>")
        if before.strip():
            self._append_text(before)
        if "</thinking>" in after:
            thinking, _, remaining = after.partition("</thinking>")
            self._close_text_part()
            self.parts.append({
                "type": "reasoning",
                "content": thinking.strip(),
                "is_collapsed": True,
            })
            self._buffer = remaining
        else:
            # Incomplete thinking block — wait for more deltas
            self._buffer = "<thinking>" + after
            return

    if self._buffer:
        self._append_text(self._buffer)
        self._buffer = ""
```

**Caveat:** Codex app server may not emit `<thinking>` tags. If it does, this parsing works. If it doesn't, skip the reasoning part type entirely — don't fake it.

### 4.6 InputRequestBlock — inline approval form

```tsx
function InputRequestBlock({ questions, answers, resolution, onSubmit }: {
  questions: InputQuestion[];
  answers: Record<string, any> | null;
  resolution: "pending" | "resolved" | "stale";
  onSubmit: (answers: Record<string, any>) => void;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const isResolved = resolution !== "pending";

  return (
    <div className={`msg-input-request ${isResolved ? "msg-input-request--resolved" : ""}`}>
      <div className="msg-input-request__header">
        {isResolved ? "✓ Resolved" : "⚠ Input needed"}
      </div>
      {questions.map(q => (
        <div key={q.id} className="msg-input-request__question">
          {q.header && <label>{q.header}</label>}
          <p>{q.question}</p>
          {isResolved ? (
            <div className="msg-input-request__answer">
              {answers?.[q.id] ?? "—"}
            </div>
          ) : q.options ? (
            <select
              value={draft[q.id] ?? ""}
              onChange={e => setDraft(d => ({ ...d, [q.id]: e.target.value }))}
            >
              <option value="">Select...</option>
              {q.options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input
              type={q.is_secret ? "password" : "text"}
              value={draft[q.id] ?? ""}
              onChange={e => setDraft(d => ({ ...d, [q.id]: e.target.value }))}
            />
          )}
        </div>
      ))}
      {!isResolved && (
        <button
          onClick={() => onSubmit(draft)}
          disabled={questions.some(q => !draft[q.id])}
        >
          Submit
        </button>
      )}
    </div>
  );
}
```

**Backend wiring for resolution:**
```
User clicks Submit
  → POST /chat/input-response { request_id, answers }
  → ChatService calls codex_client.resolve_runtime_request_user_input(request_id, answers=answers)
  → Codex app server receives answers, continues turn
  → Turn resumes streaming (more deltas arrive)
  → Publish "input_resolved" SSE event
  → Frontend updates part.resolution = "resolved", part.answers = answers
```

### 4.7 PlanBlock — step list

```tsx
function PlanBlock({ steps, isStreaming }: {
  steps: PlanStep[]; isStreaming: boolean
}) {
  return (
    <div className="msg-plan">
      <div className="msg-plan__header">Plan</div>
      <ol className="msg-plan__steps">
        {steps.map(step => (
          <li key={step.id} className={`msg-plan__step msg-plan__step--${step.status}`}>
            <span className="msg-plan__step-indicator">
              {step.status === "completed" ? "✓" :
               step.status === "in_progress" ? <Spinner size="sm" /> : "○"}
            </span>
            {step.text}
          </li>
        ))}
      </ol>
      {isStreaming && <span className="cursor-blink" />}
    </div>
  );
}
```

### 4.8 DiffSummaryBlock — file changes

```tsx
function DiffSummaryBlock({ files }: { files: FileDiff[] }) {
  return (
    <div className="msg-diff">
      <div className="msg-diff__header">
        {files.length} file{files.length !== 1 ? "s" : ""} changed
      </div>
      {files.map(f => (
        <div key={f.path} className="msg-diff__file">
          <span className={`msg-diff__badge msg-diff__badge--${f.change_type}`}>
            {f.change_type === "added" ? "A" : f.change_type === "deleted" ? "D" : "M"}
          </span>
          <span className="msg-diff__path">{f.path}</span>
          {f.lines_added > 0 && <span className="msg-diff__added">+{f.lines_added}</span>}
          {f.lines_removed > 0 && <span className="msg-diff__removed">-{f.lines_removed}</span>}
        </div>
      ))}
    </div>
  );
}
```

**How to derive diff_summary:** Extract from tool_call arguments when `tool_name` is `write_file`, `edit_file`, `create_file`, etc. This is a derived/synthetic part — the Codex server doesn't send diff events directly.

---

## 5. SSE Event Reducer — Applying Rich Events to State

```typescript
function applyChatEvent(session: ChatSession, event: ChatEvent): ChatSession {
  const messages = [...session.messages];

  switch (event.type) {
    case "message_created":
      return {
        ...session,
        active_turn_id: event.active_turn_id,
        messages: [...messages, event.user_message, event.assistant_message],
      };

    case "assistant_delta": {
      const msg = findMessage(messages, event.message_id);
      if (!msg) return session;

      // Update the last assistant_text part, or create one
      const parts = [...(msg.parts || [])];
      const lastTextPart = findLastPart(parts, "assistant_text");
      if (lastTextPart) {
        lastTextPart.content = event.content;
        lastTextPart.is_streaming = true;
      } else {
        parts.push({ type: "assistant_text", content: event.content, is_streaming: true });
      }
      return updateMessage(session, event.message_id, { parts, status: "streaming" });
    }

    case "assistant_tool_call": {
      const msg = findMessage(messages, event.message_id);
      if (!msg) return session;
      const parts = [...(msg.parts || [])];

      // Close current streaming text part
      const lastText = findLastPart(parts, "assistant_text");
      if (lastText) lastText.is_streaming = false;

      parts.push({
        type: "tool_call",
        tool_name: event.tool_name,
        arguments: event.arguments,
        status: "running",
      });
      return updateMessage(session, event.message_id, { parts });
    }

    case "assistant_status": {
      const msg = findMessage(messages, event.message_id);
      if (!msg) return session;
      const parts = [...(msg.parts || [])];

      // Replace or add status pill
      const lastStatus = parts.length > 0 && parts[parts.length - 1].type === "status_block"
        ? parts.length - 1 : -1;
      const statusPart = {
        type: "status_block",
        status_type: event.status_type,
        label: event.label,
        timestamp: new Date().toISOString(),
      };
      if (lastStatus >= 0) {
        parts[lastStatus] = statusPart;
      } else {
        parts.push(statusPart);
      }
      return updateMessage(session, event.message_id, { parts });
    }

    case "input_requested": {
      const msg = findMessage(messages, event.message_id);
      if (!msg) return session;
      const parts = [...(msg.parts || [])];
      parts.push({
        type: "input_request",
        request_id: event.request_id,
        questions: event.questions,
        answers: null,
        resolution: "pending",
      });
      return updateMessage(session, event.message_id, { parts });
    }

    case "input_resolved": {
      const msg = findMessage(messages, event.message_id);
      if (!msg) return session;
      const parts = (msg.parts || []).map(p =>
        p.type === "input_request" && p.request_id === event.request_id
          ? { ...p, answers: event.answers, resolution: "resolved" }
          : p
      );
      return updateMessage(session, event.message_id, { parts });
    }

    case "assistant_completed": {
      const msg = findMessage(messages, event.message_id);
      if (!msg) return session;
      const parts = (msg.parts || []).map(p => {
        if (p.type === "assistant_text") return { ...p, is_streaming: false };
        if (p.type === "tool_call" && p.status === "running") return { ...p, status: "completed" };
        return p;
      });
      // Remove trailing status pills — they're transient
      while (parts.length > 0 && parts[parts.length - 1].type === "status_block") {
        parts.pop();
      }
      return {
        ...updateMessage(session, event.message_id, {
          parts,
          content: event.content,
          status: "completed",
        }),
        active_turn_id: null,
        thread_id: event.thread_id,
      };
    }

    case "assistant_error":
      return {
        ...updateMessage(session, event.message_id, {
          status: "error",
          error: event.error,
        }),
        active_turn_id: null,
      };

    case "session_reset":
      return event.session;

    default:
      return session;
  }
}
```

---

## 6. Key UX Decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Tool calls: expanded or collapsed? | **Collapsed by default** | Most users care about results, not arguments. Power users click to expand. |
| Status pills: persist or remove? | **Remove on completion** | They're transient indicators. Keeping them clutters the history. |
| Reasoning: show or hide? | **Collapsed, with preview** | Interesting for debugging, distracting for normal use. |
| Input requests: inline or modal? | **Inline in message flow** | Keeps context visible. Modals break the reading flow. |
| Plan blocks: always show? | **Only if steps > 1** | Single-step plans are noise. |
| Diff summary: when to show? | **Only after tool calls that modify files** | Derived, not raw. Show as a summary after the tool call block. |
| Markdown in text: full or limited? | **Full (headers, lists, code, links)** | Codex writes markdown. Rendering it properly is the minimum. |
| Streaming text: per-char or per-chunk? | **Per-chunk as received** | Don't buffer or debounce. The SSE delta is already chunked. |
| Fallback for unknown parts? | **Skip silently** | Future part types should degrade gracefully, not crash the renderer. |

---

## 7. Implementation Priority

**Phase 1 (minimum viable):** `assistant_text` + `user_text` + streaming + markdown
This is what CodexMonitor has today. Ship this first.

**Phase 2 (visible improvement):** `tool_call` (collapsed) + `status_block` (transient)
Users can now see what Codex is doing. Biggest UX win per effort.

**Phase 3 (interactive):** `input_request` + resolution flow
Enables approval workflows. Requires new API endpoint + Codex client wiring.

**Phase 4 (polish):** `reasoning` + `plan_block` + `diff_summary`
Nice-to-have. Only add if the Codex server actually sends the raw data.
