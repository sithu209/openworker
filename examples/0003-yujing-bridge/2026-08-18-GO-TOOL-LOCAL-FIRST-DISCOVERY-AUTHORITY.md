# Case 0003 玉井橋 — go-tool local-first discovery authority

日期：2026-08-18

## 發現的缺口

Case 0003 的 Terrain execution handler 已經 localize，但 `go-tool-runtime/config.yaml` 仍保留 GitHub-first 時期的 discovery metadata：

- `terrain.streetview.acquire`
- `terrain.aoi.build`
- `terrain.consumer.orchestrate`
- `terrain.blender.execute`

這些 capability 的舊 metadata 仍帶 `workflow` / `runner_labels`，如果 knowledge/discovery 只讀這些欄位，模型可能錯誤選擇 GitHub Actions 作 business execution plane。

這屬於 information-plane authority 漂移，而不是 Terrain owning tool 的 execution 缺口。

## 修正

Repo：`liuxb99/go-tool-runtime`

提交：

- `93c2cfe7e692034e84e55fc63f90b25155e725a9` — Config Load 完成 fragment 載入後執行 canonical local execution normalization。
- `56b0f2c31e1d074069054692c27f7a0e666b1ad9` — 新增 `internal/config/local_first_overrides.go`。
- `addc6a7045f9de682d3eff9020517aebd1213ee3` — regression test，鎖定 Case 0003 Terrain capabilities 必須為 `execution.mode=local_action`，且 unrelated capability 不得被改動。

Canonical normalization 只作用於：

```text
terrain.streetview.acquire
terrain.aoi.build
terrain.consumer.orchestrate
terrain.blender.execute
```

載入後 description 會明確宣告：

```text
OpenWorker durable local job
→ go-tool localexec
→ owning repository local entrypoint
```

既有 `workflow` / `runner_labels` 僅保留為 legacy fallback / CI metadata，不再具有 business execution authority。

## Execution reality check

這次沒有只改 metadata。

已重新確認：

- `internal/localexec/terrain_local.go` 實際註冊 Street View / Orthophoto / AOI。
- `internal/localexec/terrain_downstream_local.go` 實際實作 Consumer / Blender。
- `cmd/gtr-local-exec/main.go` 會呼叫 `RegisterTerrainDownstream(terrainRoot)`，因此 Consumer / Blender 確實進入 canonical local executor registry。

所以這次變更是「information plane 對齊既有 execution plane」，不是宣告一個不存在的 local capability。

## Case 0003 acceptance 影響

此修正只代表工具選路資訊已與新版架構一致，**不代表任何新的 REAL artifact 已接受**。

Case 0003 acceptance boundary 仍維持：

- GEO：ACCEPTED
- Street View / Orthophoto / Terrain / Consumer / Blender / SceneX / OS / Drive review：仍需 UL7 fresh REAL physical QC。

下一次 UL7 執行應使用最新版 go-tool discovery；模型查到上述 Terrain capabilities 時，canonical route 必須是 OpenWorker → localexec，不得因 legacy workflow metadata 回退 GitHub-first。
