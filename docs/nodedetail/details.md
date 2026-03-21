Task Framing & Progressive Spec Workflow
High-level design doc for user–agent project shaping
1. Mục tiêu của hệ thống
Hệ thống này được thiết kế để giúp user và agent cùng làm rõ một task theo cách:
giữ đúng ý định của user


giảm context drift


không bắt user phải nói hết mọi chi tiết từ đầu


làm task cụ thể dần qua nhiều tầng


chỉ ưu tiên làm rõ những unknown thật sự ảnh hưởng tới steering ở tầng hiện tại


giữ lại phần chưa rõ nhưng chưa quan trọng để xử lý ở subtasks hoặc ở giai đoạn sau


Mục tiêu của hệ thống không phải là làm rõ mọi thứ ngay từ đầu.
 Mục tiêu là:
làm cho task đủ cụ thể để có thể tiến triển


giữ được intent gốc của user


giảm số lượng câu hỏi agent cần hỏi


tập trung vào các thông tin ít nhưng quan trọng để định hình đúng hướng của project


ưu tiên boundary, risk, success criteria và steering decisions hơn là completeness


Hệ thống này không tối ưu cho maximum clarity upfront.
 Nó tối ưu cho:
progressive clarification


intent preservation


controlled specificity


user-guided depth


minimum necessary clarification



2. Triết lý cốt lõi
2.1. Steering quan trọng hơn completeness
Không cần thu toàn bộ requirement ở vòng đầu. Chỉ cần làm rõ những gì ảnh hưởng tới:
hướng đi của task


phạm vi của vòng hiện tại


tiêu chí thành công


boundary của vòng hiện tại


mức độ cụ thể cần đạt ở tầng hiện tại


2.2. Task là node công việc, không phải mô tả đầy đủ bài toán
Trong hệ thống này, task là một đơn vị công việc hoặc một node trong cây công việc.
Ví dụ:
chair website


Core Site Entry


Study Planner MVP


Task ở đây chỉ là:
một việc phải làm


một node để tổ chức decomposition


một nhãn ngắn gọn để người dùng và hệ thống tham chiếu


Task không đồng nghĩa với:
problem statement


user story


internal state


working goal của agent


Điều này giúp:
khớp với UI tree / node


giữ mental model đơn giản cho user


tránh overload khái niệm “task”


2.3. Task title và User story / Problem là hai lớp nghĩa khác nhau
Một task nên được mô tả ở hai lớp:
Task title: tên ngắn gọn của việc phải làm


User story / Problem: bài toán hoặc nhu cầu mà task này tồn tại để giải quyết


Ví dụ:
Task title: Core Site Entry


User story / Problem: Người truy cập lần đầu cần một điểm vào rõ ràng để hiểu website nói về gì và nên đi đâu tiếp theo


Tách hai lớp này giúp:
giữ task title ngắn, dễ đặt trong tree


giữ frame đủ rõ về intent


tránh việc chỉ nhìn title rồi agent tự điền nghĩa


2.4. Frame là human-friendly, spec là agent-friendly
User nên tương tác với một artifact dễ hiểu, gần với ngôn ngữ business/product.
Agent sẽ dùng một version mở rộng hơn để giữ:
normalized requirements


assumptions/defaults


deferred / unresolved points


risk và boundaries


2.5. Frame là version đầu của spec
Frame không phải artifact hoàn toàn khác với spec.
 Frame là thin spec.
Spec là version mở rộng hơn từ frame để agent tiếp tục làm việc.
2.6. Trong bản demo, frame là artifact nguồn
Ở mức demo, để giữ hệ thống đơn giản và tránh drift:
frame là artifact nguồn


working spec luôn được build từ frame hiện tại


spec không được chỉnh độc lập ngoài frame


Điều này giúp:
giảm độ phức tạp triển khai


giữ user-facing artifact làm tâm điểm


tránh việc frame và spec sync lệch nhau


2.7. Task không cần rõ hết mới tiến lên được
Task có thể bắt đầu từ mức rất thô.
 Hệ thống sẽ dùng task-shaping fields để làm task cụ thể hơn theo từng bước.
