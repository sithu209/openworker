# OpenWorker 已退役 — 現行 Authority 請使用 DirectWork

> **重要：此 repository 不再是新任務、新案例或本機工作總控的現行 authority。DirectWork 已正式取代 OpenWorker。**

## 現行正式架構

```text
ChatGPT / LLM / Local Coder
  → go-tool-runtime 查工具、方法、canonical inputs、negative knowledge
  → 必要時 GitHub Action 只傳短密語 / command envelope
  → DirectWork durable work
  → Queue
  → Slot/Executor
  → local tool / project workspace
  → Events / Evidence / Artifact
  → verified Drive publication（需要 ChatGPT 審查時）
  → exact Drive revision
  → ChatGPT review
```

## 本 repository 的定位

本 repo 現在只保留：

- 歷史案例與 REAL run evidence；
- 舊 WorkLedger / CaseWorklist / runner / workflow 記錄；
- OpenWorker → DirectWork 遷移歷史；
- root cause、失敗教訓、SHA、receipt、provenance 等不可抹除的歷史證據。

上述內容**不得**被大模型解讀成目前仍應使用 OpenWorker 執行新工作。

## 禁止事項

- 禁止新 work dispatch 到 OpenWorker。
- 禁止以 `openworker.*` action 作為新案例 canonical action。
- 禁止把 GitHub Actions workflow success 當 business completion。
- 禁止把 runner online 當 DirectWork durable work evidence。
- 禁止把 Drive Desktop sync/copy 當正式 cloud publication proof。
- 禁止從舊案例文件恢復「一次一個 GitHub business action」或「rerun workflow 就是 canonical recovery」等舊操作。

## 現行 authority

- **Business/control authority：`liuxb99/DirectWork` 主線。**
- **AI tool/method guidance：`liuxb99/go-tool-runtime` 主線。**
- **Google Drive → ChatGPT review：`drive.chatgpt.review.publish` → DirectWork durable work → `drive.file.publish-verified` → independent remote verification → exact Drive revision identity。**

若舊文件與 DirectWork/go-tool-runtime 主線契約衝突，**一律以 DirectWork + go-tool-runtime 現行主線契約為準；舊文件只保留歷史證據價值。**
