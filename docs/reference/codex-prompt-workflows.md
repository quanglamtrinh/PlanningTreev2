# Codex Prompt Workflows

Tai lieu nay tong hop tat ca workflow trong project co prompt de Codex agent lam viec.
Muc tieu la giup theo doi:

- Workflow nao thuc su goi Codex
- `base_instructions` cua thread la gi
- `turn prompt` duoc ghep nhu the nao
- Moi field trong prompt lay tu dau
- Output contract / tool nao duoc phep goi
- `outputSchema` neu co

Luu y quan trong:

- "Prompt hieu luc" cua Codex khong chi la 1 string.
- Moi workflow thuc te co 4-5 lop context:
  - `base_instructions` khi `thread/start` hoac `thread/fork`
  - `role_prefix` prepend vao turn prompt (cho frame/clarify/spec)
  - `turn prompt` tai moi lan `run_turn_streaming(...)`
  - `outputSchema` rang buoc output format (cho frame/clarify/spec)
  - lich su thread neu thread duoc `resume`
  - toan bo codebase vi workflow chay voi `cwd=workspace_root`

## Tong quan

| Workflow | Co goi Codex? | Muc dich |
|---|---|---|
| Chat | Yes | Tra loi / tuong tac voi user tren node hien tai |
| Split `workflow` | Yes | Chia task theo workflow / outcome |
| Split `simplify_workflow` | Yes | Tim core workflow nho nhat roi them dan |
| Split `phase_breakdown` | Yes | Chia task theo phase trien khai |
| Split `agent_breakdown` | Yes | Chia theo boundary / risk / dependency |
| Generate Frame | Yes | Sinh `frame.md` tu context + lich su chat |
| Generate Clarify | Yes | Sinh cau hoi clarify tu confirmed frame |
| Generate Spec | Yes | Sinh `spec.md` tu confirmed frame |
| Confirm Frame | No prompt truc tiep | Nghiep vu xac nhan frame, co the trigger clarify/spec generation |
| Confirm Clarify | No prompt truc tiep | Apply clarify vao frame |
| Confirm Spec | No prompt truc tiep | Xac nhan spec |

## Bang Workflow Co Prompt