2.8. Không phải mọi unknown đều cần xử lý giống nhau
Một điểm chưa rõ không mặc định phải hỏi user ngay.
Mỗi unknown nên được xử lý theo một trong ba hướng:
Ask now: hỏi user ngay nếu nó ảnh hưởng steering hoặc boundary hiện tại


Assume for now: dùng default tạm thời nếu có thể đoán an toàn và dễ sửa về sau


Defer: để lại cho subtasks hoặc giai đoạn sau nếu chưa ảnh hưởng tầng hiện tại


Đây là rule nền để hệ thống không:
hỏi quá nhiều


assume quá tay


hoặc giữ mọi thứ ở trạng thái mơ hồ vô tổ chức


2.9. Không phải mọi unknown đều cần được promote thành shaping field
Chỉ những unknown có steering value rõ ở tầng hiện tại mới nên được promote thành task-shaping fields.
Các unknown khác nên:
được assume tạm thời nếu an toàn


hoặc được defer về sau


2.10. User quyết định độ sâu của task
User không cần phải trả lời hết mọi field.
 User có thể chọn:
chỉ muốn task ở mức generic


muốn refine sâu hơn


muốn đẩy phần chưa rõ xuống subtasks sau


2.11. Bản demo không cần orchestration phức tạp
Trong bản demo, agent không cần nêu rõ hoặc điều phối mạnh các bước như:
execute


split


refine further


Agent chỉ cần:
draft frame


clarify bằng task-shaping fields


update frame ở hậu trường


build spec ở hậu trường


Quyết định đi tiếp như thế nào là việc của user.

3. Kiến trúc tổng thể
Trong bản demo, hệ thống có 3 khái niệm chính:
Task
Task là node công việc hoặc nhiệm vụ phải làm.
 Task được nhận diện chủ yếu qua task title.
Frame
Frame là bản đầu tiên, human-friendly, được dùng để align với user.
Working Spec
Working spec là version mở rộng của frame, dùng cho agent.
Quan hệ giữa chúng
task là đơn vị công việc đang được xử lý


task title là nhãn ngắn gọn của task


frame là artifact chính user nhìn thấy và chỉnh sửa


spec là artifact nội bộ cho agent


trong bản demo, frame là nguồn để build spec


spec không phải nguồn sự thật độc lập



4. Các khái niệm chính
4.1. Task
Task là một việc phải làm, tương ứng với một node trong hệ thống.
Vai trò của task
là đơn vị để user nhìn thấy công việc


là đơn vị để tree decomposition tổ chức công việc


là container logic để agent draft frame và build spec cho node đó


Thành phần nhận diện tối thiểu
Ở mức user-facing, task có thể được nhận diện trước hết bằng:
task id hoặc node position


task title


Task title chỉ là tên ngắn gọn của công việc.
 Nó không mang toàn bộ meaning của frame hoặc spec.
Ví dụ:
task title: chair website


task title: Core Site Entry


task title: End-to-End Review



4.2. Frame
Frame là thin spec ở dạng human-friendly.
 Frame là artifact chính mà user sẽ đọc, sửa hoặc confirm.
Frame không cần technical-heavy, nhưng phải đủ rõ để làm việc tiếp.
Vai trò của frame
phản ánh cách agent đang hiểu task


làm cho task cụ thể hơn nhưng vẫn dễ đọc


tạo nền cho quá trình clarify


làm base để tạo spec


là artifact nguồn trong bản demo


Format frame đề xuất
Task title


User story / Problem


Functional requirements


Success criteria


Out of scope


Task-shaping fields


Giải thích từng field trong frame
Task title
Tên ngắn gọn của node công việc.
Field này giúp:
nhận diện task trong tree


giữ artifact dễ quét


giữ decomposition action-oriented


Task title không cần chứa toàn bộ problem statement.
User story / Problem
Mô tả bài toán đang được giải.
Nếu task phù hợp với product language thì có thể dùng user story.
 Nếu task không phải product feature thì có thể dùng problem statement.
