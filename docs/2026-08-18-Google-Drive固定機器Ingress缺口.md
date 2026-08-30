# Google Drive → 固定機器 Ingress 缺口與 REAL 驗證

日期：2026-08-18

狀態：**IMPLEMENTED — DRIVE INGRESS CODE/OWNING-CI GREEN / OPTIONAL CAPABILITY / NOT A UNIVERSAL ACCEPTANCE GATE**

## 架構邊界修正

本能力最初使用 KnowGraphGo 工程規範 ZIP 做 REAL ingress 案例，因此一度把 Google Drive OAuth provisioning 誤列為工程規範 corpus acceptance 的前置條件。

此判斷已修正。

Google Drive 在 OpenWorker 的主要角色是：**把需要 ChatGPT 視覺／多模態檢查的實體成果發布成可審查 evidence**。它不是 GitHub、固定機器或所有 source data 的通用 transport requirement。

新的權威路由規則見：

- `coworker/review_policy.py`
- `docs/2026-08-18-成果審查路由邊界.md`
- `tests/test_review_policy.py`
- `.github/workflows/review-policy-ci.yml`

Review Policy CI Run `32072184488` = **success**。

## Drive ingress 能力仍然保留

`coworker/drive_ingress.py` 提供 fail-closed raw-file ingress：

```text
Google Drive raw file
→ authenticated Drive API alt=media
→ expected size + SHA-256
→ unique temp download
→ atomic local publish
→ durable ingress receipt
```

安全規則：

- expected SHA 必須合法。
- expected size 必須為正。
- unique temp。
- downloaded byte count / temp size / temp SHA 必須一致。
- destination 已存在且 identity 相同：idempotent PASS。
- destination identity 不同：拒絕覆寫。
- final file 再驗 SHA/size。
- receipt 不保存 OAuth token。

CLI：`scripts/download_drive_file_atomic.py`。

Credential resolution：

```text
OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN
→ machine-local SecretStore google_drive / google_drive:* profile
→ Google ADC
```

固定 ODA workflow：`.github/workflows/external-source-drive-ingress-oda.yml`。

## Targeted / owning CI

`tests/test_drive_ingress.py` 已覆蓋：

1. initial publish。
2. idempotent replay。
3. wrong SHA reject。
4. wrong size reject。
5. conflicting destination reject且保留原檔。
6. SecretStore Google Drive profile fallback。

Drive Ingress owning CI Run **`32071211423` = success**：

- project/dev dependency install：PASS。
- py_compile：PASS。
- blocking tests：PASS。

因此 Drive ingress 程式品質已 GREEN。

## 歷史 REAL ODA runs

用 KnowGraphGo canonical standards ZIP 做 transport 測試：

```text
file id = 1tDuIxI_bTd19o3qK48OBePzfiESSo5DN
size    = 1,719,409 bytes
sha256  = 9bd159e9dc625efd35fd48f13da724d35dc83458557661255d9063406287a702
```

三次 REAL run：

### `32069844110`

- ODA authority PASS。
- targeted tests 5 passed。
- OAuth Actions secret absent。

### `32070110999`

- ODA authority PASS。
- targeted tests 6 passed。
- `env_present=false / local_profiles=0 / ADC unavailable`。

### `32070519847`

- ODA authority PASS。
- targeted tests `6 passed in 0.22s`。
- user SecretStore probe：`inspected_secret_files=0 / readable_active_drive_stores=0 / ambiguous=false`。

這些 run 的正確結論是：**ODA Drive ingress REAL credential provisioning 尚未完成**。

不再推論為：**KnowGraphGo engineering standards corpus 被阻塞**。

## 何時 Drive 是 blocking gate

只有 acceptance contract 明確需要感知品質判斷時才是 blocking gate，例如：

```text
Blender render
工程圖／施工圖
影片
3D scene screenshot
PDF 版面
網站畫面
音訊成果
```

這些案例需要：

```text
physical artifact
→ Drive review bundle
→ ChatGPT multimodal inspection
→ review receipt
```

此時 OAuth / Drive publish failure 才應阻塞 delivery acceptance。

## 何時 Drive 不是 blocking gate

例如：

```text
hash / size / line count
JSON schema
SQLite round-trip
GraphData deterministic IDs
ledger provenance
machine-readable receipt
純文字 corpus ingestion
```

若全部品質條件可由 deterministic machine evidence 驗證：

```text
ReviewRequirement(machine_verifiable=True)
→ ReviewRoute.MACHINE_VERIFIABLE
→ google_drive_review_required=false
```

工程規範案例即屬此類。

## 現在 Drive ingress 自己的未完成項

若未來某個真正需要 Drive multimodal review 的案例指定 ODA 為發布／下載 execution identity，仍需任一合法 credential source：

```text
A. OPENWORKER_GOOGLE_DRIVE_ACCESS_TOKEN
B. runner identity SecretStore google_drive profile
C. Google ADC
```

在沒有這種實際需求前，不應為了純 machine-verifiable 案例反覆重跑相同 OAuth probe。
