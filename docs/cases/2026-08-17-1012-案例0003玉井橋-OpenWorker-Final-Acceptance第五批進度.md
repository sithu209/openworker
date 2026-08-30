# 案例 0003：玉井橋 — OpenWorker Final Acceptance 第五批進度

> 更新時間：2026-08-17 10:12（Asia/Taipei）
>
> Repo：`liuxb99/openworker`
>
> 狀態：`VERIFYING / UL7 RUNNER INFRASTRUCTURE BLOCKED`
>
> 本文件延續前四批 OpenWorker mini-Git / Final Acceptance 補強。昨日 REAL 成果仍是歷史 baseline；在新版 OpenWorker 自己完成 fresh reopen + WorkLedger acceptance 前，不恢復 `CLOSED`。

## 1. 本批結論

本批沒有把 Case 0003 的 `pending` 誤判成產品失敗。

最新 Final Acceptance：

- workflow：`Case 0003 Yujing Bridge OpenWorker Final Acceptance UL7`
- run：`31986095405`
- job：`95261288856`
- job name：`OpenWorker REAL Final Acceptance`
- requested labels：`self-hosted / Windows / X64 / UL7`
- 目前狀態：`queued/pending`
- 尚未開始任何 step，因此尚未產生 DTM / Blender / SceneX / OS 的 fresh acceptance PASS/FAIL。

昨日 SceneX 正式成功 job `95142388557` 已證明同一 routing contract 真實可用：

- labels：`self-hosted / Windows / X64 / UL7`
- runner：`DESKTOP-UL7V2VV-R006`
- runner id：`39`
- conclusion：`success`

同時查驗目前：

- `liuxb99/SceneX`：沒有 in-progress workflow run；
- `liuxb99/Terrain_To_DXF`：沒有 in-progress workflow run；
- `liuxb99/openworker` 的 in-progress CI 是 GitHub-hosted pytest/gui jobs，不是 UL7 self-hosted business job；
- Case 0005 push workflow 雖被建立，但其 `locate` job 因 commit message gate 為 `completed / skipped`，沒有佔用 UL7。

因此目前最合理的權威判定是：UL7 self-hosted runner 暫時沒有以 idle `UL7` runner 身分接單。這屬於 infrastructure availability，不屬於 Terrain / Blender / SceneX / OS 產品返工。

## 2. 本批修補 A：H11 CI 不再污染所有 main push

發現 `.github/workflows/engineering-h11-workspace-bootstrap-win11.yml` 原本：

```yaml
on:
  push:
    branches:
      - main
```

而且包含：

```yaml
runs-on: [self-hosted, Windows, X64]
```

這代表任何文檔、案例、WorkLedger commit 都會額外建立 generic Windows self-hosted 工作，會無謂增加三台本機 runner 的競爭。

已修 commit：

`73d14e2aa679bb90f3c5c918c4f02a2616cece09`

現在 H11 自動 push 只對 H11/runtime/engineering 相關程式、測試、workflow 與 `pyproject.toml` 生效；其餘案例與文檔修改不再觸發 H11 Windows job。`workflow_dispatch` 仍保留，真正需要時可人工/自動明確啟動。

這是 OpenWorker runner governance 的共用修補，不是 Case 0003 特例。

## 3. 本批修補 B：Final Acceptance revision invariants 永久測試

上一批已把 `scripts/case0003_final_acceptance.py` 改為：

- 每次 Final Acceptance 都建立新的 child revision；
- HEAD 是 `REWORK_REQUIRED` 時建立 `rework` child；
- 其他狀態建立 `acceptance` child；
- fresh artifact 只寫進這次 attempt revision；
- 同一 revision 的 duplicate logical artifact 不再靜默忽略。

本批新增永久測試：

`tests/test_case0003_final_acceptance.py`

commit：

`4abace74dd713b11bab2f45370a50478d4af23e6`

鎖定三個 invariant：

1. initial/progress HEAD → Final Acceptance 必須開新的 `acceptance` child；
2. `REWORK_REQUIRED` HEAD → Final Acceptance 必須開新的 `rework` child，並保留 `parent_revision_id / rework_of_revision_id / gap_owner_repo`；
3. 同一 acceptance revision 重複寫入相同 logical artifact 必須 fail，不能吞掉差異。

這使 `Work = mini-Git` 的 append-only 語義有永久 regression protection。

## 4. Runner availability 與產品失敗必須分離

OpenWorker 後續統一採以下分類：

```text
workflow/job 尚未取得 assigned runner
→ INFRASTRUCTURE_WAITING / INFRASTRUCTURE_BLOCKED
→ 不建立產品 REWORK_REQUIRED

runner 已開始執行
→ required product verifier FAIL
→ REWORK_REQUIRED
→ gap_owner_repo
→ child revision
→ 修 owning repo
→ rerun
```

原因：

- runner offline / unavailable 不代表 DTM 壞掉；
- queue backlog 不代表 SceneX regression；
- GitHub routing 問題不能污染產品 revision history；
- 只有產品 verifier 真正開始後的失敗才可形成 owning-repo rework。

## 5. Final Acceptance 正式 acceptance chain

UL7 接單後仍執行：

```text
Verify DESKTOP-UL7V2VV
→ fresh SceneX Region Pack
→ Godot 4.6.3 D3D12 REAL browse
→ fresh 1280×720 screenshot/evidence
→ OpenWorker Final Acceptance child revision
→ DTM SQLite read-only reopen + PRAGMA quick_check
→ AOI terrain-context/grid parse
→ Consumer orchestration parse
→ Blender 5.2 REAL .blend reopen + bpy object/scene validation
→ SceneX fresh evidence validation
→ OS delivery HTML reopen
→ Delivery tree non-empty validation
→ required checks all passed
→ accept_revision
→ deliver_revision
```

任何產品 check FAIL：

```text
check=failed
→ revision=REWORK_REQUIRED
→ gap_owner_repo=<owning repo>
→ verification_plan
→ 保留此次失敗 revision
```

## 6. 本批 commit / run 索引

- H11 CI path-scoping：`73d14e2aa679bb90f3c5c918c4f02a2616cece09`
- Final Acceptance revision tests：`4abace74dd713b11bab2f45370a50478d4af23e6`
- 最新 Final Acceptance run：`31986095405`
- 最新 Final Acceptance job：`95261288856`
- 歷史可證明 UL7 label 正確的 SceneX job：`95142388557` / runner `DESKTOP-UL7V2VV-R006`

## 7. 下一步

目前不應修改 DTM / SceneX / Blender 產品程式，也不應退回 matrix lottery。

下一個權威事件只能是：

1. UL7 runner 恢復並接下 `95261288856`；
2. 取得第一個 REAL verifier PASS/FAIL；
3. PASS 則繼續完整 acceptance chain；
4. FAIL 才依 `gap_owner_repo` 返工；
5. 最終 WorkLedger `accepted_revision_id == delivered_revision_id` 後才恢復 Case 0003 `CLOSED / REAL VERIFIED BY OPENWORKER`。
