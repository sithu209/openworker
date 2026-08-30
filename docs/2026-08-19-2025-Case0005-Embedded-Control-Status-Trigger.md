# Case0005 Embedded Control 状态触发与当前阻塞

> 时间：2026-08-19 20:25 +08:00
> Case：0005 白雪公主
> 目标机：DESKTOP-ODAQN0D
> 状态：STATUS QUERY TRIGGERED / WAITING FOR ODA RUNNER RECEIPT

## 本轮实际动作

1. 新增 `.github/workflows/case-0005-embedded-status-oda.yml`。
2. workflow 仅承担 `OPENWORKER_CONTROL` 短命令运输与 durable receipt read-back，不做 Case business execution。
3. 固定命令：`CASE.STATUS`。
4. request_id：`case0005-status-20260819-a1`。
5. 控制入口提交：`7dda15358a1c6641f0cf75ac6c167980b800184d`。
6. 独立触发提交：`4b1cb91942f9851e2bb2412db18bf36e72e98f7a`，commit marker 为 `[case0005-embedded-status]`。

## 为什么本轮没有直接 CASE.CONTINUE_BATCH

`docs/CASE_CONTROL_PATH_AUTHORITY_ZH.md` 当前声明 Case0005 仍存在 durable business work：

`case0005-0005-010-r000014-17b8b780`

在该 work terminal 之前禁止重复 `case_continue`，所以本轮先使用 OpenWorker `CASE.STATUS` 取得真实流程状态。

## 预期 durable 回执

ODA Hook + dispatcher 成功后，workflow 会将结果写回：

`command-results/DESKTOP-ODAQN0D/case0005-status-20260819-a1/final.json`

目前该文件尚未出现，因此当前唯一可确认的阻塞是：

> ODA self-hosted runner 尚未完成本次短命令接单 / Hook receipt read-back。

在 durable receipt 出现前，不得宣称 Case 已推进，也不得用新的 request_id 重复制造 business work。

## 下一动作

回执出现后按结果处理：

- 若 current work 为 `pending/claimed/running`：只观察，不 continue。
- 若 terminal `completed`：由 OpenWorker reconcile，再发唯一 request_id 的 `CASE.CONTINUE_BATCH`。
- 若 terminal `failed`：读取 leaf blocker，流程问题修 OpenWorker，工具问题问 go-tool。
- 若进入 review/approval gate：停在 gate，不绕过用户审批。