Field này trả lời:
ai đang cần gì


hoặc bài toán chính là gì


hoặc task này tồn tại để giải quyết chuyện gì


Field này giúp:
khóa intent của task


giảm nguy cơ agent tự suy diễn từ title


giữ frame human-friendly hơn chỉ dùng task title


Functional requirements
Những gì task hoặc version hiện tại phải làm được.
Đây là field rất quan trọng vì:
user hiểu được


PM hiểu được


junior dev hiểu được


agent cũng dùng được


Ở frame, FR có thể còn rộng.
Success criteria
Điều kiện để coi vòng hiện tại là đủ tốt.
Field này giúp:
tránh làm quá nhiều


tránh kết thúc quá sớm


định nghĩa rõ “đạt chưa”


Out of scope
Những gì chủ động không làm trong vòng hiện tại.
Field này giúp:
chặn scope creep


giữ cho task gọn


định nghĩa boundary bằng ngôn ngữ dễ hiểu


Task-shaping fields
Các field dùng để làm task cụ thể hơn.
Đây là cơ chế chính để workflow make progress.
 Task-shaping fields thay vai trò của open questions ở lớp user-facing.
Chúng là:
các chiều thông tin mà khi được làm rõ, task sẽ tiến triển rõ rệt


các quyết định có giá trị steering ở tầng hiện tại


các điểm giúp giảm đoán mò của agent


Ví dụ:
landing page: tone, audience, CTA


MVP app: platform, storage level, auth scope


research task: time horizon, source quality, depth



4.3. Working Spec
Working spec là version mở rộng của frame cho agent.
Spec không cần là design doc chi tiết.
 Nó chỉ cần đủ rõ để agent không đi sai hướng và có thể giữ context qua refine hoặc split sau này.
Vai trò của spec
normalize lại task ở ngôn ngữ agent dễ reason hơn


lưu những assumptions và defaults đang được dùng


lưu task-shaping fields ở trạng thái hiện tại


tách phần deferred ra khỏi phần cần làm rõ ngay


giữ risk và boundaries để agent không drift


làm nền cho split tiếp hoặc execute sau này


Format working spec đề xuất
Working Goal


Source frame


Functional requirements


Success criteria


Out of scope


Assumptions & Defaults


Task-shaping fields


Deferred / Unresolved points


Key risks / Boundaries


Clarification notes


Giải thích từng field trong spec
Working Goal
Phiên bản chuẩn hóa, action-oriented của task ở ngôn ngữ agent.
Field này không phải là task title được viết lại nguyên xi.
 Nó là phát biểu rõ hơn về:
agent đang cố đạt điều gì


trong phạm vi nào


để phục vụ outcome nào


Dùng tên Working Goal để tránh nhầm với:
task title của node


user story / problem trong frame


Source frame
Tham chiếu ngắn gọn về frame hiện tại mà spec được build từ đó.
Functional requirements
FR đã được agent normalize thêm nếu cần.
Success criteria
Tiêu chí thành công của vòng hiện tại.
Out of scope
Giữ phạm vi loại trừ để agent không overbuild.
Assumptions & Defaults
Những điều agent tạm coi là đúng để tiếp tục công việc khi user chưa specify hết.
Field này quan trọng vì:
tránh việc agent đoán ngầm


giúp spec usable dù chưa hoàn chỉnh


cho phép task vẫn tiến lên mà không bắt user trả lời tất cả


Task-shaping fields
Các field hiện đang được dùng để làm task cụ thể hơn.
Spec sẽ ghi lại:
field nào đã có giá trị


field nào đang tạm defaulted


field nào còn có thể clarify nếu user muốn đi sâu hơn


Deferred / Unresolved points
Những điểm còn chưa rõ nhưng không cần giải quyết ngay ở tầng hiện tại.
Chúng tồn tại để:
giữ lại những gì chưa tới lúc xử lý


chuyển xuống subtasks


hoặc giữ generic nếu user muốn


Key risks / Boundaries
Các risk và boundary mà agent cần nhớ để không drift.
Clarification notes
Ghi chú ngắn về những gì đã được clarify ở vòng hiện tại.

