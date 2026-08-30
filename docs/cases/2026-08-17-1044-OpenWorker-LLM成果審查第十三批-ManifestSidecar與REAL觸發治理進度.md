# OpenWorker LLM 成果審查第十三批：Manifest Sidecar 與 REAL 觸發治理進度

時間：2026-08-17 10:44（Asia/Taipei）

## 本批目標

延續第十二批 exact manifest SHA binding 與原生 tuning revision，補齊「遠端 ChatGPT 如何可靠取得 exact manifest SHA」與「binding helper 變更後必須自動觸發 Case 0003 REAL gate」兩個實務缺口。

## 已完成

### 1. Portable manifest SHA sidecar

新增 `coworker/review_bundle_binding.py`：

- `manifest_sha256(bundle_root)`：對 immutable `manifest.json` 計算 SHA256。
- `write_manifest_sha256_sidecar(bundle_root)`：建立 `manifest.sha256`。
- sidecar 已存在且內容與 manifest 不一致時 fail-closed。
- 相同 immutable bundle 重複呼叫可 idempotent 返回同一 SHA。

Commit：`c6db396d92d9a08575d411be910b9a60c6a59c9d`

### 2. Case 0003 正式 handoff 接上 sidecar

`scripts/case0003_review_handoff.py` 現在：

1. `ReviewCycle.build_bundle()` 建 immutable bundle。
2. 對 exact `manifest.json` 產生 `manifest.sha256`。
3. 再把整個 bundle（含 sidecar）原子 handoff 到 Google Drive TEMP exchange。
4. `WAITING_DRIVE_HANDOFF` 與 `WAITING_LLM_REVIEW` state 都記錄 `bundle_manifest_sha256`。
5. terminal marker 同時輸出 revision、manifest SHA、Drive target。

因此 ChatGPT 在 Drive 端不需要自行重新計算 manifest bytes 的 hash，只需讀 `manifest.sha256`，並原樣放入 review receipt 的 `bundle_manifest_sha256`。

Commit：`61deb17459a157367537f49f545c218ce2bb6628`

### 3. Sidecar 永久測試

新增 `tests/test_review_bundle_binding.py`：

- sidecar 必須等於 exact `manifest.json` SHA256。
- same bundle 重複生成 binding 必須 idempotent。
- stale/tampered sidecar 必須 fail-closed。

Commit：`e383618ce41f777570e8670729771e4449f5f70f`

### 4. REAL workflow trigger 補齊

`.github/workflows/case-0003-yujing-bridge-ul7.yml` 的 `push.paths` 已加入：

`coworker/review_bundle_binding.py`

之後 binding helper 單獨修改也會觸發 Case 0003 UL7 REAL gate，不會出現治理碼變了但實機驗證沒跟著跑的缺口。

Commit：`4ca3a237512dbec1339aa8f6595bd39e109b8d0b`

## 目前驗證狀態

### Hosted CI

最新 sidecar test 對應 CI：

- run `31988856909` / CI #315
- `gui-unit` 已 SUCCESS
- `pytest` 仍在 Test
- `gui-e2e` 仍在 e2e

因此本批尚未提前標記完整 CI PASS。

### Case 0003 REAL

最新正式 run：

- run `31988901946`
- run number `22`
- head `4ca3a237512dbec1339aa8f6595bd39e109b8d0b`
- 狀態：queued

前一個 #21 已由 single-writer concurrency 正常取消。

目前分類仍是 `INFRASTRUCTURE_WAITING`：UL7 尚未接單，而不是產品 `TOOL_GAP`。

## 現在的 review binding 閉環

```text
REAL artifacts
→ Review Bundle
→ review-request.json
→ manifest.json
→ exact SHA256(manifest.json)
→ manifest.sha256
→ Google Drive TEMP
→ ChatGPT 讀 artifacts + manifest.sha256
→ receipt.bundle_manifest_sha256
→ OpenWorker 重新計算本地 manifest SHA
→ exact match 才允許 PASS / TUNE / FAIL / TOOL_GAP
```

## 下一步

1. 等最新 Hosted CI terminal，若有舊 contract 被 manifest binding 抓出，直接修正式呼叫點，不放寬規則。
2. 等 UL7 接單，產生第一份含 `manifest.sha256` 的真實 Case 0003 Drive Review Bundle。
3. ChatGPT 透過 Google Drive Connector 讀全部 artifacts 與 sidecar。
4. 產生第一份真實 PASS / TUNE / TOOL_GAP receipt。
5. 驗證 WorkLedger accepted/delivered pointer 只有 PASS 後才能移動。
