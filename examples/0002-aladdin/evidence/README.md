# 0002 阿拉丁神燈 — Evidence Index

本目錄只保存**證據索引與驗收規則**；大型 MP4、workspace、ledger 與 delivery artifacts 保存在正式執行環境，不把二進位成果複製進 Git。

## 當前正式鏈

- go-tool capability：`engineering.source-to-film`
- formal execution / OS run：`31916089801`
- OS job：`95087955499`
- runner：`DESKTOP-ODAQN0D-R003`
- OS head：`86376b7ef635afa65de1aa1bd591b5908958812c`

## 必須收集的 evidence

1. 工具版本 provenance：OS / OpenWorker / go-tool / Studio / ComfyX 實際 checkout SHA。
2. go-tool health / capabilities / capability detail / readiness / dispatch response。
3. execution id / target run id / job id / runner identity。
4. canonical input：story / title / delivery_case。
5. Studio final narrative prompt 與 shot semantics。
6. ComfyX execution ledger：execution_id / prompt_id / job_id / shot_id / physical artifact path / size / mtime / SHA256。
7. Studio canonical workspace artifact metadata。
8. source / canonical / ledger SHA256 identity proof。
9. visual semantic QC 與 technical QC。
10. Final Assembly、字幕、Artifact Registry、Delivery Revision、website delivery evidence。

## REAL 驗收規則

- queued / workflow success 本身不是成果。
- API 回傳 succeeded 但沒有 physical artifact，不算成功。
- 舊 artifact、mtime 不新鮮、無 execution correlation，不算成功。
- 只有 accepted artifact 可進 final delivery。
- 每次重跑都記錄當下最新工具 SHA；SHA 是 provenance，不是 compatibility pin。

完成後由 `STATUS.md` 指向本索引中的最終 accepted evidence。