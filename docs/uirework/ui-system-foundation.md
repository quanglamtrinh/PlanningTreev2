# Desktop Workflow UI System Foundation

Tài liệu tổng hợp dựa trên chuỗi làm việc trước đó: **UI audit -> design principles -> design tokens -> component system tối thiểu** cho desktop workflow app (tree/graph/detail/spec).

Giả định phạm vi đánh giá:
- App desktop light theme, nhiều panel đồng thời.
- Mục tiêu sản phẩm: scan nhanh cấu trúc task, hiểu state hiện tại, biết bước tiếp theo, đọc spec thoải mái, thao tác không rối.
- Ưu tiên: consistency, readability, hierarchy, giảm cognitive load.

---

## Part 1 - UI Audit

### A. Executive summary
- UI đã có nền tảng tốt về bố cục đa panel và hướng minimal, nhưng mức đồng nhất giữa các vùng còn chưa ổn định.
- Vấn đề lớn nhất nằm ở: **state clarity**, **hierarchy giữa các panel**, và **readability cho nội dung dài**.
- Một số pattern đang bị phân mảnh (badge, button, tab, panel shell), làm tăng nhiễu thị giác và giảm tốc độ scan.
- Nếu sửa đúng thứ tự ưu tiên, app sẽ giữ được cảm giác calm/professional nhưng vẫn information-dense.

### B. Những điểm đang làm tốt
- Cấu trúc macro-layout rõ: sidebar -> canvas -> detail/spec/action.
- Light theme và border mảnh tạo nền dễ đọc, không nặng kiểu dashboard.
- Có tách vùng chức năng theo nhiệm vụ (overview, execution, audit).
- Tabs Ask/Execution/Audit giúp chia mode logic tương đối rõ.
- Nhiều khu vực đã tránh lạm dụng shadow, phù hợp mục tiêu minimal.

### C. Những vấn đề lớn nhất về consistency
- Panel shell chưa thật sự đồng nhất: padding, header height, divider, corner radius khác nhau giữa vùng.
- Status mapping chưa một chuẩn duy nhất: cùng trạng thái nhưng khác nhãn/màu/độ nhấn ở các màn.
- Button hierarchy chưa chặt: có vùng xuất hiện nhiều CTA cùng cấp, hoặc CTA và secondary cạnh tranh nhau.
- Tab style chưa nhất quán tuyệt đối giữa primary context tab và tab cục bộ.
- Card pattern bị phân mảnh: node card, list card, content block có cấu trúc khác nhau quá nhiều.

### D. Những vấn đề lớn nhất về readability
- Một số khối text dài chưa tối ưu line length và line-height, gây mỏi mắt khi đọc spec lâu.
- Typography hierarchy còn dày mức trung gian, làm giảm tốc độ scan.
- Micro-label/meta text trong task/detail đôi lúc quá nhỏ hoặc quá sát nhau.
- Màu text secondary/muted có lúc thiếu tương phản trong nền sáng.
- Nhiều điểm dùng icon + badge + text cùng lúc, làm loãng trọng tâm đọc.

### E. Những vấn đề lớn nhất về hierarchy
- Chưa luôn rõ panel nào đang là trọng tâm hiện tại.
- Active state giữa sidebar item, node active, tab active, section active chưa tạo chuỗi nhận thức nhất quán.
- Vùng action bar/composer đôi lúc không thể hiện đủ rõ "bước tiếp theo là gì".
- Có chỗ thừa nhấn mạnh (nhiều màu, nhiều pill/border), có chỗ thiếu nhấn mạnh (next action, blocking reason).
- Một số section header chưa đủ phân tầng so với nội dung bên dưới.

### F. Phân tích theo từng vùng UI

#### 1) Sidebar trái
- Vấn đề: indent/nested rhythm chưa tuyệt đối ổn định, active marker và badge có lúc cạnh tranh nhau.
- Tác động: khó scan tree nhanh, khó biết focus hiện tại thuộc project hay task.
- Hướng chỉnh: cố định row height, indent step, vị trí status/meta; giữ đúng một active affordance.

#### 2) Graph / canvas
- Vấn đề: node card và connector có lúc truyền tải quá nhiều tín hiệu cùng lúc.
- Tác động: nhìn tổng thể nhanh nhưng khó xác định critical path và trạng thái blocked.
- Hướng chỉnh: chuẩn hóa node anatomy, giảm decoration, làm rõ semantics connector (hierarchy vs dependency).

