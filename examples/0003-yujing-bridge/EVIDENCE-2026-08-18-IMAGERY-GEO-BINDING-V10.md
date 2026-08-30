# Case 0003 — Imagery accepted-GEO binding / controller v10

更新時間：2026-08-18 Asia/Taipei

## 問題

Case 0003 imagery gate 已有 physical SHA、Street View renderer provenance 與 semantic visibility，但先前沒有把 imagery manifest 明確綁定到目前 `geo/geolocation.json` 的 accepted latitude/longitude。若 workspace 殘留另一個位置的自洽 imagery evidence，理論上可能形成 stale-location false PASS。

## 修正

### go-tool-runtime

`terrain.streetview.acquire` 的 workspace manifest 升為：

- `streetview-browser-screenshots/v3`
- 新增 `geolocation.lat/lng`

`terrain.orthophoto.acquire` 的 workspace manifest 升為：

- `orthophoto-workspace/v2`
- 新增 `geolocation.lat/lng`
- producer `plan.latitude/longitude` 仍保留作第二層來源證據

### OpenWorker imagery submit

`case0003_local_imagery_parallel.ps1` 升為 `openworker/case0003-local-imagery-parallel/v4`。

Street View / Orthophoto 除原有 SHA、host、provider、visibility 等 gate 外，新增：

- manifest geolocation 必須與目前 accepted GEO 一致；
- Orthophoto producer plan latitude/longitude 也必須與 accepted GEO 一致；
- tolerance = `1e-7` degree；
- GEO 改變後舊 imagery 自動失效並重新提交缺少的 imagery stage。

### Canonical controller

`case0003_local_continue.ps1` 升為 `openworker/case0003-local-continue/v10`。

Imagery contract：

`accepted-geo + physical SHA + producer provenance + semantic visibility`

因此 downstream Consumer / Blender 只有在 imagery bytes、producer receipt、semantic QC、fixed host 以及 accepted GEO 全部一致後才可能解鎖。

## 相關提交

- go-tool accepted-GEO evidence：`bd88e068607a2018a0d6f5627aa4a54e0ee023a9`
- OpenWorker imagery submit v4：`15e128acf8bf9fbc327c3b8e7fec9520d5a7213a`
- OpenWorker controller v10：`3d4019ff2b4c9c691aeb5de619bb6dad1e88ee35`
- go-tool regression test：`ae0a983f55ef98f47d5a9def2975232716b08165`
- OpenWorker source-contract test：`f9b1dfd78977ebebb5d0db60ab5bc3c0dbe92b45`

## Acceptance boundary

這一批只修正 correctness contract，**不構成 UL7 REAL imagery acceptance**。

目前仍只有 GEO 可稱 ACCEPTED。下一次 UL7 `case0003_local_continue_auto.ps1` 執行後，必須取得 current GEO 對應的 fresh Street View v3 四向 PNG 與 Orthophoto workspace v2 PHOTO2 mosaic，且 v10 gates 為 true，才可把 imagery 進一步寫入案例 acceptance history。
