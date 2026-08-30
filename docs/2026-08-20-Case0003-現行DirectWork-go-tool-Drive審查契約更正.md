# Case 0003 現行 DirectWork / go-tool / Google Drive / ChatGPT 審查契約更正

- 更新時間：2026-08-20（Asia/Taipei）
- 適用案例：Case 0003 玉井橋
- 性質：現行操作契約更正；用來覆蓋舊案例文件中的過時操作方式

## 1. 為什麼需要更正

Case 0003 的歷史文件保存了大量 REAL 執行、Blender 回修、Drive publication 與 ChatGPT review 證據，這些歷史證據仍有效；但其中部分「怎麼執行下一步」的描述已被新版 DirectWork / go-tool 架構取代。

歷史證據不得刪除或改寫成沒發生過；過時的是操作方法，不是歷史事實。

## 2. 2026-08-20 起的現行權威鏈

```text
ChatGPT / LLM
  -> 先問 go-tool：查 capability、required inputs、guidance、negative knowledge
  -> DirectWork：建立/驅動 durable work
  -> 本機 executor / localexec：執行 owning capability
  -> durable evidence：received / queued / claimed / running / completed 或 blocked
  -> REAL artifact
  -> 需要 ChatGPT 審查時：drive.chatgpt.review.publish
  -> drive.file.publish-verified
  -> Google Drive 真實 upload + independent remote verification
  -> exact Drive revision identity
  -> ChatGPT 審查
  -> review receipt / decision
  -> PASS 才可進 delivery gate
```

### 權威判斷

- GitHub Actions workflow success 不是 business completion authority。
- Runner online 只證明 listener 在線，不等於 durable work 已完成。
- Google Drive Desktop 本機同步資料夾不是 publication authority。
- HTTP 200、檔案存在、非空 ZIP/PNG 都不能單獨代表審查閉環完成。
- 真正完成要看 durable work lifecycle、REAL artifact、Drive remote verification、exact Drive revision identity，以及需要時的 ChatGPT review receipt。

## 3. Case0003 舊文件中必須視為歷史、不可再照做的項目

### 3.1 `runs-on: [self-hosted, Windows, X64, UL7]` 作為 business scheduler

這是歷史 REAL workflow 的證據與故障排查資料，保留；但新工作不應把 GitHub runner label 當 canonical business scheduler。

現行方式：DirectWork durable work -> 指定本機 executor / localexec。機器約束仍需 fail-closed 驗證，例如 Case0003 固定 UL7 / `DESKTOP-UL7V2VV` 時，executor 必須核對實際 host。

### 3.2 「一次只跑一個 business action」

此規則已過時。新版架構允許 DirectWork 把可安全並行、依賴已滿足的工作拆成多個 durable works，由多 executor 並行；同一不可重入 action 仍不得重複競跑。

正確語意是：

```text
可並行的不同 work -> 可併發
同一不可重入 work -> single active claim / lease
依賴未滿足 -> 不得提前執行
```

### 3.3 「修 owning repo 後優先 rerun 原 GitHub job」

只保留為歷史 workflow 重現手段，不再是 canonical recovery。

現行 recovery：修 owning repo -> go-tool 重新取得現行 capability contract -> DirectWork 建立新的可追溯 durable work / retry -> executor 執行 -> durable evidence。

### 3.4 `openworker.review.publish` / 舊 `drive.review.publish` 作為一般成果上傳預設答案

過時。

一般「把成果上傳 Google Drive 給 ChatGPT 審查」的現行高層能力：

```text
drive.chatgpt.review.publish
```

其 canonical primitive：

```text
drive.file.publish-verified
```

目標是讓同一 durable work 完成：

1. 本機成果檢查；
2. Google Drive upload；
3. independent remote metadata verification；
4. 回傳 exact Drive revision identity；
5. 再交給 ChatGPT 審查。

舊 `drive.review.publish` 僅保留 legacy compatibility / 特殊治理型 bundle 情境，不是普通成果審查的預設路徑。

### 3.5 案例自行研究 OAuth / 寫 uploader / rclone / Drive Desktop copy

全部不是現行預設方法。

Case0003 已有 REAL 成功經驗，後續案例應重用 go-tool 公布的 Drive capability，不應讓 LLM 每次重新發明上傳方式。憑證由 runtime/capability contract 管理；不得把 token 寫入案例文件、receipt、log 或 Git。

## 4. Case0003 歷史證據仍然有效

以下類型資料仍應完整保留：

- DTM / AOI / Consumer / Blender / SceneX / OS 的 REAL run/job/commit 記錄；
- Blender 空白畫面與 camera / transform root cause；
- `BLENDER_VISIBILITY_OK` 等品質 gate 的形成過程；
- 已經真正存在的 artifact SHA256；
- 已完成的 REAL Google Drive publication 與可見 revision folder 證據；
- ChatGPT 實際做過的 visual/semantic review 結果；
- 失敗教訓與 negative knowledge。

這些是知識庫，不因架構升級而刪除。

## 5. 文件閱讀規則

讀取 `2026-08-17-1605-Case0003-玉井橋全流程操作手冊與Blender品質回修紀錄.md` 時：

- 歷史 run/job/SHA/root-cause/evidence：照原文視為歷史紀錄；
- 涉及「現在應如何 dispatch / rerun / upload / review」：以本文件與 go-tool 現行 capability contract 為準；
- 若舊文件與 go-tool 現行 guidance 衝突，以 go-tool 現行 guidance 為準；
- 不得因舊文件仍出現 OpenWorker workflow / GitHub Actions 路徑，就讓 LLM 回退舊架構。

## 6. 給大模型的最短操作提示

```text
先問 go-tool，不猜工具。
業務執行走 DirectWork durable work，不把 GitHub Actions success 當完成。
成果要給 ChatGPT 審查時，用 drive.chatgpt.review.publish，底層走 drive.file.publish-verified。
必須取得 remote verification + exact Drive revision identity，才交給 ChatGPT 審查。
歷史案例文件只保留證據；操作方式若與現行 capability 衝突，以 go-tool 現行 contract 為準。
```

## 7. 後續案例文件治理

Case0002、0004、0005 以及後續案例若仍存在相同舊語意，也應依同一原則修正：

- 不刪歷史證據；
- 明確標註 deprecated operational guidance；
- 將 canonical execution 改成 DirectWork durable work；
- 將工具選擇交給 go-tool；
- 將普通成果 Drive 審查統一為 `drive.chatgpt.review.publish -> drive.file.publish-verified`；
- completion 以 durable evidence / REAL artifact / remote verification 為準。