#### 3) Split view
- Vấn đề: tỉ lệ chú ý giữa pane trái/phải chưa ổn định, divider chưa luôn truyền tải vai trò resizable rõ.
- Tác động: user dễ mất định hướng khi chuyển overview -> detail.
- Hướng chỉnh: dùng panel priority rõ, divider có affordance nhất quán, min/max width logic.

#### 4) Task detail content
- Vấn đề: block thông tin chưa cùng một nhịp spacing/typography, meta đôi lúc lấn trọng tâm chính.
- Tác động: chậm đọc, khó xác định "what matters now".
- Hướng chỉnh: section header chuẩn, content block chuẩn, giảm cấp text thừa.

#### 5) Spec/document panel
- Vấn đề: reading comfort chưa tối ưu cho session dài (line length, paragraph rhythm, heading cadence).
- Tác động: mỏi mắt, bỏ sót điều kiện quan trọng trong spec/review.
- Hướng chỉnh: fixed reading column, type scale cho đọc dài, highlight/annotation tiết chế.

#### 6) Action bar / composer / CTA area
- Vấn đề: chưa luôn rõ action nào là primary và khi disabled thiếu lý do hiển thị rõ.
- Tác động: user không biết bước tiếp theo hoặc vì sao chưa thực thi được.
- Hướng chỉnh: một primary action duy nhất theo context, disabled-with-reason bắt buộc, secondary de-emphasis.

### G. Danh sách vấn đề theo mức độ critical / major / minor

#### Critical
- C1. Chưa rõ "next step" tại action/composer ở một số trạng thái.
- C2. Active state giữa navigation/canvas/detail chưa tạo được một đường dẫn nhận thức liên tục.
- C3. State semantics chưa thống nhất (label + color + emphasis), gây hiểu nhầm trạng thái.
- C4. Khả năng đọc spec dài chưa đủ thoải mái cho làm việc lâu.

#### Major
- M1. Panel shell và spacing rhythm chưa đồng bộ giữa các vùng.
- M2. Typography hierarchy dư cấp, gây nhiễu khi scan.
- M3. Tab/button patterns còn rời rạc theo màn.
- M4. Node/card pattern chưa chuẩn hóa anatomy.
- M5. Visual noise từ badge/meta/icon dày ở vùng dense.
- M6. Divider/resizable affordance chưa đủ rõ cho desktop behavior.

#### Minor
- m1. Một số hover/focus treatment chưa đồng bộ.
- m2. Trọng lượng border giữa panel và card chưa nhất quán.
- m3. Empty/loading/error state chưa dùng cùng cấu trúc component.
- m4. Một số nhãn ngắn chưa theo cùng writing style.

### H. 10 ưu tiên sửa đầu tiên
1. Chuẩn hóa state model toàn app: label + color + emphasis mapping duy nhất.
2. Chuẩn hóa CTA hierarchy: mỗi panel chỉ một primary action.
3. Thiết kế lại composer states theo chuẩn `idle/focus/disabled-with-reason/sending/error`.
4. Chuẩn hóa panel shell (padding, header height, border, radius).
5. Chuẩn hóa sidebar tree item (row height, indent, active marker).
6. Chuẩn hóa workflow node anatomy + connector semantics.
7. Tối ưu document/spec reading mode (line length, line-height, heading spacing).
8. Rút gọn typography scale và khóa role-based text styles.
9. Chuẩn hóa tab pattern giữa global context và local section.
10. Chuẩn hóa empty/loading/error templates theo panel type.

---

## Part 2 - Design Principles

### 1. Principle name: One Panel, One Focus
- Ý nghĩa: Mỗi panel chỉ phục vụ một nhiệm vụ chính tại một thời điểm.
- Áp dụng trong app này như thế nào: sidebar để điều hướng; canvas để quan hệ workflow; detail/spec để hiểu và hành động.
- Ví dụ đúng: panel detail chỉ có một CTA `Finish review`, action phụ chuyển thành ghost/link.
- Ví dụ sai: cùng panel hiển thị đồng thời nhiều CTA mạnh như `Run`, `Confirm`, `Finish`.

### 2. Principle name: State Before Style
- Ý nghĩa: Trạng thái phải rõ ràng và nhất quán trước khi nghĩ đến trang trí.
- Áp dụng trong app này như thế nào: mọi nơi dùng cùng status dictionary (draft, in-progress, review, done, blocked).
- Ví dụ đúng: `review` luôn cùng nhãn, cùng badge treatment, cùng thứ tự ưu tiên.
- Ví dụ sai: `review` khi thì vàng, khi thì xanh; lúc ghi `In QA`, lúc ghi `Reviewing`.

