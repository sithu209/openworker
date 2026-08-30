# OpenWorker 一鍵清隊列即時運維能力

日期：2026-08-18
狀態：IMPLEMENTED / WAITING FOR REAL HOST VERIFICATION

## 需求

清隊列是高頻運維動作，不應成為 Case Worklist 的業務步驟，也不應要求大模型自己串接 query → cancel → verify。

OpenWorker 對外提供一次呼叫完成的原子操作：

```text
openworker queue-drain --capability <capability-id>
```

亦提供獨立入口：

```text
openworker-queue-drain --capability <capability-id>
```

## 契約

一次呼叫內部必須完成：

```text
resolve go-tool-runtime
→ capability-scoped queue admin
→ query active runs
→ cancel queued / waiting / in_progress runs
→ verify
→ 若仍有 active run，於同一次 OpenWorker 呼叫內重試
→ clean=true 且 remaining_active=[] 才成功返回
```

特性：

- 幂等：空隊列重複呼叫仍成功。
- 可重複：OpenWorker 自身重複執行沒有關係。
- fail-closed：不能證明 `clean=true` 就返回失敗。
- capability scoped：不接受任意 repository 作為清理範圍。
- go-tool-runtime 仍是 GitHub Actions queue admin 的實際執行權威。
- 不改 Case Worklist canonical step；這是即時運維，不是產品步驟。

## Runtime discovery

OpenWorker 依序尋找：

1. 顯式 `runtime_root`；
2. `OPENWORKER_GO_TOOL_RUNTIME_ROOT`；
3. Windows canonical `D:\AI-Tools\AI Tool Runtime`；
4. current working directory（僅在它本身就是 go-tool-runtime 時）。

## 驗收

單元測試必須覆蓋：

- 已 clean 時一次返回；
- 第一次仍有 active run 時，同一次 OpenWorker 呼叫內再次 drain，直到 clean；
- capability 空白時 fail-closed；
- 實際 command 必須包含 `--workflow-scoped=true` 與 `--cancel-active=true`。

REAL 驗證下一步：在固定 Windows host 上對一個已註冊 queue-admin capability 建立可取消 run，執行一次 `openworker queue-drain`，確認輸出 `clean=true` 且 GitHub queue 無 active run。