4.4. Task-Shaping Fields
Task-shaping fields là cơ chế chính để làm task cụ thể hơn.
 Đây không chỉ là nơi chứa câu hỏi.
 Đây là cách workflow make progress.
Vai trò
làm task từ mơ hồ sang usable hơn


tạo thêm specificity theo từng vòng


giúp frame và spec trưởng thành dần


hỗ trợ split ở các tầng sau


Tính chất
Task-shaping fields có thể xuất hiện rất sớm.
 Khi task còn thô, chúng cũng sẽ ở mức thô.
 Khi task đã cụ thể hơn, chúng cũng trở nên cụ thể hơn.
Ví dụ:
Task còn thô
platform


audience


tone


storage level


user scope


Task cụ thể hơn
mobile web vs desktop web


single-user vs multi-user


prototype persistence vs durable persistence


formal vs friendly tone


internal CTA vs public CTA


Quy tắc tạo task-shaping fields
Một thông tin chỉ nên trở thành task-shaping field nếu nó làm ít nhất một trong các việc sau:
làm task cụ thể hơn theo cách hữu ích


giúp task tiến gần hơn tới một spec usable


làm rõ steering ở tầng hiện tại


giảm đáng kể mức agent phải đoán


giúp split sau này sạch hơn


Nếu một unknown chưa có vai trò như trên, nó không nên được promote thành task-shaping field.
Format tối thiểu cho một task-shaping field
Field name


Why it matters


Current value (if any)


Có thể mở rộng thêm về sau với:
source


resolved / unresolved


user-provided / assumed / deferred


Nhưng chưa cần cho bản high-level hiện tại.

4.5. Unknown Handling Rule
Đây là rule nền để agent xử lý các điểm chưa rõ một cách có kiểm soát.
Mỗi unknown nên được phân loại theo một trong ba hướng:
Ask now
Hỏi user ngay nếu unknown đó:
ảnh hưởng rõ tới steering ở tầng hiện tại


làm thay đổi boundary hoặc scope hiện tại


làm thay đổi success criteria


hoặc là quyết định khó sửa nếu đoán sai


Assume for now
Dùng default tạm thời nếu:
có một default hợp lý


default đó không làm lệch intent cốt lõi


dễ sửa ở tầng sau


chưa đủ quan trọng để hỏi ngay


Defer
Để lại cho subtasks hoặc giai đoạn sau nếu:
chưa ảnh hưởng tầng hiện tại


chưa cần để định hướng vòng hiện tại


có thể giải sau mà không làm hỏng task hiện tại


Ý nghĩa
Rule này giúp workflow:
không hỏi quá nhiều


không ép user vào implementation sớm


không để mọi điểm chưa rõ trôi nổi vô tổ chức


tập trung vào minimum necessary clarification



4.6. Assumptions & Defaults
Đây là các giả định mà agent dùng để tiếp tục công việc khi user chưa specify hết.
Mục đích
tránh việc agent đoán ngầm


giúp spec usable dù chưa hoàn chỉnh


cho phép task vẫn tiến lên mà không bắt user trả lời tất cả


Ví dụ
assumed single-user unless stated otherwise


assumed generic styling if no preference is given


assumed internal-use scope unless public audience is specified


Nguyên tắc
Assumptions nên:
vừa đủ


không vượt scope


không thay đổi intent cốt lõi


dễ sửa ở các tầng sau nếu cần



4.7. Deferred / Unresolved Points
Đây là phần còn chưa rõ của task nhưng chưa cần xử lý ngay.
Vai trò
giữ lại phần chưa cần xử lý ngay


tránh làm task-shaping fields phình quá mức


cho phép user giữ task ở mức generic nếu muốn


làm vùng đệm cho subtasks và split sau này


Phân biệt với assumptions
Deferred / unresolved points không giống assumptions.
Assumption là thứ agent đang tạm dùng để tiếp tục


Deferred point là thứ agent biết là còn mở nhưng chưa cần xử lý ngay


