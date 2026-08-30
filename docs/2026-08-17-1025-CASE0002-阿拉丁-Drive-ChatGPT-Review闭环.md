# CASE 0002 阿拉丁 — Google Drive → ChatGPT 成果審查閉環

時間：2026-08-17 10:25（Asia/Taipei）  
現行契約更正：2026-08-20（Asia/Taipei）

> **2026-08-20 現行操作規則**：本文 2026-08-17 的 run、commit、失敗/成功證據保留為歷史事實；涉及「現在怎麼 dispatch、handoff、上傳 Drive、判斷完成」時，一律以 **go-tool + DirectWork durable work** 為準。OpenWorker 舊腳本、Drive Desktop atomic copy、GitHub Action success 都不再是 canonical business path。

## 目標

Case 0002 不以 Action `success`、文件非空或 SHA 一致作為最終品質結論。機械驗證仍負責 provenance / reopen / decode / SHA；需要 ChatGPT 審查時，先由 go-tool 選擇現行 capability，再由 DirectWork 建 durable work，把成果透過 Google Drive 真實發布與遠端驗證後交給 ChatGPT 審查，返回 PASS / TUNE / TOOL_GAP / FAIL。

## 現行權威鏈

```text
ChatGPT / LLM
  -> go-tool 查 capability / inputs / guidance / negative knowledge
  -> DirectWork durable work
  -> 本機 executor / localexec
  -> REAL storyboard / PPTX / video / evidence
  -> drive.chatgpt.review.publish
  -> drive.file.publish-verified
  -> Google Drive upload + independent remote verification
  -> exact Drive revision identity
  -> ChatGPT physical artifact inspection
  -> review receipt / decision
  -> PASS 才可 delivery
```

Google Drive 只作 review exchange；durable work/evidence、artifact SHA、review verdict、parameter delta 與 owning-repo rework 必須可追溯。GitHub Actions 若被使用，只能作短密語/transport，不是 business scheduler 或 completion authority。

## 2026-08-17 歷史實作（保留作證據，不作現行預設操作）

### `scripts/case0002_review_handoff.py`

歷史 wrapper：

- work code：`CASE-0002-ALADDIN`
- assigned host：`DESKTOP-ODAQN0D`
- 支持 `--phase storyboard|final`
- storyboard 要求 PPTX、manifest、視覺資產與 evidence
- final phase 強制至少一個非空 `.mp4`

歷史流程曾使用 immutable bundle、WorkLedger 與 Drive sync folder atomic copy。這些紀錄保留用來解釋當時的證據與治理設計；**新執行不得把 Drive Desktop/sync copy 當 publication authority**。

## 現行 Drive / ChatGPT Review 規則

普通成果要交給 ChatGPT 審查時，模型不得重新研究 OAuth、另寫 uploader、猜 rclone、或把檔案複製到 Drive Desktop 後就宣稱完成。

現行高層 capability：

```text
drive.chatgpt.review.publish
```

canonical primitive：

```text
drive.file.publish-verified
```

完成至少要求：

1. source artifact 存在且符合案例 gate；
2. DirectWork durable work 有 received / queued / claimed / running / completed 或 blocked 證據；
3. Google Drive 真實 upload；
4. independent remote metadata verification；
5. exact Drive revision/file identity；
6. ChatGPT 審查的是該 exact revision；
7. review receipt 綁定該成果身份。

## 審查維度

- story / storyboard semantic correctness
- Aladdin / Genie character consistency
- scene / magic-lamp continuity
- shot composition / camera readability
- storyboard image quality and video-reference reuse suitability
- OpenMAIC slide readability / image placement
- final phase temporal coherence / motion quality
- subtitles / delivery quality
- parameter tuning opportunities
- real tool gaps requiring owning-repository repair

## 參數治理

LLM 只能對 allowlist 參數返回 TUNE：

- `video.duration_sec`
- `video.width`
- `video.height`
- `video.acceleration_profile`
- `video.seed`
- `presentation.image_scale`

模型路徑、workflow ID、ComfyUI node、checkpoint 等不屬於可自由調參項；若審查發現缺能力，返回 TOOL_GAP 並指定 owning repo / capability / verification plan。

## Review decision

歷史 `scripts/case0002_apply_llm_review.py` 的 PASS/TUNE/TOOL_GAP/FAIL 語意仍可作治理參考：

- PASS → reviewed revision 才可進 delivery gate
- TUNE → 建新 revision / parameter delta，再 REAL rerun + review
- TOOL_GAP → owning repo repair + verification plan
- FAIL → REWORK_REQUIRED

但新執行應由 DirectWork durable work 驅動相應 capability，不把手動執行舊 OpenWorker wrapper 當 canonical 路徑。

## 歷史永久測試與 commits

以下仍是有效歷史證據：

- `bf1078543e6cd01e3ede9a2795842162057eac7d` — Case 0002 Drive handoff wrapper
- `ebab68bdf7f29da65791ac898e5ed1806525393b` — ChatGPT review receipt apply
- `29478b8d9b0ad461c19176f4560d16f5eb9f6675` — governance regression tests
- 歷史 OpenWorker CI `31987877806` 僅代表當時 CI 狀態，不代表今天的 business completion。

## Case 0002 現行閉環

```text
ComfyX / Studio / OpenMAIC REAL artifacts
  ↓
mechanical QC / reopen / SHA / provenance
  ↓
go-tool 查現行 review publication capability
  ↓
DirectWork durable work
  ↓
drive.chatgpt.review.publish
  ↓
drive.file.publish-verified
  ↓
Google Drive remote verification + exact revision identity
  ↓
ChatGPT physical artifact inspection
  ├─ PASS → delivery gate
  ├─ TUNE → child/new revision → REAL rerun → review again
  └─ TOOL_GAP/FAIL → owning repo repair → REAL rerun → review again
```

## 下一步規則

1. 形成 REAL storyboard/reference image + image-bound PPTX 後，不直接跑舊 handoff script；先問 go-tool。
2. 由 DirectWork 建立 storyboard review durable work。
3. 使用 `drive.chatgpt.review.publish -> drive.file.publish-verified` 發布並取得 exact Drive identity。
4. ChatGPT 審查分鏡；TUNE/TOOL_GAP 先修再擴散到影片。
5. final MP4、字幕、QC 完成後，以同一現行 contract 做第二次審查。
6. 只有 final review PASS 才進 delivery gate。