### 3. Principle name: Read in Layers
- Ý nghĩa: Nội dung phải scan theo tầng: tiêu đề -> tóm tắt -> chi tiết.
- Áp dụng trong app này như thế nào: section header rõ, body text vừa đủ, meta de-emphasized.
- Ví dụ đúng: task detail mở đầu bằng mục tiêu và next step, metadata đặt sau.
- Ví dụ sai: metadata dày ở đầu block làm chìm nội dung chính.

### 4. Principle name: Structure Over Decoration
- Ý nghĩa: Dùng layout, spacing, alignment để tạo rõ ràng; giảm color/effect dư.
- Áp dụng trong app này như thế nào: phân tách panel bằng border mảnh và spacing đều thay vì nền/gradient mạnh.
- Ví dụ đúng: node active nổi bằng border + subtle background.
- Ví dụ sai: node active dùng shadow đậm + glow + màu nóng bão hòa.

### 5. Principle name: Stable Patterns, Reused Everywhere
- Ý nghĩa: Một loại vấn đề chỉ nên có một pattern giải quyết.
- Áp dụng trong app này như thế nào: badge/button/tab/panel/container dùng shared component, không custom theo màn.
- Ví dụ đúng: tất cả tab dùng chung anatomy + states.
- Ví dụ sai: mỗi màn dùng một kiểu tab active indicator khác nhau.

### 6. Principle name: Guide the Next Action
- Ý nghĩa: UI luôn trả lời được câu hỏi "tiếp theo tôi làm gì?".
- Áp dụng trong app này như thế nào: composer + action bar luôn có primary action rõ và disabled reason khi cần.
- Ví dụ đúng: nút `Confirm` disabled kèm note "Cần chọn 1 task đang active".
- Ví dụ sai: nút disabled không có lý do.

### 7. Principle name: Calm Density
- Ý nghĩa: Information-dense nhưng không căng thẳng thị giác.
- Áp dụng trong app này như thế nào: giới hạn số lớp nhấn mạnh trên mỗi vùng, ưu tiên typography rõ và khoảng thở hợp lý.
- Ví dụ đúng: một row task có title + một status + một meta chính.
- Ví dụ sai: một row có icon, 3 badge, 2 counter, 2 action luôn hiển thị.

### Design decision filter (7 câu hỏi)
1. Quyết định này có làm rõ panel trọng tâm hiện tại không?
2. User có biết ngay task/step nào đang active không?
3. User có biết bước tiếp theo là gì không?
4. Quyết định này tăng hay giảm độ dễ đọc cho nội dung dài?
5. Pattern này đã tồn tại trong design system chưa, hay đang tạo pattern mới không cần thiết?
6. Có đang thêm nhấn mạnh thị giác không cần thiết (màu, border, effect, motion) không?
7. Nếu áp dụng quyết định này trên toàn app, mức độ nhất quán có tăng lên không?

---

## Part 3 - Design Tokens

### A. Token architecture tổng thể
- Mô hình 3 lớp:
- `ref.*`: primitive values (hex, px, duration).
- `sys.*`: semantic tokens theo vai trò UI.
- `cmp.*`: alias theo component (chỉ dùng khi cần override có kiểm soát).
- Quy tắc:
- Ưu tiên dùng `sys.*` trong thiết kế và code.
- Không dùng trực tiếp màu primitive trong component trừ khi khai báo token mới.
- Mỗi state/role chỉ có một token chính.

Ví dụ naming:
- `sys.color.bg.app`
- `sys.color.text.primary`
- `sys.space.12`
- `sys.radius.md`
- `sys.motion.fast`

### B. Color tokens

#### Core neutrals + accent
| Token | Value | Usage |
|---|---|---|
| `sys.color.bg.app` | `#F6F4EF` | App background |
| `sys.color.bg.panel` | `#FBFAF7` | Panel background |
| `sys.color.bg.card` | `#FFFFFF` | Card/content block |
| `sys.color.bg.subtle` | `#F3F0E9` | Hover/subtle area |
| `sys.color.border.default` | `#E2DED4` | Panel/card borders |
| `sys.color.border.strong` | `#CEC7BA` | Emphasis border |
| `sys.color.text.primary` | `#1F2328` | Primary text |
| `sys.color.text.secondary` | `#4A5460` | Secondary text |
| `sys.color.text.muted` | `#6E7783` | Meta/muted |
| `sys.color.accent.warm` | `#B86A2C` | Accent primary |
| `sys.color.accent.warmSubtle` | `#F5E5D6` | Accent subtle bg |