Điểm này rất quan trọng vì hai loại này có vai trò vận hành khác nhau.

4.8. Success Criteria
Success criteria là định nghĩa “đủ tốt” của vòng hiện tại.
Vai trò
giúp user và agent có cùng điểm kết thúc


tránh overbuild


tránh mơ hồ về completion


Ví dụ
đủ dùng cho internal review


đủ để có thể split tiếp


đủ để triển khai core flow vòng đầu



4.9. Out of Scope
Out of scope là các phần không làm trong vòng hiện tại.
Vai trò
giữ boundary rõ


giúp task gọn


hỗ trợ decomposition


chặn scope creep


Ví dụ
no collaboration


no production deployment


no advanced analytics


no native mobile app



5. Workflow tổng thể
Phase 1 — User Input
User đưa task hoặc goal ở dạng tự do.
 User không cần biết format.
 Agent là bên chuyển đổi đầu vào này thành frame.
Phase 2 — Draft Frame
Agent tạo frame đầu tiên ở dạng human-friendly.
Frame này có thể đã chứa task-shaping fields ở mức thô.
 Không cần đợi task thật rõ rồi mới sinh task-shaping fields.
Mục tiêu
phản ánh cách hiểu ban đầu


bắt đầu làm task cụ thể hơn


giữ task ở ngôn ngữ user vẫn đọc được


Kết quả mong đợi
Frame đầu tiên nên làm rõ được ít nhất:
task title là gì


task đang giải bài toán gì


version hiện tại cần làm được gì


chưa làm gì


những shaping fields nào đáng hỏi tiếp


Phase 3 — Clarify Through Task-Shaping Fields
Agent dùng task-shaping fields để hỏi user những điểm quan trọng nhất ở tầng hiện tại.
Đây là bước lõi của workflow.
Mục tiêu
làm task cụ thể hơn


giảm unknown ảnh hưởng tới steering


giúp user make progress mà không cần đi hết vào implementation


Nguyên tắc
ưu tiên shaping fields ảnh hưởng tới steering


user không cần trả lời tất cả


field nào chưa cần thì để lại ở deferred / unresolved points


không phải mọi unknown đều được hỏi ở vòng này


mỗi unknown nên được xử lý theo ask / assume / defer


Ý nghĩa
Task-shaping fields không đi thẳng vào spec.
 Chúng phải đi qua một vòng clarify với user trước.
Phase 4 — Update Frame (Behind the Scene)
Sau khi user trả lời, agent cập nhật frame.
Đây là bước nội bộ.
 Frame mới là version trưởng thành hơn của frame cũ:
user story / problem có thể rõ hơn


FR có thể rõ hơn


success criteria có thể cụ thể hơn


out of scope có thể rõ hơn


task-shaping fields có thể có giá trị cụ thể hơn


User không nhất thiết phải thấy bước này như một thao tác riêng.
Phase 5 — Build Working Spec (Behind the Scene)
Từ frame đã được cập nhật, agent tạo working spec.
Đây cũng là bước nội bộ.
Spec sẽ:
kế thừa nội dung của frame mới


chuyển problem statement thành working goal rõ hơn cho agent


thêm assumptions/defaults nếu cần


giữ lại deferred / unresolved points


thêm risk/boundary phục vụ agent


Nguyên tắc quan trọng
Working spec luôn được tổng hợp từ updated frame, không phải từ frame draft ban đầu.
 Trong bản demo, spec không được chỉnh độc lập ngoài frame.
Phase 6 — Progressive Refinement in Lower Layers
Nếu task được split sau này, subtasks sẽ tiếp tục quá trình tương tự:
draft frame


clarify shaping fields


update frame


build spec


Đây là cách specificity tăng dần qua nhiều tầng.

6. Mối quan hệ giữa task, frame, task-shaping fields, deferred points và spec
6.1. Task là node công việc
Task là việc phải làm hoặc node trong tree.
 Task title chỉ là nhãn nhận diện của node.
6.2. Task title không đủ thay cho problem statement
Task title giúp nhận diện công việc.
 User story / Problem giúp giải thích tại sao task tồn tại và đang giải quyết chuyện gì.
