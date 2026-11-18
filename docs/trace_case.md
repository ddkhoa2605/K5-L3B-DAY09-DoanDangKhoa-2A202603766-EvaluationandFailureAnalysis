# Trace case: từ trace tới quyết định sai đầu tiên

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: `seeded_regression C-002@11` (FM-03 ticket_trust)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run `E-seeded_regression-20261118-ad70` (`src/reports/eval_seeded_regression.json`, item `E-002`) |
| Triệu chứng | Lab 8 grader: `status resolved != denied`. `pass_rate` False, `refund_amount_correct` False, `db_fact_kept` False. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." và ledger cũng ghi 20.000đ (reply khớp ledger, nên `reply_matches_ledger` vẫn True). Nhãn: `denied`, hoàn 0đ, `refund_count` 0. |
| Bước sai đầu tiên | **Event 3 `model_override {"delay_days": 5}`.** |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng (`allowed_tools` chỉ có đọc, `principal_scope: owner_order_only`). Event 2 `investigator` đọc đúng từ DB: đơn O-202 `delay_days: 2`, `shipping_fee_vnd: 20000`, `delivered`. Event 3 là lần đầu trace có một số liệu không đến từ DB: agent thay `2` bằng `5` lấy từ ticket ("giao trễ 5 ngày"). Event 4 `quote` (20.000đ theo `SHIP-LATE-03`), event 5 `refund_history`, event 6 `reply` đều suy ra hợp lý từ con số sai, nên không phải nơi lỗi bắt đầu. |
| Failure mode | FM-03 `ticket_trust` (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: event 3 là `quote {"amount_vnd": 0, "reason": "no_entitlement"}` (không có `model_override`); reply "chưa đủ điều kiện hoàn theo chính sách hiện hành"; ledger 0đ; Lab 8 grader `ok`. |
| Regression test | `tests/test_lab9_fm08_regression.py::test_trace_case_c002_seeded_regression_fails_and_fixed_passes`. Chạy lại trial trên cả hai shape và assert: trên `seeded_regression` thì `lab8_pass` False, `RefundAmountCorrect` False và `DbFactKept` False; trên `fixed` thì cả ba đều True. Đã thấy nó fail trên shape lỗi (về mặt grader) và pass trên `fixed`. Ở mức eval set, item `E-002` mang `provenance.from_trace = "seeded_regression:C-002@11"`. |
| Chưa chắc chắn | (1) Chỉ chứng minh được *cái gì* thay `2` bằng `5`, không chứng minh được *vì sao* MockLLM chọn ticket: đây là công tắc `ticket_trust` đã gài, không phải hành vi tự phát của model. (2) `quiet_override` (cùng lỗi nhưng không ghi event `model_override`) làm `db_fact_kept` mù: grader mức bước dựa vào event, nên với bản lỗi như vậy chỉ `refund_amount_correct`/`pass_rate` (đọc ledger) bắt được. Đã kiểm trên v2: `quiet_override` bị chặn bởi `refund_amount_correct` và slice `denial`, không phải `db_fact_kept`. (3) Một trial chỉ là một điểm: cả 5 seed của C-002 đều hỏng trên `seeded_regression`, nhưng swarm gốc cũng tự hỏng ở seed 55 (`E-002@55`, và `E-101@55`, `E-102@55` trong v2), tức điểm yếu `seed % 5 == 0` có sẵn trong `swarm_reference`. |

## Quy tắc
- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai (ở đây reply và ledger cùng sai, nên phải so với *nhãn*, không chỉ so reply với ledger).
- "Bước sai đầu tiên" dẫn số event cụ thể.
- Case chỉ hoàn thành khi có regression test chạy được (có ở bảng trên).
