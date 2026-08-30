# Case 0004 — 新版 OpenWorker 一鍵清隊列與 Go Tool 先問後做

日期：2026-08-18
固定 workspace：`D:\AI-Work\jobs\0004-DWG-TO-3D`
固定 host：`DESKTOP-O87PJNR`

## 背景

Case 0004 已把 durable Worklist 切到 revision 141，canonical next step 為 `0004-045`，狀態 READY。後續不得回到舊的固定切圖主線；正確路徑是 overview → LLM 樓層 viewport 定位 → Story Index → 每層 zoom PNG → multimodal review。

目前 Action/圖片 handoff 受舊 queued / waiting / in_progress 工作影響，因此改用最新版 OpenWorker one-call queue drain。清隊列屬即時運維，不得成為 Case Worklist business step。

## Go Tool 先問後做規則

工具選擇不得由案例 workflow 猜 capability。固定機器應先呼叫本機 go-tool：`POST http://127.0.0.1:8848/agent/query`。

必要欄位：`project / workspace_root / question`。go-tool 是 capability information authority；只允許回已註冊 capability，不足時必須說明下一步查詢，不得猜 execution result。

Case 0004 已新增 O87 go-tool query workflow：`.github/workflows/case-0004-o87-ask-go-tool.yml`，commit `e539353017ccd2bbf258a0640b1b9d67b4655033`。

目標回答：Story Index queue 應使用哪個 registered queue-admin capability，以及 queue clean 後 `0004-045` 應使用哪個 registered business capability。

截至本文件建立時，`review-tmp/case0004/latest-go-tool-query.json` 尚未回寫，因此不得宣告 go-tool query 已完成。

## Story Index queue-admin scope 缺口

新版 OpenWorker `queue_drain` 只接受 registered queue-admin capability id。Story Index 原本只有 business capability `dwg.story_index.execute.case-worklist`，因此補上 queue-admin scope `dwg.story_index.queue.admin`。

repo：`go-tool-runtime`；commit：`091a2855ad0a1cf27ba0a7709ccb9054713a7ab1`。

此 capability 只授權 queue query/cancel/verify，不執行 Story Index business work。

## 通用 OpenWorker 遠端 one-call drain operator

因目前 ChatGPT 連線面沒有直接在 O87 執行本機 console command 的 transport，OpenWorker 新增可重用的通用 remote operator：`.github/workflows/ops-one-call-queue-drain.yml`。

初始 commit：`36cbd4a75a4abd3149cee7fa228e013eff5c22da`；增補 evidence 回寫 commit：`a23dd81e481fc237c2e776ef1cd56ee261fc5e8e`。

流程：exact COMPUTERNAME route → checkout latest OpenWorker → checkout latest go-tool-runtime → POST local go-tool `/agent/query` → go-tool 必須確認 expected registered queue-admin capability → `python -m coworker.queue_drain` → go-tool-runtime `gtr-actions-queue` 真正執行 query/cancel/verify → `clean=true` 且 `remaining_active=[]` 才成功 → 回寫 `evidence/ops/latest-queue-drain.json`。

不得自行重寫 query/cancel/verify 邏輯；OpenWorker 只負責 one-call UX，go-tool-runtime 仍是 Actions queue admin execution authority。

## REAL 驗收狀態

截至本文件建立時：`0004-045` READY；`latest-go-tool-query.json` 尚未回寫；`evidence/ops/latest-queue-drain.json` 尚未回寫。因此尚未證明 `clean=true`，不得宣告 queue 已清，也尚未重跑 `0004-045`。

## 下一個合法動作

取得 go-tool 真實回答 → 取得 OpenWorker one-call drain evidence（必須 `clean=true` 且 `remaining_active=[]`）→ 只在 queue clean 後依 go-tool 回答執行 `0004-045 cad.build_story_index` → 產出 `story-index.png + manifest + SHA256` → `0004-047 cad.render_story_viewports` 逐層 zoom PNG → `0004-049` multimodal 檢核 → `0004-050 Story Region`。