6.3. Frame là thin spec
Frame là phiên bản đầu tiên của spec, được viết theo ngôn ngữ con người.
6.4. Frame nên chứa cả task title và user story / problem
Điều này giúp:
giữ decomposition sạch


giữ intent rõ


tránh hiểu sai từ title ngắn gọn


6.5. Task-shaping fields nằm trong frame
Task-shaping fields không phải bước tách biệt ở phía sau.
 Chúng là một phần của frame ngay từ sớm.
6.6. Task-shaping fields làm task cụ thể hơn
Frame không chỉ mô tả task.
 Frame còn chứa cơ chế để refine task.
6.7. Clarification đi qua task-shaping fields
Agent dùng task-shaping fields để hỏi user.
 Đây là cơ chế make progress chính.
6.8. Unknown không được xử lý theo một cách duy nhất
Một unknown có thể:
được hỏi ngay


được assume tạm


hoặc được defer


6.9. Assumptions và deferred points là hai vùng khác nhau
Assumptions là các quyết định tạm thời agent đang dùng.
 Deferred / unresolved points là các điểm còn mở nhưng chưa cần xử lý ngay.
6.10. Spec là bản đóng gói có cấu trúc hơn cho agent
Spec mở rộng từ updated frame và giữ lại:
problem statement đã được chuyển thành working goal


kết quả clarify hiện tại


assumptions/defaults


deferred points còn lại


boundary/risk



7. Tại sao mô hình này phù hợp
7.1. Phù hợp với user non-tech
User không phải trả lời câu hỏi implementation quá sớm.
 User chỉ cần nhìn frame và bổ sung các shaping fields quan trọng.
7.2. Phù hợp với user có technical background
Nếu user muốn đi sâu, họ có thể refine shaping fields sớm hơn và cụ thể hơn.
7.3. Phù hợp với PM và junior dev
Các field trong frame đều dễ đọc:
task title


user story / problem


functional requirements


success criteria


out of scope


task-shaping fields


7.4. Phù hợp với agent
Spec đủ cấu trúc để agent:
giữ intent


nhớ assumptions


phân biệt clarified vs deferred


reason theo working goal thay vì chỉ dựa vào title


truyền context xuống các tầng sau


7.5. Hỗ trợ kiểm soát độ chi tiết
User có thể chọn mức refine của task:
generic hơn


cụ thể hơn


hoặc defer phần chưa rõ xuống subtasks


7.6. Hạn chế context drift
Bằng cách chỉ hỏi các unknown có giá trị steering cao, ghi rõ assumptions/defaults, và tách task title khỏi problem statement, agent ít bị drift hơn trong quá trình tiếp tục làm việc.

8. Những gì hệ thống chủ động không làm
Không cố làm rõ hết mọi unknown ngay từ đầu
 Vì điều đó gây friction và không cần thiết.


Không biến mọi unknown thành task-shaping field
 Vì điều đó làm workflow phình và mất trọng tâm.


Không để ambiguity ôm luôn assumptions
 Vì assumption và deferred point có vai trò khác nhau.


Không dùng task title như thể nó đã đủ giải thích bài toán
 Vì title ngắn gọn không thay thế cho user story / problem.


Không bắt user phải chọn hết các shaping fields
 Vì user có quyền giữ task ở mức generic.


Không biến spec thành design doc chi tiết
 Vì spec chỉ cần đủ cho steering và progressive refinement.


Không để spec trở thành nguồn sự thật độc lập trong bản demo
 Vì điều đó làm tăng nguy cơ drift với frame.


Không để agent quyết định split hay execute trong bản demo
 Ở bản demo, agent không đóng vai trò điều phối bước tiếp theo.



