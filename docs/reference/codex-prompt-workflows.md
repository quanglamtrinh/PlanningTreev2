# Codex Prompt Workflows

Tai lieu nay tong hop tat ca workflow trong project co prompt de Codex agent lam viec.
Muc tieu la giup theo doi:

- Workflow nao thuc su goi Codex
- `base_instructions` cua thread la gi
- `turn prompt` duoc ghep nhu the nao
- Moi field trong prompt lay tu dau
- Output contract / tool nao duoc phep goi

Luu y quan trong:

- "Prompt hieu luc" cua Codex khong chi la 1 string.
- Moi workflow thuc te co 4 lop context:
  - `base_instructions` khi `thread/start`
  - `turn prompt` tai moi lan `run_turn_streaming(...)`
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

| Workflow | Base instructions tren thread | Turn prompt duoc ghep o runtime | Field dung trong turn prompt | Output / tool | Code |
|---|---|---|---|---|---|
| Chat | Tro ly huu ich cho PlanningTree, tra loi ro rang va actionable | `Project: {project_name}`<br>`Root goal: {root_goal}`<br><br>`Current task: {title}`<br>`Description: {description}`<br><br>`Ancestors:` ...<br>`Completed siblings:` ...<br><br>`---`<br>`User message:`<br>`{user_content}` | `project_name`, `root_goal`, `title`, `description`, `ancestors`, `completed_siblings`, `user_content` | Khong co dynamic tool rieng | [chat_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/chat_prompt_builder.py#L24) · [chat_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/chat_service.py#L242) · [chat_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/chat_service.py#L359) |
| Split `workflow` | PlanningTree split assistant; phai goi `emit_render_data(kind='split_result', payload=...)`; neu co task frame thi phai coi cac shaping decisions trong frame la rang buoc | `{retry_feedback?}`<br><br>`You are a decomposition agent...`<br>`Split a parent task into a small set of sequential workflow-based subtasks.`<br><br>`Runtime context:`<br>`- Parent task: {current_node_prompt}`<br>`- Task frame:` `{frame_content?}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br>`- Completed sibling context:` ...<br><br>`Output contract:` schema `subtasks[{id,title,objective,why_now}]` | `current_node_prompt`, `frame_content`, `root_prompt`, `parent_chain_prompts`, `prior_node_summaries_compact`, `retry_feedback` | `emit_render_data(kind="split_result", payload=...)` | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L164) · [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L11) · [split_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/split_service.py#L163) |
| Split `simplify_workflow` | Giong split o tren | Giong cau truc split, nhung mode body doi thanh: tim core workflow nho nhat roi them lai phan con lai theo thu tu phu thuoc | Giong split `workflow` | `emit_render_data(...)` | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L42) |
| Split `phase_breakdown` | Giong split o tren | Giong cau truc split, nhung mode body doi thanh: chia theo phase delivery tuan tu | Giong split `workflow` | `emit_render_data(...)` | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L72) |
| Split `agent_breakdown` | Giong split o tren | Giong cau truc split, nhung mode body doi thanh: chia theo boundary / risk / dependency khi workflow / phase khong hop | Giong split `workflow` | `emit_render_data(...)` | [split_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/split_prompt_builder.py#L102) |
| Generate Frame | Task-framing assistant; sinh `frame.md`; khong hoi lai; phai goi `emit_frame_content` | `Task context:`<br>`- Current task: {current_node_prompt}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br>`- Completed siblings:` ...<br><br>`Conversation history:`<br>`[user]: ...`<br>`[assistant]: ...`<br><br>`Generate the frame document now. Call emit_frame_content...` | `current_node_prompt`, `root_prompt`, `parent_chain_prompts`, `prior_node_summaries_compact`, `chat_messages[]` | `emit_frame_content(content=...)` | [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L82) · [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L32) · [frame_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/frame_generation_service.py#L185) |
| Generate Clarify | Task-clarification assistant; chi hoi cho `Task-Shaping Fields` chua resolve; moi cau 2-4 options; phai goi `emit_clarify_questions` | `Task context:`<br>`- Current task: {current_node_prompt}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br><br>`Confirmed frame document:`<br>`{frame_content}`<br><br>`Generate clarifying questions for this task now...` | `current_node_prompt`, `root_prompt`, `parent_chain_prompts`, `frame_content` | `emit_clarify_questions(questions=...)` | [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L130) · [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L8) · [clarify_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/clarify_generation_service.py#L209) |
| Generate Spec | Technical spec writer; sinh spec tu confirmed frame; phai goi `emit_spec_content` | `Task context:`<br>`- Current task: {current_node_prompt}`<br>`- Root goal: {root_prompt}`<br>`- Parent chain:` ...<br><br>`Confirmed frame document:`<br>`{frame_content}`<br><br>`Generate a technical implementation spec for this task now...` | `current_node_prompt`, `root_prompt`, `parent_chain_prompts`, `frame_content` | `emit_spec_content(content=...)` | [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L66) · [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L8) · [spec_generation_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/spec_generation_service.py#L213) |

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

#### Base instructions

Frame thread duoc tao voi system prompt mo ta vai tro task-framing assistant, format cua frame, va rule:

- khong invent requirement
- khong hoi clarification
- de trong field shaping neu chua ro
- phai goi `emit_frame_content`

Nguon: [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L32)

#### Turn prompt skeleton

```text
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

Generate the frame document now. Call emit_frame_content with the full markdown content.
```

Nguon: [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L82)

#### Ghi chu

- Day la workflow duy nhat ngoai chat co nhung explicit lich su chat local vao prompt string.
- `chat_messages` duoc doc tu store local cua app, khong phai tu Codex thread.

### 4. Generate Clarify

#### Base instructions

Clarify thread duoc tao voi rule:

- chi hoi cho `Task-Shaping Fields` chua co value
- moi question phai co 2-4 options
- exactly 1 `recommended`
- `field_name` phai match field trong frame
- phai goi `emit_clarify_questions`

Nguon: [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L8)

#### Turn prompt skeleton

```text
Task context:
- Current task: {current_node_prompt}
- Root goal: {root_prompt}
- Parent chain:
  - ...

Confirmed frame document:

{frame_content}

Generate clarifying questions for this task now.
Call emit_clarify_questions with the full list of questions.
```

Nguon: [clarify_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/clarify_prompt_builder.py#L130)

#### Ghi chu

- Clarify ban dau duoc seed deterministic bang parse `Task-Shaping Fields` trong `frame.md`.
- AI clarify chi dung de bien field chua resolve thanh question + options chat luong hon.

Nguon seed: [node_detail_service.py](C:/Users/Thong/PlanningTreeMain/backend/services/node_detail_service.py#L433)

### 5. Generate Spec

#### Base instructions

Spec thread duoc tao voi rule:

- viet technical implementation spec tu confirmed frame
- spec khong phai copy frame
- phai co cac section nhu `Overview`, `Architecture Decisions`, `Implementation Plan`, ...
- phai goi `emit_spec_content`

Nguon: [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L8)

#### Turn prompt skeleton

```text
Task context:
- Current task: {current_node_prompt}
- Root goal: {root_prompt}
- Parent chain:
  - ...

Confirmed frame document:

{frame_content}

Generate a technical implementation spec for this task now.
Call emit_spec_content with the full spec as markdown.
```

Nguon: [spec_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/spec_prompt_builder.py#L66)

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

### Base instructions hieu luc

Thread frame da duoc tao truoc voi rule:

```text
You are a task-framing assistant for the PlanningTree project planning tool.
...
Output the frame by calling emit_frame_content with the full markdown string.
```

Nguon: [frame_prompt_builder.py](C:/Users/Thong/PlanningTreeMain/backend/ai/frame_prompt_builder.py#L32)

### Turn prompt sau khi ghep field

```text
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

Generate the frame document now. Call emit_frame_content with the full markdown content.
```

### Cach field duoc ghep

| Buoc | Du lieu | Cach ghep |
|---|---|---|
| 1 | `node.title` + `node.description` | ghep thanh `current_node_prompt` |
| 2 | `snapshot.project.root_goal` | dua vao dong `Root goal` |
| 3 | ancestor chain | dua vao block `Parent chain` |
| 4 | sibling da done | dua vao block `Completed siblings` |
| 5 | chat history local | dua vao block `Conversation history` |
| 6 | lenh cuoi | append cau lenh `Generate the frame document now...` |

### Prompt hieu luc thuc te cua Codex o workflow nay

Prompt ma model thuc su "nhin thay" khong chi la turn prompt o tren. No bao gom:

1. `base_instructions` cua frame thread
2. turn prompt vua duoc ghep
3. lich su thread neu thread da duoc reuse / resume
4. repo hien tai vi chay voi `cwd=workspace_root`

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
- Vi vay string trong builder la "prompt turn hien tai", con "context hieu luc" thi lon hon.