| Workflow | Base instructions tren thread | Role prefix (prepend vao turn prompt) | Turn prompt duoc ghep o runtime | Field dung trong turn prompt | Output mechanism | Code |
|---|---|---|---|---|---|---|
| Chat | Tro ly huu ich cho PlanningTree, tra loi ro rang va actionable | Khong co | `Project: {project_name}`<br>`Root goal: {root_goal}`<br><br>`Current task: {title}`<br>`Description: {description}`<br><br>`Ancestors:` ...<br>`Completed siblings:` ...<br><br>`---`<br>`User message:`<br>`{user_content}` | `project_name`, `root_goal`, `title`, `description`, `ancestors`, `completed_siblings`, `user_content` | Plain text (khong co dynamic tool hoac outputSchema) | [chat_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/chat_prompt_builder.py#L24) · [chat_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/chat_service.py#L242) · [chat_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/chat_service.py#L359) |
| Split `workflow` | PlanningTree split assistant; phai goi `emit_render_data(kind='split_result', payload=...)`; neu co task frame thi phai coi cac shaping decisions trong frame la rang buoc | Khong co | `{retry_feedback?}`<br><br>`You are a decomposition agent...`<br>`Split a parent task into a small set of sequential workflow-based subtasks.`<br><br>`Runtime context:`<br>`- Parent task: {current_node_prompt}`<br>`- Task frame:` `{frame_content?}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br>`- Completed sibling context:` ...<br><br>`Output contract:` schema `subtasks[{id,title,objective,why_now}]` | `current_node_prompt`, `frame_content`, `root_prompt`, `parent_chain_prompts`, `prior_node_summaries_compact`, `retry_feedback` | `emit_render_data(kind="split_result", payload=...)` dynamic tool | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L164) · [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L11) · [split_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/split_service.py#L163) |
| Split `simplify_workflow` | Giong split o tren | Khong co | Giong cau truc split, nhung mode body doi thanh: tim core workflow nho nhat roi them lai phan con lai theo thu tu phu thuoc | Giong split `workflow` | `emit_render_data(...)` dynamic tool | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L42) |
| Split `phase_breakdown` | Giong split o tren | Khong co | Giong cau truc split, nhung mode body doi thanh: chia theo phase delivery tuan tu | Giong split `workflow` | `emit_render_data(...)` dynamic tool | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L72) |
| Split `agent_breakdown` | Giong split o tren | Khong co | Giong cau truc split, nhung mode body doi thanh: chia theo boundary / risk / dependency khi workflow / phase khong hop | Giong split `workflow` | `emit_render_data(...)` dynamic tool | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L102) |
| Generate Frame | `""` (empty — explicit de khong inherit tu audit thread) | Task-framing assistant; 5 rules; format frame.md | `Task context:`<br>`- Current task: {current_node_prompt}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br>`- Completed siblings:` ...<br><br>`Conversation history:`<br>`[user]: ...`<br>`[assistant]: ...`<br><br>`Generate the frame document now. Respond with structured JSON output.` | `current_node_prompt`, `root_prompt`, `parent_chain_prompts`, `prior_node_summaries_compact`, `chat_messages[]` | `outputSchema: {content: string}`<br>3-tier: structured JSON → tool_calls fallback → raw stdout | [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L95) · [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L55) · [frame_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/frame_generation_service.py#L184) |
| Generate Clarify | `""` (empty — explicit) | Task-clarification assistant; 6 rules; chi hoi cho unresolved Task-Shaping Fields; 2-4 options moi cau | `Task context:`<br>`- Current task: {current_node_prompt}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br><br>`Confirmed frame document:`<br>`{frame_content}`<br><br>`Generate clarifying questions now. Respond with structured JSON output.` | `current_node_prompt`, `root_prompt`, `parent_chain_prompts`, `frame_content` | `outputSchema: {questions: [{field_name, question, ...}]}`<br>3-tier: structured JSON → tool_calls fallback → text parse (NO raw stdout) | [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L159) · [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L49) · [clarify_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/clarify_generation_service.py#L215) |
| Generate Spec | `""` (empty — explicit) | Technical spec writer; 6 rules; spec sections; khong inspect workspace | `Task context:`<br>`- Current task: {current_node_prompt}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br><br>`Confirmed frame document:`<br>`{frame_content}`<br><br>`Generate the technical spec now. Respond with structured JSON output.` | `current_node_prompt`, `root_prompt`, `parent_chain_prompts`, `frame_content` | `outputSchema: {content: string}`<br>3-tier: structured JSON → tool_calls fallback → text parse (NO raw stdout) | [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L96) · [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L46) · [spec_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/spec_generation_service.py#L227) |

## Bang Field Va Nguon Du Lieu

| Field trong prompt | Gia tri / y nghia | Duoc lay tu dau | Code |
|---|---|---|---|
| `project_name` | Ten project hien tai | `snapshot.project.name` | [project_store.py](C:/Users/Thong/PlanningTreeMain/backend/storage/project_store.py#L177) |
| `root_goal` / `root_prompt` | Root goal cua project | `snapshot.project.root_goal` | [split_context_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_context_builder.py#L18) |
| `project_path` / `workspace_root` | Thu muc repo duoc dung lam `cwd` | `snapshot.project.project_path` | [project_store.py](C:/Users/Thong/PlanningTreeMain/backend/storage/project_store.py#L277) |
| `title` | Tieu de node hien tai | `tree_state.node_index[node_id].title` | [node_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_service.py#L105) |
| `description` | Mo ta node hien tai | `tree_state.node_index[node_id].description` | [node_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_service.py#L113) |
| `current_node_prompt` | Prompt compact cua node, thuong la `title: description` | `_format_node_prompt(node)` | [split_context_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_context_builder.py#L92) |
| `parent_chain_prompts` | Danh sach ancestor cua node | Build tu `parent_id` | [split_context_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_context_builder.py#L34) |
| `prior_node_summaries_compact` | Cac sibling da `done` cung parent | Build tu tree state | [split_context_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_context_builder.py#L52) |
| `chat_messages` | Lich su chat local cua node | `.planningtree/chat/{node_id}.json` | [chat_state_store.py](C:/Users/Thong/PlanningTreeMain/backend/storage/chat_state_store.py#L44) |
| `frame_content` cho clarify/spec/split | Confirmed frame snapshot | Uu tien `frame.meta.json.confirmed_content`, fallback `frame.md` | [clarify_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/clarify_generation_service.py#L108) · [spec_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/spec_generation_service.py#L116) · [split_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/split_service.py#L157) |
| `retry_feedback` | Loi validate payload split cua lan truoc | Sinh tu validator cua split | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L183) |

## Chi Tiet Theo Tung Workflow

### 1. Chat

#### Base instructions

Duoc set khi tao thread:

```text
You are a helpful assistant for the PlanningTree project planning tool.
Help the user with their task by providing clear, actionable guidance.
```

Nguon: [chat_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/chat_service.py#L359)

#### Turn prompt skeleton

```text
Project: {project_name}
Root goal: {root_goal}

Current task: {title}
Description: {description}

Ancestors:
  - {ancestor_1}
  - {ancestor_2}

Completed siblings:
  - {sibling_title}: {sibling_description}

---

User message:
{user_content}
```

Nguon: [chat_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/chat_prompt_builder.py#L24)

#### Ghi chu

- Chat workflow khong nhung explicit lich su chat local vao turn prompt string.
- Lich su hoi thoai chu yeu song trong Codex thread duoc `resume`.

### 2. Split

#### Base instructions

Split thread co base instructions chung:

```text
You are the PlanningTree split assistant.
For split turns, produce structured UI data with emit_render_data(kind='split_result', payload=...).
The split payload must use exactly one top-level key: subtasks.
Each subtask item must use exactly: id, title, objective, why_now.
If you can produce a valid split, call emit_render_data before writing a short summary for the user.
Do not duplicate the structured payload in the summary text.
```

Nguon: [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L150)

#### Turn prompt skeleton

```text
{retry_feedback_if_any}

{mode_specific_body}

Runtime context:
- Parent task: {current_node_prompt}
- Task frame:
{frame_content_if_exists}
- Root goal: {root_prompt}
- Parent chain:
  - ...
- Completed sibling context:
  - ...

Output contract:
- First call emit_render_data(kind='split_result', payload=...).
- The payload must be valid JSON in this exact shape:
  {"subtasks":[{"id":"S1","title":"...","objective":"...","why_now":"..."}]}
- hard rules...
```

Nguon: [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L164)

#### Mode-specific bodies

| Mode | Tinh chat |
|---|---|
| `workflow` | Workflow-first, outcome-first, golden path first |
| `simplify_workflow` | Tim version nho nhat van chung minh duoc core workflow |
| `phase_breakdown` | Chia theo phase delivery / hardening |
| `agent_breakdown` | Chia theo boundary / dependency / risk / migration / cleanup |

Nguon: [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L11)

#### Ghi chu

- Split co retry prompt neu payload sai schema.
- Split khong con chen `spec.md` vao prompt.
- Neu co frame, split se dung `confirmed_content` trong `frame.meta.json` truoc; neu chua co thi moi fallback `frame.md`.
- Frame duoc xem la task-shaping context, va prompt moi yeu cau subtasks phai phan anh cac quyet dinh trong frame khi co lien quan.

### 3. Generate Frame

#### Thread config

Frame generation chay tren ask_planning thread (fork tu audit thread).
- `baseInstructions`: `""` (sent explicitly — khong inherit tu audit thread)
- `dynamicTools`: `[]` (khong co dynamic tools)

Nguon: [ask_thread_config.py](C:/Users/Thong/PlanningTreeMain/backend/ai/ask_thread_config.py#L11)

#### Role prefix (prepend vao turn prompt)

Task-framing assistant voi 5 rules:

1. Derive frame tu conversation + context
2. Khong invent requirements
3. Khong hoi clarification
4. De trong field shaping neu chua ro
5. Keep concise and actionable

Nguon: [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L55)

#### Turn prompt skeleton

```text
{role_prefix}

Task context:
- Current task: {current_node_prompt}
- Root goal: {root_prompt}
- Parent chain:
  - ...
- Completed siblings:
  - ...

Conversation history:
[user]: ...
[assistant]: ...

Generate the frame document now. Respond with the full markdown content as structured JSON output.
```

Nguon: [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L95)

#### Output schema

```json
{"type": "object", "required": ["content"], "properties": {"content": {"type": "string"}}}
```

Nguon: [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L82)

#### Extraction (3-tier)

1. **Structured JSON**: Parse stdout as `{content: "..."}` (co strip JSON fence truoc)
2. **Tool calls fallback**: Tim `emit_frame_content` tool call (backward compat voi old threads)
3. **Raw stdout**: Neu stdout co content, dung truc tiep (frame content IS markdown nen raw stdout hop le)

Nguon: [frame_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/frame_generation_service.py#L196)

#### Ghi chu

- Day la workflow duy nhat ngoai chat co nhung explicit lich su chat local vao prompt string.
- `chat_messages` duoc doc tu store local cua app, khong phai tu Codex thread.
- Frame la workflow duy nhat co raw stdout fallback (tier 3) vi frame content la markdown.

### 4. Generate Clarify

#### Thread config

Chay tren cung ask_planning thread voi frame (fork tu audit thread).
- `baseInstructions`: `""` (sent explicitly)
- `dynamicTools`: `[]`

#### Role prefix (prepend vao turn prompt)

Task-clarification assistant voi 6 rules:

1. Doc frame, focus vao "Task-Shaping Fields"
2. Field chua co value → sinh 1 question
3. Field da co value → skip
4. Khong invent question ngoai frame fields
5. Neu tat ca da resolve → return `{"questions": []}` as structured output
6. Moi question co 2-4 options, exactly 1 recommended, `id` = snake_case(value)

Nguon: [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L49)

#### Turn prompt skeleton

```text
{role_prefix}

Task context:
- Current task: {current_node_prompt}
- Root goal: {root_prompt}
- Parent chain:
  - ...

Confirmed frame document:

{frame_content}

Generate clarifying questions now. Respond with structured JSON output.
```

Nguon: [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L159)

#### Output schema

```json
{
  "type": "object",
  "required": ["questions"],
  "properties": {
    "questions": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["field_name", "question", "options"],
        "properties": {
          "field_name": {"type": "string"},
          "question": {"type": "string"},
          "why_it_matters": {"type": "string"},
          "current_value": {"type": "string"},
          "options": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "label", "value", "rationale", "recommended"],
              "properties": {
                "id": {"type": "string"},
                "label": {"type": "string"},
                "value": {"type": "string"},
                "rationale": {"type": "string"},
                "recommended": {"type": "boolean"}
              }
            }
          }
        }
      }
    }
  }
}
```

Nguon: [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L87)

#### Extraction (3-tier)

1. **Structured JSON**: Parse stdout as `{questions: [...]}` (co strip JSON fence truoc)
2. **Tool calls fallback**: Tim `emit_clarify_questions` tool call (backward compat)
3. **Text parse**: Tim JSON array trong stdout text
4. **KHONG co raw stdout fallback** — raw text khong phai clarify data hop le

**Quan trong**: `questions = []` la success case hop le (tat ca field da resolve → auto-confirm). Code dung `is not None` check, khong dung truthiness.

Nguon: [clarify_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/clarify_generation_service.py#L228)

#### Ghi chu

- Clarify ban dau duoc seed deterministic bang parse `Task-Shaping Fields` trong `frame.md`.
- AI clarify chi dung de bien field chua resolve thanh question + options chat luong hon.

Nguon seed: [node_detail_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_detail_service.py#L433)

### 5. Generate Spec

#### Thread config

Chay tren cung ask_planning thread voi frame va clarify.
- `baseInstructions`: `""` (sent explicitly)
- `dynamicTools`: `[]`

#### Role prefix (prepend vao turn prompt)

Technical spec writer voi 6 rules:

1. Doc frame — tat ca shaping fields da resolved
2. Be specific and actionable
3. Reference specific technologies/patterns
4. 200-500 words
5. Markdown headers cho moi section
6. Khong inspect workspace, khong chay commands — da co du context trong prompt

Spec sections: Overview, Architecture Decisions, Implementation Plan, Data Model, API/Interface, Edge Cases, Testing Strategy.

Nguon: [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L46)

#### Turn prompt skeleton

```text
{role_prefix}

Task context:
- Current task: {current_node_prompt}
- Root goal: {root_prompt}
- Parent chain:
  - ...

Confirmed frame document:

{frame_content}

Generate the technical spec now. Respond with structured JSON output.
```

Nguon: [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L96)

#### Output schema

```json
{"type": "object", "required": ["content"], "properties": {"content": {"type": "string"}}}
```

Nguon: [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L83)

#### Extraction (3-tier)

1. **Structured JSON**: Parse stdout as `{content: "..."}` (co strip JSON fence truoc)
2. **Tool calls fallback**: Tim `emit_spec_content` tool call (backward compat)
3. **Text parse**: Kiem tra markdown headers hoac JSON content trong stdout
4. **KHONG co raw stdout fallback** — raw text co the la summary, khong phai spec

Nguon: [spec_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/spec_generation_service.py#L239)

## Workflow Khong Co Prompt Truc Tiep Nhung Anh Huong Den Prompt

### Confirm Frame

`confirm_frame()`:

- confirm `frame.md`
- snapshot `confirmed_content` vao `frame.meta.json`
- dong bo `# Task Title` ve `node.title`
- seed `clarify.json` tu unresolved shaping fields

Nguon: [node_detail_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_detail_service.py#L100)

### Confirm Clarify

`apply_clarify_to_frame()`:

- lay answer da chon trong `clarify.json`
- patch truc tiep vao section `Task-Shaping Fields` cua `frame.md`
- bump frame revision

Nguon: [node_detail_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_detail_service.py#L247)

### Confirm Spec

`confirm_spec()`:

- danh dau spec la confirmed
- ghi `source_frame_revision`

Nguon: [node_detail_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_detail_service.py#L308)

## Vi Du Mau: Generate Frame

### Gia su du lieu dau vao

| Field | Gia tri mau | Nguon |
|---|---|---|
| `project_name` | `PlanningTreeMain` | `snapshot.project.name` |
| `root_goal` | `Build a planning tool for project decomposition` | `snapshot.project.root_goal` |
| `node.title` | `Core Site Entry` | node hien tai |
| `node.description` | `Tao landing page dau tien de user hieu san pham va biet buoc tiep theo.` | node hien tai |
| `current_node_prompt` | `Core Site Entry: Tao landing page dau tien de user hieu san pham va biet buoc tiep theo.` | `_format_node_prompt(node)` |
| `parent_chain_prompts` | `["Website MVP: Ban dau co the demo", "Marketing Site: Entry point cho user moi"]` | ancestor chain |
| `prior_node_summaries_compact` | `[{"title":"Brand foundation","description":"Chot tone, mau, typography"}]` | sibling da done |
| `chat_messages` | user / assistant trao doi truoc do | `.planningtree/chat/{node_id}.json` |

### Thread config hieu luc

Ask planning thread duoc fork tu audit thread voi:
- `baseInstructions`: `""` (empty string sent explicitly → khong inherit audit base instructions)
- `dynamicTools`: `[]` (khong co dynamic tools)

Nguon: [ask_thread_config.py](C:/Users/Thong/PlanningTreeMain/backend/ai/ask_thread_config.py#L11)

### Turn prompt sau khi ghep field (voi role prefix)

```text
You are a task-framing assistant for the PlanningTree project planning tool.

Your job is to generate a frame document (frame.md) for a task node.
...

Rules:
1. Derive the frame entirely from the conversation history and task context provided.
2. Do not invent requirements that are not grounded in the conversation or context.
3. Do not ask clarification questions — produce the best frame from available information.
4. Leave Task-Shaping Fields blank (no value after the colon) when the conversation
   does not provide enough information to decide.
5. Keep section content concise and actionable.

Task context:
- Current task: Core Site Entry: Tao landing page dau tien de user hieu san pham va biet buoc tiep theo.
- Root goal: Build a planning tool for project decomposition
- Parent chain:
  - Website MVP: Ban dau co the demo
  - Marketing Site: Entry point cho user moi
- Completed siblings:
  - Brand foundation: Chot tone, mau, typography

Conversation history:
[user]: Toi muon trang mo dau that ro, mobile-first.
[assistant]: Toi se draft frame theo huong landing page ngan gon.
[user]: Can CTA dan sang tao project va xem vi du, chua can onboarding phuc tap.

Generate the frame document now. Respond with the full markdown content as structured JSON output.
```

### Output schema duoc gui kem

```json
{"type": "object", "required": ["content"], "properties": {"content": {"type": "string"}}}
```

### Cach field duoc ghep

| Buoc | Du lieu | Cach ghep |
|---|---|---|
| 1 | role prefix | prepend vao dau prompt |
| 2 | `node.title` + `node.description` | ghep thanh `current_node_prompt` |
| 3 | `snapshot.project.root_goal` | dua vao dong `Root goal` |
| 4 | ancestor chain | dua vao block `Parent chain` |
| 5 | sibling da done | dua vao block `Completed siblings` |
| 6 | chat history local | dua vao block `Conversation history` |
| 7 | lenh cuoi | append cau lenh `Generate the frame document now. Respond with structured JSON output.` |

### Prompt hieu luc thuc te cua Codex o workflow nay

Prompt ma model thuc su "nhin thay" khong chi la turn prompt o tren. No bao gom:

1. `base_instructions` cua ask_planning thread (hien tai la `""`)
2. role prefix (prepend vao turn prompt)
3. turn prompt vua duoc ghep
4. `outputSchema` rang buoc output format
5. lich su thread neu thread da duoc reuse / resume
6. repo hien tai vi chay voi `cwd=workspace_root`

## Output Extraction Architecture

Frame/clarify/spec generation dung cung mo hinh 3-tier extraction:

| Tier | Mechanism | Khi nao dung |
|---|---|---|
| 1 | `outputSchema` structured JSON tu stdout | Primary — model tra ve JSON theo schema |
| 2 | Tool calls (`emit_*`) | Backward compat voi old threads co dynamic tools |
| 3 | Text parse / raw stdout | Fallback cuoi cung |

**Khac biet giua workflows o tier 3:**

| Workflow | Tier 3 behavior | Ly do |
|---|---|---|
| Frame | Accept raw stdout as-is | Frame content la markdown, raw stdout hop le |
| Clarify | Parse JSON tu text only, KHONG accept raw | Raw text khong phai structured clarify data |
| Spec | Parse markdown/JSON tu text only, KHONG accept raw | Raw text co the la summary, khong phai spec |

**JSON fence stripping**: Model thuong wrap JSON output trong markdown fence (`` ```json ... ``` ``). Tat ca tier-1 extractors goi `strip_json_fence()` truoc khi `json.loads()`.

Nguon: [prompt_helpers.py](C:/Users/Thong/PlanningTreeMain/backend/ai/prompt_helpers.py)

**Clarify empty list**: `questions = []` la success case hop le (tat ca field da resolve). Code dung `is not None` check thay vi truthiness. Empty list trigger auto-confirm trong `_write_clarify_content`.

## Shared Prompt Helpers

File `backend/ai/prompt_helpers.py` chua cac utility dung chung:

| Function | Dung o dau | Muc dich |
|---|---|---|
| `normalize_text(value)` | clarify, spec | Chuyen value ve string, strip whitespace |
| `truncate(text, limit)` | clarify, spec | Cat text va them `...` neu vuot limit |
| `format_frame_content(frame_content, char_limit)` | clarify, spec | Format confirmed frame voi truncation |
| `strip_json_fence(text)` | frame, clarify, spec | Strip `` ```json ``` `` fence truoc khi json.loads |

**Luu y**: `_format_task_context` KHONG duoc share vi frame version co them `prior_node_summaries_compact` (completed siblings). Clarify va spec dung version don gian hon.

Nguon: [prompt_helpers.py](C:/Users/Thong/PlanningTreeMain/backend/ai/prompt_helpers.py)

## codex_client.py Wire Behavior

`base_instructions` va `dynamic_tools` dung `is not None` check (khong dung truthiness):

```python
if base_instructions is not None:
    params["baseInstructions"] = base_instructions
if dynamic_tools is not None:
    params["dynamicTools"] = dynamic_tools
```

Dieu nay dam bao `base_instructions=""` duoc gui explicit la `"baseInstructions": ""` trong RPC params. Neu bo qua (falsy check), thread fork co the inherit base instructions tu source thread.

Nguon: [codex_client.py](C:/Users/Thong/PlanningTreeMain/backend/ai/codex_client.py#L305)

## File / State Lien Quan Den Prompt Inputs

| Loai du lieu | Noi luu |
|---|---|
| Project meta | `.planningtree/meta.json` va project snapshot |
| Cay node | `.planningtree/tree.json` va snapshot |
| Chat session local | `.planningtree/chat/{node_id}.json` |
| Frame draft | node dir `frame.md` |
| Frame confirmed snapshot | node dir `frame.meta.json` |
| Clarify data | node dir `clarify.json` |
| Spec draft | node dir `spec.md` |
| Spec meta | node dir `spec.meta.json` |

## Routes Kich Hoat Cac Workflow Co Prompt

| Workflow | Route |
|---|---|
| Chat | `POST /v1/projects/{project_id}/nodes/{node_id}/chat/message` |
| Split | `POST /v1/projects/{project_id}/nodes/{node_id}/split` |
| Generate Frame | `POST /v1/projects/{project_id}/nodes/{node_id}/generate-frame` |
| Generate Clarify | `POST /v1/projects/{project_id}/nodes/{node_id}/generate-clarify` |
| Generate Spec | `POST /v1/projects/{project_id}/nodes/{node_id}/generate-spec` |

Nguon: [chat.py](C:/Users/Thong/PlanningTreeMain/backend/routes/chat.py#L23) · [split.py](C:/Users/Thong/PlanningTreeMain/backend/routes/split.py#L17) · [nodes.py](C:/Users/Thong/PlanningTreeMain/backend/routes/nodes.py#L126)

## Ghi Chu Audit

- Neu can audit chinh xac "prompt cuoi cung" cho 1 request cu the, phai xet them:
  - thread history da co gi truoc do
  - file trong repo ma Codex co the tu doc qua `cwd`
  - retry feedback cua split neu request truoc fail
  - `outputSchema` da duoc gui kem cho frame/clarify/spec turns
  - role prefix da duoc prepend vao turn prompt
- Vi vay string trong builder la "prompt turn hien tai", con "context hieu luc" thi lon hon.
- Ask planning thread (`baseInstructions=""`, `dynamicTools=[]`) duoc send explicit de khong inherit tu audit thread khi fork.