9. Guiding rules cho agent
Rule 1
Luôn bắt đầu từ frame human-friendly.
Rule 2
Trong frame, tách rõ task title và user story / problem.
Rule 3
Không dùng task title một mình để suy ra full intent của task.
Rule 4
Cho phép task-shaping fields xuất hiện rất sớm.
Rule 5
Task-shaping fields phải được ưu tiên theo steering value ở tầng hiện tại.
Rule 6
Task-shaping fields phải đi qua một vòng clarify với user trước khi được đóng gói vào spec.
Rule 7
Mỗi unknown phải được xử lý theo một trong ba hướng:
ask now


assume for now


defer


Rule 8
Không promote mọi unknown thành shaping field.
Rule 9
Nếu user không muốn đi sâu, giữ phần chưa rõ trong deferred / unresolved points.
Rule 10
Assumptions phải được ghi rõ, không để agent đoán ngầm.
Rule 11
Working spec luôn được build từ updated frame, không phải từ frame draft ban đầu.
Rule 12
Trong bản demo, spec không được chỉnh độc lập ngoài frame.
Rule 13
Dùng Working Goal trong spec để chuẩn hóa mục tiêu cho agent, thay vì lặp lại task title.
Rule 14
Độ cụ thể của task nên tăng dần qua nhiều tầng, không cần ép đủ ngay ở tầng đầu.

10. Ví dụ minh họa
User Input
Tôi muốn làm một web app quản lý học tập cho sinh viên.
Draft Frame
Task title
Study Planner MVP
User story / Problem
Sinh viên cần một công cụ đơn giản để theo dõi môn học và deadline hàng tuần mà không phải dùng một hệ thống quá nặng hoặc quá nhiều bước.
Functional requirements
tạo môn học


tạo deadline bài tập


xem deadline sắp tới trong tuần


nhận nhắc nhở


Success criteria
có thể dùng để quản lý tuần học đầu tiên


thao tác tạo môn học và deadline đủ nhanh, dễ dùng


Out of scope
không có collaboration


không có mobile app native


Task-shaping fields
target platform


reminder channel


user scope


storage level


Ở bước này, task-shaping fields còn thô, nhưng đã giúp task bắt đầu specific hơn.
Clarify Through Task-Shaping Fields
Agent hỏi user, ví dụ:
target platform: chỉ cần desktop web hay cần mobile-responsive?


reminder channel: browser notification, email, hay chỉ hiển thị trong app?


user scope: chỉ cho một sinh viên cá nhân hay có nhiều tài khoản?


storage level: chỉ cần prototype tạm thời hay cần lưu bền vững?


Ví dụ user trả lời:
mobile-responsive web


browser notification


single-user


persistent storage


Updated Frame (Behind the Scene)
Task title
Study Planner MVP
User story / Problem
Sinh viên cần một web app mobile-responsive để theo dõi môn học và deadline hàng tuần theo cách đơn giản, nhanh và đủ nhẹ cho việc sử dụng thường xuyên.
Functional requirements
tạo môn học


tạo deadline bài tập


xem các deadline trong tuần


nhận browser notification cho deadline


Success criteria
có thể dùng để quản lý tuần học đầu tiên


thao tác tạo môn học và deadline đủ nhanh, dễ dùng


usable trên web mobile-responsive


Out of scope
không có collaboration


không có mobile app native


Task-shaping fields
target platform: mobile-responsive web


reminder channel: browser notification


user scope: single-user


storage level: persistent


Working Spec (Built Behind the Scene)
Working Goal
Build a single-user study planner MVP for mobile-responsive web that helps a student manage subjects and weekly deadlines with low setup friction.
Source frame
Study Planner MVP frame focused on lightweight weekly planning.
Functional requirements
allow creating and editing subjects


allow creating deadlines tied to subjects


show a weekly view of upcoming deadlines


provide browser notifications for reminders


support persistent data storage


Success criteria
usable for first-week planning


core planning flow is simple and quick


works well on mobile-responsive web


Out of scope
collaboration


native mobile app


advanced calendar features


Assumptions & Defaults
auth model remains unspecified at this stage


weekly planning remains the main scope


Task-shaping fields
target platform: mobile-responsive web


reminder channel: browser notification


user scope: single-user


storage level: persistent


Deferred / Unresolved points
authentication model


recurring task support


advanced planning views


