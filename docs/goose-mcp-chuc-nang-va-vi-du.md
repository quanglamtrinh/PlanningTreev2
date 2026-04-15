# Goose MCP: Tac Dung Va Vi Du Cu The Cho Tung Chuc Nang

Tai lieu nay giai thich ro tung chuc nang MCP trong repo Goose theo cach thuc dung cho user:
- Chuc nang nay dung de lam gi
- Prompt vi du user co the go
- Goose se giup duoc gi cu the

## 1. Nhin nhanh: MCP trong Goose la gi?

ELI5:
- Goose co the duoc hieu nhu "bo nao AI"
- MCP tools la "hop do nghe"
- Moi extension la 1 bo cong cu chuyen mon (code, nho, web, file, bieu do...)

Luong chung:
1. User dua yeu cau
2. Goose chon tool phu hop
3. Neu thieu tool: Goose co the tim va bat them extension
4. Tool chay, tra ket qua ve chat
5. Goose tiep tuc buoc tiep theo cho den khi xong viec

## 2. Nhom chuc nang MCP trong Goose

Goose co 3 nhom:
- Built-in MCP servers: `autovisualiser`, `computercontroller`, `memory`, `tutorial`
- Platform extensions (chay in-process nhung van theo model MCP tool): `developer`, `analyze`, `todo`, `apps`, `chatrecall`, `extensionmanager`, `summon`, `summarize`, `code_execution`, `tom`, `orchestrator`
- External extensions: ket noi server ben ngoai qua `stdio` hoac `streamable_http`

Luu y quan trong:
- `SSE` da khong duoc ho tro trong Goose (can migrate sang `streamable_http`)

---

## 3. Chi tiet tung extension va tung chuc nang

## 3.1 `autovisualiser` (Built-in)
Muc tieu: bien du lieu thanh bieu do tu dong.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `render_sankey` | Ve luong du lieu/funnel | "Ve funnel tu lead -> demo -> won cho toi" | Tao bieu do flow de thay diem roi rt va ty le chuyen doi |
| `render_radar` | So sanh nhieu tieu chi | "So sanh 3 model theo speed, cost, quality, context" | Ve radar chart de user thay diem manh/yeu theo tung truc |
| `render_donut` | Ti le thanh phan | "Ty trong doanh thu theo nganh hang" | Hien ty trong theo phan tram de chot uu tien nhanh |
| `render_treemap` | Cau truc cap cha-con | "Doanh thu theo category va subcategory" | Ve treemap de thay ngay nhom nao chiem dien tich lon |
| `render_chord` | Quan he giua cac nhom | "Luot chuyen giua cac bo phan A-B-C" | Hien lien ket qua lai giua cac nhom de tim nut that |
| `render_map` | Du lieu dia ly | "Danh dau cac diem giao hang tren ban do" | Ve map co marker de user xem phan bo theo vung |
| `render_mermaid` | So do quy trinh/sequence | "Ve flow xu ly don hang bang mermaid" | Tao diagram de trinh bay quy trinh cho team |
| `show_chart` | Hien chart da tao | "Mo to chart vua tao" | Render chart trong chat (MCP app) |

---

## 3.2 `computercontroller` (Built-in)
Muc tieu: thao tac may tinh, web, va file van phong.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `web_scrape` | Lay noi dung web va luu cache | "Lay noi dung trang pricing cua X" | Crawler trang va tra text co the dung tiep de phan tich |
| `automation_script` | Chay script shell/python/js de tu dong hoa | "Viet script doi ten 200 file theo mau..." | Tu dong hoa thao tac lap lai thay vi user lam tay |
| `computer_control` | Dieu khien UI he thong/ung dung | "Mo browser, vao site A, tim B, chup ket qua" | Dieu huong UI theo buoc, phu hop task khong can code |
| `xlsx_tool` | Doc/sua Excel | "Doc cot doanh thu va tim 5 dong cao nhat" | Truy xuat worksheet/range/cell va xu ly so lieu nhanh |
| `docx_tool` | Doc/sua Word | "Them muc 'Ket luan' vao file report.docx" | Trich xuat text hoac cap nhat noi dung tai lieu |
| `pdf_tool` | Trich xuat text/anh tu PDF | "Doc PDF hop dong va liet ke dieu khoan thanh toan" | Lay text/anh tu PDF de tom tat, search, so sanh |
| `cache` | Quan ly file ket qua tam | "Liet ke file cache va mo file vua scrape" | User co the xem lai artifact da tao |

---

## 3.3 `memory` (Built-in)
Muc tieu: cho Goose "nho" so thich va quy tac lam viec cua user.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `remember_memory` | Luu tri nho theo category/tags/scope | "Nho rang toi thich output ngan gon va co checklist" | Luu preference de cac phien sau lam dung gu user |
| `retrieve_memories` | Lay tri nho theo category | "Lay lai memory category coding-style" | Goi lai chinh xac quy tac da luu de ap dung |
| `remove_memory_category` | Xoa toan bo 1 category | "Xoa toan bo memory category old-project" | Don dep tri nho cu, tranh xung dot quy tac |
| `remove_specific_memory` | Xoa 1 muc cu the | "Xoa memory noi dung 'dung tab'" | Sua tung muc nho sai/het han |

