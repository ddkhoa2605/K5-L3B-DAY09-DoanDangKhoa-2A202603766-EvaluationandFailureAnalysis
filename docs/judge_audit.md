# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (từ `src/`). Judge ở chế độ REPLAY: verdict của judge đã nằm sẵn trong CSV, không gọi model. FAIL là lớp dương (judge phải *tìm* lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok (`judge_tone_public.csv`) | 100 | 0.757 | 0.857 | 0.800 | Đạt cả ba | **Dùng**, có điều kiện (xem Kết luận) |
| helpful (`judge_helpful_public.csv`) | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** κ và recall (P đạt) | **Loại** khỏi gate |

Ma trận nhầm lẫn (người × judge, FAIL dương):

| | tp | fp | fn | tn |
|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 |
| helpful | 9 | 0 | 21 | 70 |

Tỉ lệ lỗi sau hiệu chỉnh Rogan-Gladen (`stats.rogan_gladen`): tone quan sát 0.28 → **0.30** (khớp 30/100 nhãn người); helpful quan sát **0.09** → 0.30. Tức judge helpful báo "chỉ 9% reply lỗi" trong khi người thấy 30%: nó không chỉ yếu mà còn làm lệch con số báo cáo theo hướng đẹp hơn thực tế.

## ≥5 case audit thủ công
Đọc từng reply, đối chiếu nhãn người và ghi chú trong CSV. 10 ca bất đồng của tone_ok đều được xét; bảng dưới đưa đủ cả 10.

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Xưng "em … anh" kèm "nha", không có "Dạ": suồng sã với khách khiếu nại. Rubric thêm: không dùng "em/nha/nhé" thay cho "Dạ … ạ". |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người | Gọi khách là "bạn". Trên 100 dòng, 6/6 reply có "bạn" bị người chấm FAIL (judge bắt 5/6, sót đúng ca này). Rubric thêm: đại từ gọi khách chỉ "anh/chị". |
| 3 | H-029 "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Có "Dạ, vui lòng" nên judge tưởng lịch sự, nhưng "không cần nhắn thêm" là giọng ra lệnh. Rubric thêm: câu yêu cầu/cấm khách làm gì phải mềm hoá ("anh/chị vui lòng chờ, LogiX sẽ phản hồi"). |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Ngắn nhưng đủ số tiền và thời hạn. Judge phạt vì "thiếu xin lỗi": luật này sai khi claim đã được giải quyết. Rubric sửa: xin lỗi chỉ bắt buộc khi từ chối hoặc có sự cố; tuyệt đối không phạt reply ngắn đủ ý. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | "refund" là từ CS LogiX cho phép. Judge phạt vì tiếng Anh. Rubric thêm danh sách thuật ngữ được phép (refund, ticket, order). Lưu ý: 3/4 reply có "refund" bị người chấm FAIL, nhưng cả ba là kiểu "Ok, refund … cho bạn" (lỗi ở "Ok"/"bạn", không phải ở từ "refund"), nên "refund" tự nó không phải tín hiệu lỗi. |
| 6 | H-063 "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây thực chất là lỗi nội dung, gần FM-08, và nên chấm bằng code đối chiếu ledger, không phải judge giọng. Rubric tone chỉ ghi: không hứa hẹn ngoài kết quả. |
| 7 | H-070 "Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Emoji cười trong ngữ cảnh khiếu nại. Rubric thêm: cấm emoji. Đây là luật chấm được bằng regex (code rẻ hơn judge). |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Ghi chú CSV: người đọc nhầm ticket. Sửa nhãn người thành FAIL; không sửa rubric. (Mình không sửa CSV vì test `test_confusion_tone` khoá số 24/4/6/66; đây là đề xuất cho vòng gán nhãn sau.) |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Không rõ, thiên về người | Lặp "Dạ" do lỗi gõ; không xúc phạm khách. Rubric thêm: lỗi chính tả/lặp từ nhỏ không phải lỗi giọng. Nhưng chỉ 1 mẫu nên chưa kết luận chắc. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien." | PASS | FAIL | Người | Mất dấu tiếng Việt (dịch máy). Rubric thêm: tiếng Việt phải có dấu. Có thể chấm bằng code (tỉ lệ ký tự có dấu). |

