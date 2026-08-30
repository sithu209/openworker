# E6.4 Public RC Flow API 與 E2E Verification

## 目的

E6.4 關閉 E6.3 的兩個技術缺口：

1. OpenWorker 不應由 managed flow 直接呼叫 `EngineeringOSClient` 私有 `_object()` / `_required_id()`。
2. 需要一個可在真實部署環境執行的 E2E verifier，才能把「單元測試可用」與「多 repo runtime 真的可用」分開驗證。

## Public API

新增：

```python
EngineeringOSFlowClient.execute_rc_column_flow(
    job_id=...,
    column=...,
)
```

正式 route 仍是 AI-Engineering-OS：

```text
POST /api/v1/jobs/{id}/flows/rc-column
```

`managed_rcflow.py` 與 Engineering Coworker Tool 均只依賴這個 public method，不再直接碰 transport/private helper。

## 可部署 E2E Harness

新增 CLI：

```text
openworker-engineering-e2e
```

範例：

```bash
openworker-engineering-e2e \
  --base-url http://127.0.0.1:8080 \
  --project-id <PROJECT_ID> \
  --confirm-side-effects
```

這會：

```text
readiness
→ 驗證 Project identity
→ 建立 E2E Job
→ AI-Engineering-OS RC Flow
   → Design Forge calculation
   → EngSketch drawing
   → AI-BIM-Forge IFC
→ 驗證 Calculation + Drawing + BIM Artifacts
→ 停在 review
```

若另外顯式指定 reviewer：

```bash
--reviewer engineer-a
```

才會逐一核准目前 Artifact revision，並要求 OS 回報 Job `completed`。

只有再指定：

```bash
--publisher publisher-a
```

才會執行正式 Publish，並要求 OS 最終 Job `published`。

## 安全規則

- CLI 沒有 `--confirm-side-effects` 時直接拒絕執行。
- `publisher` 不允許在沒有 `reviewer` 時使用。
- 預設驗證停在 `review`，不自動核准工程成果。
- Reviewer / Publisher 身份必須顯式提供。
- Publish 仍由 AI-Engineering-OS 自己執行 Approval、SHA256、Delivery staging 與 website gate。

## VERIFICATION 定義

E6.4 提供 verifier，不代表目前已經執行成功。

Segment 只有在實際部署環境跑完以下條件後，才能從 `IMPLEMENTED — WAITING FOR FULL VERIFICATION` 升級：

1. AI-Engineering-OS readiness = ready。
2. Design Forge、EngSketch、AI-BIM-Forge 都有正確 runtime config。
3. RC flow 真的產生 calculation、drawing、IFC artifacts。
4. Artifact path/sha256 可由 Delivery Service 驗證。
5. 若執行 reviewer/publisher 模式，Review → completed → publish → published 全部成功。
6. 完整 OpenWorker pytest / compileall 通過。

因此 E6.4 的價值是把「怎麼驗證」變成可重複執行的正式程式，而不是用 mock 結果冒充 Production E2E。
