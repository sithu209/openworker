# 案例 0001：OpenWorker 工程工作基線

> 類型：大模型逐步操作手冊  
> Canonical owner：OpenWorker `examples/0001/`

## 目的

0001 是 OpenWorker 的工程工作基線案例，用來驗證「大模型在不知道 owning repo 內部實作的前提下，能否從 OpenWorker / go-tool 的正式資訊入口發現能力、建立受控工作、取得成果並留下可追溯證據」。

它不是指定某一個底層工具的單元測試；它驗證的是 worker 的通用工作方法。

## 操作順序

1. 讀本手冊，不預先閱讀 owning repo 原始碼。
2. 向 go-tool 查 health。
3. 列 capabilities，根據使用者任務選擇正式能力。
4. 讀 capability detail / canonical schema。
5. 查 readiness；缺依賴時 fail-closed。
6. 用 canonical input dispatch，保存 execution id。
7. 透過 OpenWorker / go-tool 查 execution、job、blocker、artifact。
8. consequential side effects 只走受控 engineering tools / self-hosted Action boundary，不用 unrestricted shell 當正常兜底。
9. 成果必須進 Project Work Ledger / workspace / artifact lifecycle，並能從使用者任務追到 physical artifact。
10. 若某一步工具回答不了，將它記為工具缺口，修 owning repo 後從正式入口重跑。

## 最低驗收

`user request → OpenWorker → go-tool discovery/schema/readiness → controlled dispatch → execution/job → physical artifact → ledger/provenance`

必須同時成立：

- 使用最新正式工具提交；SHA 只記 provenance。
- 有 execution / job identity。
- 有 runner / host identity（若工作需要本機執行）。
- 有 canonical workspace。
- 有 physical artifact 或明確的 domain result。
- 有 accepted / rejected artifact disposition。
- 有 append-only work ledger / evidence。
- 失敗能從正式 query surface 被下一個大模型理解，而不是只能讀 Action log 猜原因。

## 與後續案例的關係

0001 驗證通用 worker 方法；0002 阿拉丁神燈則把同一方法套到完整 Source-to-Film production。

後續所有案例都繼承 0001 的規則：**先問工具、受控執行、實體成果、可追溯證據、最新工具失敗就修最新 owning layer。**