---

## 3.4 `tutorial` (Built-in)
Muc tieu: tai bai hoc huong dan theo buoc.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `load_tutorial` | Nap tutorial markdown co san | "Huong dan toi build MCP extension" | Dua lo trinh hoc tung buoc thay vi tra loi mo ho |

---

## 3.5 `developer` (Platform)
Muc tieu: bo cong cu lam phan mem cot loi.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `tree` | Xem cau truc thu muc + file | "Cho toi overview codebase backend" | Tao ban do code de quyet dinh mo file nao truoc |
| `shell` | Chay lenh terminal | "Chay test va cho toi biet case fail" | Run test/build/lint/git command nhanh va co output |
| `edit` | Sua noi dung file theo find/replace | "Sua ham X theo logic Y" | Patch file dung cho nang cap/refactor/co bug |
| `write` | Tao file moi hoac ghi de file | "Tao file migration SQL moi" | Scaffold file moi nhanh va chinh xac |

---

## 3.6 `analyze` (Platform)
Muc tieu: phan tich code bang AST/tree-sitter.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `analyze` | 3 mode: thu muc, file, symbol-callgraph | "Analyze module auth va ve call graph cua validateToken" | Tim nhanh noi tac dong, phu thuoc, va diem rui ro khi sua |

---

## 3.7 `todo` (Platform)
Muc tieu: quan ly checklist cong viec trong session.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `todo_write` | Ghi de toan bo TODO list | "Tao checklist 6 buoc de migrate DB an toan" | Theo doi tien do ro rang, tranh sot buoc |

---

## 3.8 `apps` (Platform)
Muc tieu: tao mini-app HTML/CSS/JS qua chat.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `list_apps` | Liet ke app da co | "Liet ke cac app hien co" | User biet ngay co gi de tai su dung |
| `create_app` | Tao app moi tu PRD/mo ta | "Tao app JSON formatter" | Sinh app sandbox chay duoc ngay |
| `iterate_app` | Nang cap app theo feedback | "Them dark mode va copy button cho app tren" | Vong lap cai tien nhanh khong can code tay |
| `delete_app` | Xoa app | "Xoa app test-cu" | Don dep app khong con dung |

Ghi chu:
- Apps duoc expose duoi dang resource `ui://apps/...`

---

## 3.9 `chatrecall` (Platform)
Muc tieu: tim va nap context tu chat cu.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `chatrecall` | Search theo query hoac load theo `session_id` | "Tuan truoc minh da chot huong auth nao?" | Goi lai quyet dinh cu de tiep tuc dung mach |

---

## 3.10 `extensionmanager` (Platform)
Muc tieu: bat/tat extension dong theo nhu cau.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `search_available_extensions` | Tim extension kha dung | "Co extension nao de query Postgres khong?" | Tu dong de xuat dung tool dung bai toan |
| `manage_extensions` | Enable/disable extension | "Bat extension github cho phien nay" | Mo rong kha nang ngay trong session hien tai |
| `list_resources` | Liet ke resource tu extension | "Liet ke resource schema DB cua extension X" | Co danh sach du lieu co the doc |
| `read_resource` | Doc noi dung resource cu the | "Doc resource `db://schema/users`" | Dua thang context vao model de xu ly tiep |

---

## 3.11 `summon` (Platform)
Muc tieu: load kien thuc va giao viec cho subagent.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `load` | Liet ke/nap skill, recipe, task result | "Load skill `rust-patterns`" | Nap dung kien thuc vao context truoc khi lam |
| `delegate` | Giao task cho subagent (sync/async) | "Delegate phan tich module billing song song" | Chia nho viec va chay song song de nhanh hon |

---

## 3.12 `summarize` (Platform)
Muc tieu: tom tat nhieu file/thu muc trong 1 lan goi.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `summarize` | Doc file (co filter) + tra loi theo question | "Tom tat `backend/src` va tap trung vao auth flow" | Nhan quickly executive summary khong can doc tay |

---

## 3.13 `code_execution` (Platform)
Muc tieu: goi nhieu tools bang script TypeScript trong 1 lan.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `list_functions` | Liet ke function co the goi | "Cho toi danh sach function co the goi trong code mode" | Biet "API tool" co san truoc khi viet script |
| `get_function_details` | Xem schema I/O function | "Xem chi tiet function `developer/shell`" | Viet script dung tham so, it loi |
| `execute_bash` | Chay command trong code mode (mode phu hop) | "Dung code mode de chay 3 lenh git lien tiep" | Batched command, giam turn tool-call |
| `execute_typescript` | Viet script de orchestrate tools | "Doc package.json, lay version, tao LOG.md trong 1 lan goi" | Gom nhieu buoc vao 1 script, tiet kiem context/tokens |