#### Semantic states
| Token | Value | Usage |
|---|---|---|
| `sys.color.state.done` | `#2F7A4F` | Done/success |
| `sys.color.state.review` | `#9A6A1B` | In review |
| `sys.color.state.draft` | `#64707D` | Draft |
| `sys.color.state.warning` | `#B7791F` | Warning |
| `sys.color.state.error` | `#B33A3A` | Error |
| `sys.color.state.info` | `#2F6EA3` | Info |

#### Interaction states
| Token | Value | Usage |
|---|---|---|
| `sys.color.interactive.hover` | `rgba(31,35,40,0.04)` | Hover overlay |
| `sys.color.interactive.selectedBg` | `#EFE7DB` | Selected row/card bg |
| `sys.color.interactive.selectedBorder` | `#D5C2AA` | Selected border |
| `sys.color.interactive.active` | `#B86A2C` | Active indicator |
| `sys.color.interactive.disabledBg` | `#F1EEE7` | Disabled bg |
| `sys.color.interactive.disabledText` | `#98A0AA` | Disabled text |

### C. Typography tokens

Font families:
- `sys.font.sans`: `"Segoe UI", "Inter", "Noto Sans", sans-serif`
- `sys.font.mono`: `"Cascadia Code", "JetBrains Mono", monospace`

Type scale (role-based):
| Token | Size/Line | Weight | Usage |
|---|---|---|---|
| `sys.type.appTitle` | `20/28` | 600 | App/page title |
| `sys.type.sectionTitle` | `16/24` | 600 | Section header |
| `sys.type.nodeTitle` | `14/20` | 600 | Node title |
| `sys.type.body` | `14/22` | 400 | Main reading text |
| `sys.type.bodyDense` | `13/20` | 400 | Dense list/rows |
| `sys.type.label` | `12/16` | 600 | Labels/buttons |
| `sys.type.meta` | `12/16` | 400 | Meta text |
| `sys.type.badge` | `11/14` | 600 | Badge text |
| `sys.type.code` | `13/20` | 400 | Code/spec blocks |

### D. Spacing / radius / border / elevation tokens

Spacing scale (4pt-based):
- `sys.space.4 = 4`
- `sys.space.8 = 8`
- `sys.space.12 = 12`
- `sys.space.16 = 16`
- `sys.space.20 = 20`
- `sys.space.24 = 24`
- `sys.space.32 = 32`
- `sys.space.40 = 40`

Spacing usage rhythm:
- Panel padding: `16`
- Section gap: `24`
- Card padding: `12` hoặc `16`
- Row item horizontal padding: `12`
- Row item vertical height: `32` hoặc `36`
- Graph node internal gap: `8`
- Composer/action bar padding: `12`

Radius:
- `sys.radius.xs = 4`
- `sys.radius.sm = 6`
- `sys.radius.md = 8`
- `sys.radius.lg = 10`
- `sys.radius.xl = 12`

Border:
- `sys.border.width.thin = 1`
- `sys.border.width.strong = 2`
- `sys.border.default = 1px solid sys.color.border.default`

Elevation/shadow:
- `sys.elevation.none = none`
- `sys.elevation.xs = 0 1px 2px rgba(31,35,40,0.06)`
- `sys.elevation.sm = 0 2px 6px rgba(31,35,40,0.08)` (chỉ cho overlay/popover)

Opacity:
- `sys.opacity.disabled = 0.5`
- `sys.opacity.subtle = 0.72`
- `sys.opacity.overlay = 0.08`

Motion/transition (chỉ khi cần):
- `sys.motion.fast = 120ms`
- `sys.motion.base = 180ms`
- `sys.motion.slow = 240ms`
- `sys.easing.standard = cubic-bezier(0.2, 0, 0, 1)`
- `sys.easing.exit = cubic-bezier(0.4, 0, 1, 1)`

### E. State token rules
- Quy tắc 1: State semantics tách khỏi component type. Badge, node, list row cùng dùng một map state.
- Quy tắc 2: State quan trọng dùng tối đa 2 lớp nhấn mạnh: color + weight/border. Không thêm shadow/glow.
- Quy tắc 3: `active`, `selected`, `focused` là ba trạng thái khác nhau:
- `active`: ngữ cảnh hiện tại.
- `selected`: user đã chọn item.
- `focus`: keyboard focus.
- Quy tắc 4: Disabled luôn có cả visual token và explanatory text nếu chặn hành động chính.
- Quy tắc 5: Error/warning không dùng làm nền phủ toàn vùng nếu không bắt buộc.

