# Case 0005 白雪公主：真實 Case Status 與 Bootstrap 啟動失敗診斷

更新时间：2026-08-19 11:22 +08:00

## 1. 本輪結論

Case 0005 的 transient command transport 已經真實打通到 ODA 本機 `openworkerctl -> localhost:8848`。

本輪不再把 GitHub transport 視為主要 blocker。最新權威 Case 狀態顯示，真正 blocker 已落到 **OpenWorker durable bootstrap job 啟動層**。

## 2. REAL case_status 證據

GitHub run：`32211118354`

ODA dispatch job：`95943906221`

Runner：`DESKTOP-ODAQN0D-R001`

Machine：`DESKTOP-ODAQN0D`

transport receipt：

- phase=`oda_accepted`
- command=`case_status`
- request_id=`20260819-1240-oda-case0005-status-010`
- accepted=`true`
- exit_code=`0`
- `github_action_used_for_command_transport=true`
- `github_action_used_for_business_execution=false`
- authority=`openworker`

OpenWorker node snapshot：

- online=`true`
- free_workers=`4`
- busy_workers=`0`
- max_workers=`4`
- queued_jobs=`0`
- 2 x NVIDIA GeForce RTX 5060 Ti
- service upgrade=`VERIFIED`
- supervisor API=`v1`
- capabilities 包含 `case0005 / comfyx / minimax-h3 / presentation / storyboard / video / local-supervisor`

但是 Case runtime 當下：

- `worklist=null`
- `controller=null`
- workspace ledger event count=`0`
- 所有可見 Case bootstrap durable jobs 均為 `failed / exit_code=1`

因此「bootstrap submit script succeeded=true」只代表 bootstrap durable job 成功入隊，不代表 controller bootstrap 成功完成。

## 3. 最新失敗 bootstrap job

Job：`case0005-bootstrap-1787080499731203800`

Command：

```text
"C:\Python314\python.exe" -m coworker.case0005_logged_controller --node-url "http://127.0.0.1:8787" bootstrap --workspace "D:\AI-Work\jobs\0005-SNOW-WHITE" --manifest "D:\AI-Work\runtime\openworker\case-worklists\0005.json" --spec "D:\AI-Work\runtime\openworker\case-specs\0005.json"
```

CWD：`D:\AI-Work\runtime\openworker`

状态：`failed`

exit_code：`1`

执行时间只有约数十毫秒，stdout 为空，因此尚未进入正常 Python controller 输出阶段。

## 4. 已新增固定 bounded diagnosis

为避免 OpenWorker 原本 stderr tail 发生 mojibake，新增：

- `scripts/run-case0005-diagnose-oda.ps1`
- `.github/workflows/diagnose-case0005-oda.yml`
- `diagnostic-requests/case0005.json`
- `case-evidence/case0005-diagnose/latest.json`

诊断严格限制：

- Case 固定 `0005`
- Machine 固定 `DESKTOP-ODAQN0D`
- 只从 OpenWorker `case status` 取得 latest job 路径
- 只允许读取 `%ProgramData%\OpenWorker\node\logs` 下 bounded 64 KiB 日志
- 不接受任意路径输入
- 不执行 Case 业务动作

诊断 run：`32211696087`

## 5. 真實 stderr 根因

最新失败 job stderr：

`C:\ProgramData\OpenWorker\node\logs\case0005-bootstrap-1787080499731203800.stderr.log`

文件只有 `18 bytes`。

原 OpenWorker tail 因编码误判显示乱码。

多编码诊断结果：

- UTF-8：乱码
- UTF-16LE：乱码
- **CP950：`找不到網路路徑。`**

stdout：0 bytes。

因此本次 bootstrap 不是 Director、ComfyX、OpenMAIC 或 Worklist acceptance failure，而是在 Python controller 真正启动前，Windows process/cwd/path 层就失败。

## 6. 当前假设与下一步验证

OpenWorker runtime `manager.go` 在 Windows 上：

1. 使用 `cmd.exe /D /S /C <command>`。
2. 设置 `cmd.Dir = job.CWD`。
3. Case bootstrap 的 `job.CWD = D:\AI-Work\runtime\openworker`。
4. OpenWorker Node 是 Windows service；service account 与交互式 runner 的磁盘/网络路径可见性必须独立验证。

由于 command 本身没有网络路径，而 stderr 明确是「找不到網路路徑」，下一步优先检查：

- service/runner 身份
- `D:` 是否为 service account 可见的本机 volume
- `D:\AI-Work\runtime\openworker` 是否为 junction/symlink/reparse 到网络位置
- 相同 CWD 下 direct Python 是否可启动
- 相同 CWD 下 `cmd.exe /D /S /C` 包装是否可启动 Python

已新增固定 runtime probe：

- `scripts/probe-case0005-runtime-oda.ps1`
- `.github/workflows/probe-case0005-runtime-oda.yml`
- `diagnostic-requests/case0005-runtime.json`
- 结果目标：`case-evidence/case0005-runtime-probe/latest.json`

## 7. Receipt 发布冲突缺口同步修复

`status-010` 本机 command 实际成功，但最终 `command-results/oda.json` commit 在 `git pull --rebase` 时与其他 receipt commit 冲突，导致 workflow conclusion 变成 failure。

因此不能用 workflow conclusion 判断本机 command 是否成功。

已开始改为 per-request immutable final receipt：

`command-results/oda/<request_id>/final.json`

相关 commit：`2ce631d074e0c83da961f136ba5bc0f983973585`

这样不同 request 不再争抢同一个 `oda.json`。

## 8. 当前 Case 业务状态

`0005-010` 仍不能标成功。

当前应标记：

- transport：REAL working
- ODA control plane：REAL_VERIFIED
- OpenWorker node：ONLINE / 4 free workers
- latest bootstrap durable job：FAILED
- business worklist/controller：not materialized in authoritative status
- blocker：Windows process/cwd path startup returns CP950 `找不到網路路徑。`

在 runtime probe 确认并修复启动路径前，不再盲目 `case_continue`，避免重复提交同一失败 bootstrap。
