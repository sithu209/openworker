# OpenCode 本機總控操作規約

OpenCode 在本架構中只是本機控制入口，不是 Case authority。

## 唯一允許的 Case 控制入口

優先使用：

```text
%ProgramData%\OpenWorker\bin\openworkerctl.cmd
```

允許命令：

```text
openworkerctl supervisor status
openworkerctl case status 0005
openworkerctl case continue 0005
openworkerctl queue clear DESKTOP-ODAQN0D
```

## 執行規則

- Case 0005 只允許 `DESKTOP-ODAQN0D`。
- `case continue` 前先確認 supervisor `OPERATIONAL`。
- OpenCode 不自行拼 `:8848` REST payload，不自行選 capability，不直接改 `.openworker` ledger。
- 不使用 GitHub Actions 執行 Case、查 Case 進度或搬運成果。
- 進度以 `openworkerctl case status` 回傳的 OpenWorker durable ledger 為準。
- queue 阻塞時使用 `openworkerctl queue clear DESKTOP-ODAQN0D`，再重新 `case continue 0005`。
- 遇到 Drive review gate 時等待 review receipt；不得繞過 approval。
- 成果由 ODA 直接 Google Drive API 發布，不經 GitHub artifact。

## 成功定義

OpenCode terminal 顯示成功不代表 Case 成功。Case 0005 至少要看到：

1. local supervisor `OPERATIONAL` / `REAL_VERIFIED`；
2. `.openworker/case-supervisor-ledger.jsonl` 有完整事件；
3. 真實 `presentation/storyboard-text-only.pptx`；
4. 該 PPTX 已由 ODA 直接發布到 Google Drive；
5. ChatGPT 能從 Drive 取回並實際審查。