### F. Rules sử dụng token trong app này
- Sidebar:
- Dùng `bg.panel`, row hover `interactive.hover`, active marker `interactive.active`.
- Task/graph states:
- Dùng `state.*` theo dictionary cố định, không tự tạo màu mới.
- Document viewer:
- Luôn dùng `type.body` + line-height đọc dài; code dùng `font.mono`.
- Action area:
- Primary button dùng accent, secondary dùng neutral; disabled dùng token disabled.
- Panel/card:
- Border mảnh + radius vừa; hạn chế shadow.

### G. Các lỗi dễ gặp khi dùng sai token
- Dùng màu primitive trực tiếp trong component thay vì semantic token.
- Tạo quá nhiều shade cho cùng một trạng thái.
- Override typography local khiến hierarchy bị vỡ.
- Dùng spacing lẻ ngoài scale 4pt gây lệch rhythm.
- Dùng shadow để tạo hierarchy thay vì layout/spacing.
- Trộn `selected` và `active` thành một style, gây mơ hồ điều hướng.

---

## Part 4 - Component System tối thiểu

### A. Danh sách core components
1. `SidebarProjectItem`
2. `SidebarTaskItem` (nested)
3. `WorkflowNodeCard`
4. `ConnectorLine` / `RelationIndicator`
5. `StatusBadge`
6. `Tab`
7. `SectionHeader`
8. `PanelContainer`
9. `ContentBlock`
10. `ButtonPrimary` (CTA)
11. `ButtonSecondary` / `ButtonGhost`
12. `InlineAction`
13. `AlertBanner`
14. `DocumentViewerBlock`
15. `ComposerBar`
16. `ProgressWidget`
17. `EmptyState`
18. `LoadingState`
19. `SplitDivider` / `ResizablePanel`

### B. Chi tiết từng component

#### 1) Sidebar project item
- Mục đích: điều hướng cấp project, cho biết project active.
- Khi nào dùng: danh sách project ở sidebar trái.
- Khi nào không dùng: không dùng cho task con.
- Anatomy: row container, icon, title, optional count, optional trailing action.
- Variants: `default`, `active`, `pinned`, `compact`.
- States: `default`, `hover`, `selected`, `focus-visible`, `disabled`, `drag-over`.
- Content rules: title 1 dòng ellipsis; count chỉ hiện khi có ý nghĩa.
- Spacing rules: height 36, horizontal padding 12, gap 8.
- Accessibility notes: hit area >= 32, keyboard Enter/Space, focus ring rõ.
- Lỗi consistency hay gặp: icon size lệch, active quá nhiều màu, count lệch cột.

#### 2) Sidebar task item / nested item
- Mục đích: hiển thị tree task + trạng thái scan nhanh.
- Khi nào dùng: mọi task trong tree sidebar.
- Khi nào không dùng: không dùng như detail card.
- Anatomy: indent rail, expander, status dot/icon, title, optional meta/badge, optional inline action.
- Variants: `parent`, `leaf`, `active`, `with-meta`.
- States: `collapsed`, `expanded`, `active`, `hover`, `focus`, `disabled`.
- Content rules: title 1 dòng; meta ngắn; tránh 2 badge cạnh nhau.
- Spacing rules: row 32, indent step cố định 12 hoặc 16.
- Accessibility notes: hỗ trợ phím mũi tên trái/phải; `aria-level`.
- Lỗi consistency hay gặp: indent không theo scale, icon trạng thái lẫn lộn, active marker đổi vị trí.

#### 3) Workflow node card
- Mục đích: đơn vị thông tin chính trên canvas.
- Khi nào dùng: biểu diễn step/task trên graph.
- Khi nào không dùng: không dùng thay panel detail.
- Anatomy: header (status + title), body (summary), footer (meta/progress), connector anchors.
- Variants: `default`, `active`, `blocked`, `done`, `group`.
- States: `default`, `hover`, `selected`, `focus`, `dragging`, `dimmed`, `editing`.
- Content rules: title <= 2 dòng; summary <= 2 dòng; meta <= 2 item.
- Spacing rules: padding 12, vertical gap 8, min width 220.
- Accessibility notes: focus ring keyboard; không chỉ dùng màu cho state.
- Lỗi consistency hay gặp: quá nhiều chip/icon, border/shadow drift, active và selected giống nhau.

