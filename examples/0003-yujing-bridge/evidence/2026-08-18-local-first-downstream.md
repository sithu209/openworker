# Case 0003 玉井橋 — Local-first downstream migration evidence

日期：2026-08-18 Asia/Taipei

狀態：`IMPLEMENTED / REAL UL7 EXECUTION STILL REQUIRED`

## 本批目的

把 Case 0003 從 imagery / AOI 之後的 consumer orchestration 與 Blender business execution 也移出 GitHub-first 主路徑，延續新版 canonical architecture：

```text
OpenWorker local controller
→ durable job / fixed host / workspace
→ go-tool gtr-local-exec
→ Terrain_To_DXF owning local entrypoint
→ physical workspace artifacts
→ QC
```

GitHub Actions 僅保留 fallback / CI / bootstrap / evidence transport，不作本案例 canonical business execution plane。

## 1. Orthophoto durable rerun repair

案例檢查發現 `internal/orthophoto/nlsc.go` 原本使用 `os.Rename(tmp, outputPath)`。Windows 上若目的檔已存在，本機 durable job 重跑可能失敗。

已修：

- `e4c427f7a7f805d437ee8254e0ea2677ce2d5846` — rerun-safe destination replacement，失敗時保留/恢復舊輸出。
- `d502506b78faaf33662dba4f4d51987882e4a247` — 新增 same-path rerun test，要求連續兩次 acquisition 成功、SHA 穩定、temp/backup 不殘留。

此修復是 local durable execution 的必要條件；不得把首次成功當成可重跑證明。

## 2. Terrain consumer owning local entrypoint

Terrain_To_DXF：

- `fb78a23fe31468dfd11900cc0278188e288d4ae1`
- `scripts/terrain_consumer_local.ps1`

本機入口會：

- fail-closed 驗證 `COMPUTERNAME == assigned_host`
- 要求 canonical workspace、accepted geolocation、terrain context
- 執行 consumer contract tests
- build/run `terrain-workspace-consumer-orchestration`
- 驗證 7 個 consumer physical artifacts
- 驗證 `consumer-orchestration/v1`
- 驗證 terrain mesh 存在/非空
- 輸出 SHA256 receipt

## 3. Terrain Blender owning local entrypoint

Terrain_To_DXF：

- `490023ef10200d23f872439325a11712f02c47bb`
- `scripts/terrain_blender_local.ps1`

本機入口會：

- fail-closed 驗證 assigned host
- orchestration path 必須 stay inside workspace
- 探測 Blender 5.2 / 5.1 / 5.0 / 4.5 或 PATH
- 執行 Blender contract tests
- build/run `terrain-blender-execute`
- 產生 REAL `.blend`、render PNG、execution request、scene evidence、render handoff
- 驗證 evidence/handoff schema
- 驗證 scene/render SHA256 provenance
- 輸出 localexec receipt

## 4. go-tool localexec registration

新增：

- `999896e75e6d272c45d6dd397f084912363103df` — `terrain.consumer.orchestrate` / `terrain.blender.execute` handlers
- `36c3064bbc3ba98b0ac15e979baf152f9f59fef4` — `gtr-local-exec` 啟動時註冊 downstream Terrain local handlers
- `bfa972d043b49e04812dde1a37955ea6183a260d` — host/path/local-entrypoint tests
- `18e281b4e9c4e7be83e1b69518d5df1d108b7cac` — 跨平台 normalize orchestration path separators，避免 `..\` 在非 Windows 測試環境逃過 gate

## 5. OpenWorker Case 0003 durable submit entrypoints

新增：

- `1f7b8eb4620e85bc33e5713ca35cf53bf16a33c4` — `scripts/case0003_local_consumer.ps1`
- `d81eeb1976f82c08789ced04b8956cc09a994815` — `scripts/case0003_local_blender.ps1`

兩者皆：

- fixed machine = `DESKTOP-UL7V2VV`
- canonical workspace = `D:\AI-Work\jobs\0003-YUJING-BRIDGE`
- POST durable job 到 local OpenWorker `/v1/jobs`
- command 執行 `go run ./cmd/gtr-local-exec --claim ...`
- `github_business_transport=false`

Consumer 必須等 accepted terrain context；Blender 必須等 consumer orchestration，不能競跑。

## 6. Case 0003 canonical local pipeline after this batch

```text
GEO accepted
   ├─ Street View localexec ─────┐
   ├─ Orthophoto localexec ──────┤ independent imagery work
   └─ AOI / DTM localexec ───────┘ (AOI uses accepted geo + canonical DTM catalog)
                    ↓
             physical QC gates
                    ↓
       terrain.consumer.orchestrate
                    ↓
          terrain.blender.execute
                    ↓
              SceneX REAL
                    ↓
      OS Artifact Registry / Delivery
```

## 7. Acceptance boundary

本批只有程式與本機執行路徑完成，**不能因此標記 REAL ACCEPTED**。

目前仍需在 UL7 實際執行並檢查：

1. Street View 四向 PNG visibility PASS。
2. Orthophoto PHOTO2 mosaic visibility / tile provenance PASS，並實際驗證同一路徑 rerun。
3. AOI required terrain artifacts + `usable_tiles > 0`。
4. Consumer 7 個 physical artifacts + mesh provenance。
5. Blender REAL `.blend` + `terrain-render.png`，並由 ChatGPT/人工視覺檢查，不只看 SHA/schema。
6. 再接 SceneX REAL screenshot、OS Artifact Registry、Delivery Revision。

這份 evidence 不宣稱 UL7 已實際執行；目前聊天環境沒有直連 UL7 `127.0.0.1:8787` 的 execution channel，因此不能用 GitHub Actions 冒充本機 REAL run。
