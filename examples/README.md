# OpenWorker 工作範例 / 操作手冊

本目錄是 OpenWorker 所有「大模型實際完成工作」案例的**唯一統一入口**。

## 核心規則

1. 每個案例都是給大模型閱讀與執行的操作手冊，不是單純的開發進度報告。
2. 假設接手的大模型不知道各 owning repo 的原始碼；它應先讀案例手冊，再透過 go-tool / OpenWorker 發現正式能力、取得 canonical schema、檢查 readiness、dispatch、查 execution / job / artifact / delivery。
3. 案例一律驗證執行當下的最新正式工具提交。SHA 只記錄 provenance，不用來 pin 舊版工具。
4. 某一步如果只能靠開發者知道的 repo、Action、腳本或手工操作才能跨過，該步就是工具缺口；修 owning repo 後再從正式入口重跑。
5. GitHub self-hosted Action 是 execution / security boundary，不是案例本身的使用者入口。
6. REAL 案例必須追到實體成果與 evidence；不能以 queued / succeeded / API 回覆成功代替成果驗收。

## 案例索引

| 編號 | 案例 | 手冊 | 狀態 |
|---|---|---|---|
| 0001 | OpenWorker 工程工作基線案例 | [`0001/README.md`](0001/README.md) | 建立 canonical manual；既有工程鏈持續驗證 |
| 0002 | 阿拉丁神燈 Source-to-Film | [`0002-aladdin/README.md`](0002-aladdin/README.md) | REAL 閉環進行中 |

## 每個案例的固定結構

- `README.md`：canonical 操作手冊，下一個大模型從這裡開始。
- `STATUS.md`：目前實際進度、最近一次 REAL run、已知 blocker、下一個驗收點。
- `evidence/README.md`：證據索引；大型實體 artifact 保存在正式 workspace / artifact registry，不把影片複製進 Git。

新增案例時從 `0003-*` 往後編號，並先更新本索引。