#### 4) Connector line / relation indicator
- Mục đích: thể hiện quan hệ và thứ tự luồng.
- Khi nào dùng: nối parent-child/dependency.
- Khi nào không dùng: không dùng để trang trí.
- Anatomy: line path, arrowhead/terminator, optional relation label.
- Variants: `hierarchy`, `dependency`, `blocked-by`, `reference`.
- States: `default`, `hover`, `selected`, `muted`.
- Content rules: label chỉ bật khi quan hệ không tự hiểu.
- Spacing rules: stroke 1; route cách node edge tối thiểu 8.
- Accessibility notes: phân biệt relation bằng pattern (solid/dashed), không chỉ màu.
- Lỗi consistency hay gặp: lạm dụng nhiều màu line, animation liên tục gây nhiễu.

#### 5) Status badge
- Mục đích: mã hóa trạng thái ngắn gọn.
- Khi nào dùng: task row, node, panel header, list.
- Khi nào không dùng: không dùng thay alert banner.
- Anatomy: capsule nền nhẹ, text ngắn, optional dot/icon.
- Variants: `draft`, `in-progress`, `review`, `done`, `warning`, `error`, `info`.
- States: `subtle`, `emphasis` (chỉ critical), `disabled`.
- Content rules: 1-2 từ; một trạng thái chỉ một nhãn toàn app.
- Spacing rules: height 20, horizontal padding 8, fixed badge text style.
- Accessibility notes: contrast đủ; không chỉ dựa vào màu.
- Lỗi consistency hay gặp: cùng state khác nhãn/màu giữa màn.

#### 6) Tab
- Mục đích: chuyển ngữ cảnh ngang cấp (Ask/Execution/Audit).
- Khi nào dùng: đổi mode cùng cấp.
- Khi nào không dùng: không dùng như filter chip hoặc stepper.
- Anatomy: tab list, tab item label, optional count, active indicator.
- Variants: `primary-tabs`, `secondary-tabs`.
- States: `default`, `hover`, `active`, `focus`, `disabled`.
- Content rules: nhãn ngắn 1-2 từ; hạn chế icon.
- Spacing rules: height 36, horizontal padding 12/tab.
- Accessibility notes: role `tablist/tab`; keyboard arrows.
- Lỗi consistency hay gặp: mỗi màn một kiểu active indicator.

#### 7) Section header
- Mục đích: chia tầng thông tin trong panel.
- Khi nào dùng: đầu section trong detail/spec/list.
- Khi nào không dùng: không dùng cho app title.
- Anatomy: title, optional subtitle/meta, trailing actions.
- Variants: `plain`, `with-divider`, `sticky`.
- States: `default`, `collapsed`, `expanded`.
- Content rules: title ngắn; subtitle tối đa 1 dòng.
- Spacing rules: top margin theo section rhythm; title-body gap cố định.
- Accessibility notes: semantic heading level rõ (`h2/h3`).
- Lỗi consistency hay gặp: heading level nhảy cóc, section gap thiếu nhất quán.

#### 8) Panel container
- Mục đích: khung chuẩn cho mọi vùng lớn.
- Khi nào dùng: sidebar, canvas panel, detail panel, spec panel.
- Khi nào không dùng: không dùng cho block con nhỏ.
- Anatomy: shell, optional header, scroll body, optional footer.
- Variants: `sidebar-panel`, `content-panel`, `utility-panel`.
- States: `default`, `active-context`, `collapsed`, `resizing`.
- Content rules: mỗi panel chỉ một trọng tâm.
- Spacing rules: panel padding cố định, border 1, radius thống nhất.
- Accessibility notes: `aria-label` cho panel.
- Lỗi consistency hay gặp: panel nào cũng đòi attention ngang nhau.

#### 9) Content block
- Mục đích: đơn vị đọc/scan trong panel.
- Khi nào dùng: text block, key-value, checklist, note.
- Khi nào không dùng: không thay cho graph node.
- Anatomy: optional block title, body, optional meta/actions.
- Variants: `text`, `kv`, `list`, `code-snippet`.
- States: `default`, `editable`, `selected`, `empty`.
- Content rules: chunk ngắn; tránh trộn nhiều typographic levels.
- Spacing rules: padding 12-16, block-to-block gap cố định.
- Accessibility notes: line-height thoải mái cho đọc.
- Lỗi consistency hay gặp: card hóa mọi block gây nặng visual.

#### 10) CTA button
- Mục đích: hành động chính của ngữ cảnh.
- Khi nào dùng: `Confirm`, `Finish`, `Run`, `Submit`.
- Khi nào không dùng: không dùng cho thao tác phụ.
- Anatomy: container, verb-first label, optional icon, loading spinner.
- Variants: `primary`, `destructive-primary` (hạn chế).
- States: `default`, `hover`, `pressed`, `focus`, `loading`, `disabled`.
- Content rules: hành động rõ nghĩa, tránh label mơ hồ.
- Spacing rules: height 32 hoặc 36, horizontal padding ổn định.
- Accessibility notes: contrast đủ cao; disabled có lý do khi cần.
- Lỗi consistency hay gặp: nhiều primary buttons cùng một cụm.