Thống kê từ 10 ca: 4/6 false negative của judge (bạn, em/nha, emoji, mất dấu) bắt được bằng quy tắc regex đơn giản, 2/6 (giọng ra lệnh, hứa thêm) cần đọc nghĩa hoặc đối chiếu ledger; 3/4 false positive do **luật rubric sai** (bắt buộc xin lỗi, cấm tiếng Anh, lặp "Dạ"), 1 do **nhãn người sai** (H-081).

## Vì sao `helpful` bị loại
- Recall 0.30 (bắt 9/30 reply người cho là lỗi), κ 0.375 < 0.6. Dù P=1.0, một judge chỉ đúng khi nó lên tiếng thì vẫn bỏ sót 70% lỗi: dùng làm gate sẽ cho mọi regression lọt qua.
- 21/21 false negative là cùng một dạng: **reply nêu số tiền khác ledger** (ghi chú dạng "ledger ghi 40.000đ" trong CSV: HL-015, HL-020, HL-087 …) hoặc không có nội dung cụ thể (HL-047, HL-091, HL-097 "Ok bạn, đơn … xử lý rồi nhé"). Đây là FM-08 (misreport). Judge thấy câu dài, lịch sự, có xin lỗi và chấm PASS: nó đang thưởng cho văn phong, không kiểm số tiền (thiên lệch độ dài/lịch sự). Đo trên CSV: 18/21 false negative có ghi chú "ledger ghi …" (số sai), 13/21 chứa đoạn xin lỗi lặp lại (≥2 lần), 3/21 là reply cộc "Ok bạn, đơn … xử lý rồi nhé" không nêu số tiền; trong khi 0/70 reply người chấm PASS có chữ "xin lỗi". Đoạn xin lỗi đệm dài là thứ đánh lừa judge.
- Hệ quả thiết kế: số tiền là thứ **code** kiểm được chính xác. Vì vậy FM-08 được chấm bằng `ReplyMatchesLedger` (`lab9/graders.py`, metric `reply_matches_ledger`), không bằng judge. Trên 70 trial của shape `misreport`, grader Lab 8 bỏ sót 10/10 và grader code bắt 10/10.

## Kết luận
- **Tiêu chí bị loại:** `helpful`. Lý do: ma trận `tp=9, fp=0, fn=21, tn=70` cho recall 0.30 và κ 0.375, đều dưới sàn; tỉ lệ lỗi quan sát 0.09 sai lệch xa thực tế 0.30.
- **Tiêu chí dùng được:** `tone_ok` (κ 0.757, P 0.857, R 0.800), nhưng chỉ để **theo dõi**, không dùng làm gate chặn (hiện không có metric nào trong `metric_spec` dựa trên judge). Nếu đưa vào gate, phải báo kèm tỉ lệ đã hiệu chỉnh Rogan-Gladen.
- **Sửa rubric sau audit (đưa vào vòng chấm tới):** (1) chỉ "anh/chị", cấm "bạn/em/nha/nhé"; (2) cấm emoji; (3) tiếng Việt có dấu; (4) xin lỗi bắt buộc khi từ chối hoặc có sự cố, không phạt reply ngắn đủ ý; (5) thuật ngữ được phép: refund, ticket, order; (6) lặp từ gõ nhầm không phải lỗi giọng. Quy tắc (1)–(3) chấm được bằng regex (đã kiểm: "bạn" có mặt ở 6/6 reply người chấm FAIL, 0 reply PASS) nên nên chuyển sang code; phần judge chỉ giữ nhận xét giọng điệu thực sự mơ hồ (ví dụ H-029).
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai, một người gán nhãn (không có κ giữa người với người), và ít nhất 1 trong 100 nhãn người sai (H-081), nên trần κ thực tế thấp hơn 0.757 đo được. Cần nhãn người mới, độc lập để có held-out thật trước khi tin con số này.