---

## 3.14 `tom` (Platform)
Muc tieu: inject huong dan "luon nho" moi turn.

`tom` khong co tools goi truc tiep (`tools: []`), nhung rat quan trong:
- Doc `GOOSE_MOIM_MESSAGE_TEXT`
- Doc `GOOSE_MOIM_MESSAGE_FILE`
- Noi dung duoc chen vao moi turn (co gioi han 64KB/nguon)

Vi du:
- User set env: "KHONG upload code ra public"
- Moi turn Goose deu nho rule nay

---

## 3.15 `orchestrator` (Platform, hidden/internal)
Muc tieu: dieu phoi nhieu agent session.

| Tool | Tac dung | Vi du prompt user | Goose giup user nhu the nao |
|---|---|---|---|
| `list_sessions` | Liet ke sessions va trang thai | "Liet ke cac session dang chay" | User nhin toan canh workload |
| `view_session` | Xem/summarize 1 session | "Tom tat session 20260415_3" | Hieu nhanh session khac dang lam gi |
| `start_agent` | Tao agent session moi | "Tao agent moi de scan repo B" | Mo lane song song |
| `send_message` | Gui message den agent do | "Bao agent B tiep tuc task migration" | Dieu khien tu xa |
| `interrupt_agent` | Dung session dang ban | "Dung agent B ngay" | Cat task khi loi/qua lau |

---

## 4. Vi du workflow ro rang theo bai toan that

## Workflow A: Sua bug backend nhanh va an toan
Prompt:
`"SUA loi 500 o /api/users, giu nguyen behavior cu, chay test xong bao ket qua"`

Tool flow de xay ra:
1. `todo_write`: tao checklist
2. `analyze`: tim call graph route -> service -> repo
3. `developer.tree` + `developer.shell`: tim file va test fail
4. `developer.edit`: patch code
5. `developer.shell`: re-test
6. Bao cao ket qua + file da sua

Gia tri cho user:
- It bo sot buoc
- Co test evidence
- Giam rui ro fix sai cho

## Workflow B: User thieu tool giua chung
Prompt:
`"Query giup toi bang orders trong Postgres production-readonly"`

Tool flow:
1. `search_available_extensions`
2. `manage_extensions(action=enable, extension_name=...)`
3. Goi tool cua extension Postgres
4. Neu xong viec: `manage_extensions(action=disable, ...)`

Gia tri:
- Khong can user tu setup thu cong trong luc chat
- Goose mo dung tool cho dung task

## Workflow C: Lam viec dai han co tri nho + guardrail
Prompt:
`"Nho rang du an nay cam upload code ra public, va style log la JSON"`

Tool flow:
1. `remember_memory` (luu quy tac team)
2. `tom` inject moi turn qua env (guardrail bat buoc)
3. Session sau `retrieve_memories` khi can

Gia tri:
- Team rule duoc ap dung on dinh
- Giam loi "quen quy uoc"

---

## 5. Goi y van hanh an toan

Rui ro cao (can can nhac mode approve):
- `developer.shell`, `developer.edit`, `developer.write`
- `computer_control`, `automation_script`
- `code_execution.execute_typescript`
- `orchestrator.send_message/start_agent`

Rui ro thap:
- `analyze`, `summarize`, `chatrecall`, `tutorial`, phan lon `autovisualiser`, `memory`

Goi y:
1. Neu task nhay cam: dung mode phe duyet (`approve`/`smart_approve`)
2. Bat `.gooseignore` cho file nhay cam
3. Dung `extensionmanager` de giu bo tool gon (de model chon tool tot hon)

---

## 6. Mapping nhanh: User muon gi thi dung gi?

- Muon sua code + chay test: `developer` + `analyze`
- Muon tim lai quyet dinh cu: `chatrecall`
- Muon nho quy tac team: `memory` (+ `tom` neu can guardrail cung)
- Muon bieu do tu du lieu: `autovisualiser`
- Muon tu dong hoa thao tac may tinh/file: `computercontroller`
- Muon chia task song song: `summon` (+ `orchestrator` noi bo)
- Muon tom tat nhieu file nhanh: `summarize`
- Muon goi nhieu tools trong 1 script: `code_execution`

---

## 7. Nguon doi chieu trong repo Goose

- `crates/goose-mcp/src/lib.rs`
- `crates/goose-mcp/src/mcp_server_runner.rs`
- `crates/goose/src/agents/platform_extensions/mod.rs`
- `crates/goose/src/agents/platform_extensions/*.rs`
- `crates/goose/src/agents/extension_manager.rs`
- `crates/goose/src/agents/extension.rs`
- `crates/goose/src/agents/mcp_client.rs`
- `documentation/docs/getting-started/using-extensions.md`