#### 11) Secondary button / ghost button
- Mục đích: hành động phụ không tranh trọng tâm.
- Khi nào dùng: `Open`, `Cancel`, `Review later`.
- Khi nào không dùng: không dùng cho hành động hệ quả lớn.
- Anatomy: button shell + label.
- Variants: `secondary`, `ghost`.
- States: `default`, `hover`, `focus`, `disabled`.
- Content rules: label ngắn; không cạnh tranh CTA.
- Spacing rules: cùng height với CTA trong cùng cụm.
- Accessibility notes: ghost vẫn phải đủ contrast.
- Lỗi consistency hay gặp: ghost ở màn này như link, màn khác như button chính.

#### 12) Inline action
- Mục đích: thao tác nhanh cấp item.
- Khi nào dùng: `Edit`, `Open`, `Retry`, `More`.
- Khi nào không dùng: không dùng cho destructive action thiếu confirm.
- Anatomy: icon button hoặc text action nhỏ.
- Variants: `icon-only`, `text`, `icon+text`.
- States: `default`, `hover`, `focus`, `disabled`.
- Content rules: tối đa 1-2 inline actions chính trên item.
- Spacing rules: hit area >= 28; cách text chính >= 8.
- Accessibility notes: icon-only cần accessible label.
- Lỗi consistency hay gặp: luôn hiển thị toàn bộ actions làm nhiễu.

#### 13) Alert / warning banner
- Mục đích: thông báo cảnh báo/lỗi/blocking quan trọng.
- Khi nào dùng: system error, prerequisite thiếu, warning hành động.
- Khi nào không dùng: không dùng cho status thường nhật.
- Anatomy: icon, message, optional action, optional dismiss.
- Variants: `info`, `warning`, `error`, `success`.
- States: `shown`, `dismissed`, `persistent`.
- Content rules: câu ngắn, kèm action cụ thể.
- Spacing rules: padding 12, đặt sát ngữ cảnh liên quan.
- Accessibility notes: error quan trọng dùng live region phù hợp.
- Lỗi consistency hay gặp: banner quá bão hòa màu và xuất hiện quá thường xuyên.

#### 14) Document/spec viewer block
- Mục đích: đọc spec/review dài không mỏi mắt.
- Khi nào dùng: tài liệu, acceptance criteria, audit notes.
- Khi nào không dùng: không dùng cho input ngắn.
- Anatomy: viewer header, reading column, optional annotation rail.
- Variants: `read`, `review`, `diff`.
- States: `loading`, `ready`, `selection`, `commenting`.
- Content rules: giới hạn line length; heading hierarchy rõ; code block thống nhất.
- Spacing rules: paragraph spacing cố định; section gap lớn hơn row gap.
- Accessibility notes: hỗ trợ zoom text, keyboard scroll, selection rõ.
- Lỗi consistency hay gặp: font quá nhỏ, line quá dài, highlight quá nhiều kiểu.

#### 15) Input / composer bar
- Mục đích: nhập lệnh/hỏi/ghi chú để thực thi tiếp.
- Khi nào dùng: Ask/Execution command area.
- Khi nào không dùng: không dùng thay editor dài.
- Anatomy: input area, optional context chip, primary send/confirm, helper text.
- Variants: `single-line`, `multi-line`, `disabled-with-reason`.
- States: `idle`, `focus`, `typing`, `sending`, `disabled`, `error`.
- Content rules: placeholder định hướng hành động; disabled phải có lý do.
- Spacing rules: min height 40; padding 8-12; button cùng baseline.
- Accessibility notes: Enter/Shift+Enter rõ; label cho screen reader.
- Lỗi consistency hay gặp: disabled không giải thích; input và nút lệch trục.

#### 16) Progress widget
- Mục đích: cho biết tiến độ và next step.
- Khi nào dùng: task detail, node footer, execution summary.
- Khi nào không dùng: không thay status badge.
- Anatomy: label, meter, numeric/text progress, optional next-step hint.
- Variants: `linear`, `compact`, `step-progress`.
- States: `not-started`, `in-progress`, `paused`, `done`, `blocked`.
- Content rules: luôn có số hoặc step hiện tại; tránh copy mơ hồ.
- Spacing rules: meter height cố định; text cách meter 6-8.
- Accessibility notes: có text thay thế cho meter.
- Lỗi consistency hay gặp: màu meter và badge mâu thuẫn nhau.