Key risks / Boundaries
reminder feature may expand scope quickly


weekly planner may drift into full calendar product


Clarification notes
steering-level shaping fields have been clarified


remaining open points are deferred to later refinement or subtasks



11. Sườn phát triển sản phẩm / hệ thống
Stage 1 — Chốt artifact model
Chốt rõ:
task là gì


task title là gì


frame là gì


spec là gì


working goal là gì


task-shaping fields là gì


assumptions/defaults là gì


deferred / unresolved points là gì


Đây là lớp khái niệm quan trọng nhất.
Stage 2 — Chốt field schema
Chốt format tối thiểu cho:
frame


spec


task-shaping fields


assumptions/defaults


deferred / unresolved points


Không cần harden validation ngay, nhưng phải rõ model.
Stage 3 — Chốt workflow cơ bản
Chốt chuỗi:
user input


frame draft


shaping clarification


frame update


spec compile


Đây là flow lõi của bản demo.
Stage 4 — Chốt unknown handling rule
Định nghĩa rõ:
khi nào ask


khi nào assume


khi nào defer


Đây là phần rất quan trọng để workflow không bị loãng hoặc hỏi quá nhiều.
Stage 5 — Chốt logic shaping vs deferred
Định nghĩa rõ:
cái gì được promote thành shaping field


cái gì nên để lại ở deferred / unresolved points


cái gì nên được ghi thành assumption/default


Đây là phần rất quan trọng để workflow có trọng tâm.
Stage 6 — Chốt progressive depth model
Xác định cách hệ thống cho phép:
task generic


task medium-specific


task highly refined


Tức là chốt cách user điều khiển độ chi tiết.
Stage 7 — Harden later
Các phần để sau:
confidence scoring


richer source/provenance


inheritance rules


readiness logic sâu hơn


execution governance


split contracts chi tiết




12. Kết luận
Kiến trúc của workflow này có thể tóm gọn như sau:
user bắt đầu bằng một task còn thô


task là một node công việc, không phải problem statement hay internal state


mỗi frame tách rõ task title và user story / problem


agent tạo một frame mỏng, dễ hiểu


frame chứa các task-shaping fields để bắt đầu làm task cụ thể hơn


agent dùng các task-shaping fields để clarify với user


mỗi unknown được xử lý theo ask / assume / defer


agent cập nhật frame ở hậu trường


agent tổng hợp working spec từ frame đã cập nhật


working spec dùng working goal để chuẩn hóa mục tiêu cho agent


phần assumptions/defaults được ghi rõ


phần deferred / unresolved points chưa cần xử lý sẽ được giữ lại


nếu đi tiếp qua nhiều tầng, specificity sẽ tăng dần ở các subtasks


Điểm mạnh lớn nhất của kiến trúc này là:
không ép user phải rõ hết ngay từ đầu


không ép agent phải đoán mọi thứ ngầm


không biến mọi unknown thành blocker


giữ decomposition sạch nhờ task title ngắn gọn


giữ intent rõ nhờ user story / problem


dùng task-shaping fields như cơ chế make progress có cấu trúc


dùng ask / assume / defer để giữ clarification hiệu quả


tách assumptions khỏi deferred points để reasoning rõ hơn


dùng working goal trong spec để tránh nhầm với task title


cho phép user điều khiển độ sâu của task một cách tự nhiên


Câu chốt của toàn bộ hệ thống là:
Task là đơn vị công việc trong cây. Task title dùng để nhận diện node. User story / Problem dùng để giải thích bài toán mà task tồn tại để giải quyết. Frame là thin spec để người và agent cùng bắt đầu hiểu task. Task-shaping fields là công cụ để làm task cụ thể hơn ở tầng hiện tại. Agent dùng chúng để clarify với user, xử lý unknown bằng ask / assume / defer, rồi cập nhật frame ở hậu trường. Working spec là bản đóng gói mở rộng được tạo từ frame đã cập nhật, dùng working goal để giữ hướng cho agent và tiếp tục phát triển qua nhiều tầng.
This structure will map to frame -> clarify -> spec in node detail