#### 17) Empty state
- Mục đích: hướng dẫn khi chưa có dữ liệu.
- Khi nào dùng: first-use hoặc no-results.
- Khi nào không dùng: không dùng khi loading.
- Anatomy: title, short explanation, one primary action, optional secondary link.
- Variants: `first-use`, `no-result`, `no-access`.
- States: `default`.
- Content rules: nói rõ lý do trống + bước tiếp theo.
- Spacing rules: căn giữa gọn, max width hợp lý, khoảng trắng thoáng.
- Accessibility notes: primary action dễ tab.
- Lỗi consistency hay gặp: copy dài kiểu marketing, quá nhiều CTA.

#### 18) Loading state
- Mục đích: phản hồi hệ thống đang xử lý.
- Khi nào dùng: tải panel/list/node/document.
- Khi nào không dùng: không dùng spinner toàn màn cho tác vụ ngắn.
- Anatomy: skeleton theo layout thật, optional loading text.
- Variants: `panel-skeleton`, `row-skeleton`, `node-skeleton`.
- States: `initial-load`, `refreshing`.
- Content rules: giảm layout jump, phản ánh cấu trúc nội dung thật.
- Spacing rules: skeleton theo đúng spacing component thật.
- Accessibility notes: tôn trọng reduced motion.
- Lỗi consistency hay gặp: spinner lạm dụng; skeleton không khớp layout.

#### 19) Split panel divider / resizable panel
- Mục đích: điều chỉnh mật độ thông tin giữa overview và detail.
- Khi nào dùng: split-view desktop cần resize.
- Khi nào không dùng: layout nhỏ/cố định không cần drag.
- Anatomy: divider line, drag handle zone, optional collapse toggle.
- Variants: `vertical`, `horizontal`.
- States: `default`, `hover`, `dragging`, `focus`, `collapsed`.
- Content rules: luôn có min/max width.
- Spacing rules: handle hit area rộng hơn line hiển thị.
- Accessibility notes: hỗ trợ keyboard resize.
- Lỗi consistency hay gặp: chỉ hỗ trợ chuột, panel co quá nhỏ gây mất readability.

### C. Component nào nên merge / remove / simplify
1. Merge `SidebarProjectItem` + `SidebarTaskItem` vào base `NavTreeItem` với preset theo level.
2. Merge `ButtonPrimary`, `ButtonSecondary`, `ButtonGhost` thành một `Button` có `variant` + `priority`.
3. Merge status mapping giữa `StatusBadge` và `ProgressWidget` compact.
4. `DocumentViewerBlock` kế thừa typography/spacing của `ContentBlock`; không tạo style system riêng.
5. Giữ `AlertBanner` đúng 4 severity; bỏ custom banner ad-hoc theo màn.
6. Chuẩn hóa `InlineAction` còn 2 kiểu chính: `icon-button` và `text-action`.
7. `LoadingState` chỉ dùng skeleton templates theo panel/list/node; giảm spinner tự do.
8. `PanelContainer` là shell duy nhất cho panel cấp layout; bỏ wrapper card dư.

### D. Top 10 component rules để giữ consistency
1. Mỗi panel chỉ có một primary CTA.
2. Mỗi trạng thái nghiệp vụ chỉ một badge label + một semantic color map.
3. Row heights cố định theo role (`project 36`, `task 32`, `dense 28`).
4. Tab chỉ dùng cho context ngang cấp.
5. Node card luôn giữ anatomy 3 phần: header/body/footer.
6. Inline action de-emphasized mặc định, nhưng vẫn keyboard accessible.
7. Panel shell dùng chung border/radius/padding tokens.
8. Document viewer dùng type scale đọc dài cố định, không override tùy tiện.
9. Split divider bắt buộc min/max width guardrail.
10. Empty/loading/error là state bắt buộc với panel quan trọng.

### E. Những component phải khóa chặt để tránh app bị vỡ style
1. `PanelContainer`
2. `NavTreeItem` (base cho project/task sidebar)
3. `WorkflowNodeCard`
4. `ConnectorLine`
5. `StatusBadge`
6. `Tab`
7. `Button` system
8. `ComposerBar`
9. `DocumentViewerBlock`
10. `SectionHeader`
11. `SplitDivider`

---

## Gợi ý dùng tài liệu này khi review UI
- Dùng **Part 1** để xác định vấn đề hiện tại.
- Dùng **Part 2** để kiểm quyết định ở level principle.
- Dùng **Part 3** để check token-level consistency.
- Dùng **Part 4** để check component-level implementation.
