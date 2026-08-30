# OpenWorker Connector 可直接调用控制通道

日期：2026-08-18

## 背景

之前远程控制依赖「ChatGPT GitHub Connector 写入一个 commit → GitHub push event → Actions workflow」来间接下单。实测 Connector 通过 Contents API 产生的 commit 可以成功进入 `main`，但不能可靠地产生预期的 push workflow run，因此会出现“commit 已存在、但没有 ACCEPTED / VERIFIED receipt”的假触发现象。

OpenWorker 本机 Go runtime 本身已经具备直接控制 API，例如：

- `POST /v1/queue/drain`
- `POST /v1/cluster/queue/drain`
- `POST /v1/cluster/jobs`
- `GET /v1/cluster/status`
- `GET /v1/node/status`

真正缺口是：ChatGPT Connector 缺少一个稳定、可直接调用的远程入口。

## 方案

新增 `.github/workflows/openworker-control-issue.yml`，以 GitHub Issue 作为 Connector 可直接创建的 durable control command。

控制 Issue 必须满足：

- 标题以 `[openworker-control]` 开头；
- body 必须含一行 `command: <command>`；
- command 只允许白名单：`drain`、`reconcile`、`upgrade`。

Issue `opened` 事件由 GitHub 原生触发 GitHub-hosted runner，不依赖 self-hosted runner，也不依赖 Connector commit 的 push 事件。

控制 workflow 再使用仓库 `GITHUB_TOKEN` 的 `actions: write` 权限调用 GitHub Actions `workflow_dispatch` REST API：

- `drain` → `bootstrap-ul7-runner-label.yml`（当前实际为云端 emergency queue drain workflow）
- `reconcile` → `bootstrap-three-node-labels-v2.yml`
- `upgrade` → `upgrade-openworker-nodes-v2.yml`

GitHub 官方允许由 `GITHUB_TOKEN` 触发的 `workflow_dispatch` / `repository_dispatch` 继续产生新的 workflow run，因此避免普通事件的递归触发限制。

## 安全边界

- 不允许任意 workflow 名称；只能映射固定白名单。
- 不接受 shell、path、ref 等任意执行参数。
- 固定 dispatch `main`。
- 升级 workflow 仍保留每台机器的 `COMPUTERNAME` fail-closed 检核。
- Issue 本身就是 durable control event；成功 dispatch 后自动留言并关闭。

## 大模型调用方式

ChatGPT / GitHub Connector 无需再 push trigger 文件，只需直接创建 Issue：

```text
Title: [openworker-control] reconcile
Body:
command: reconcile
```

确认 runner registry 后再创建：

```text
Title: [openworker-control] upgrade
Body:
command: upgrade
```

需要紧急清队列：

```text
Title: [openworker-control] drain
Body:
command: drain
```

## 当前验证顺序

1. 建立 `reconcile` 控制 Issue，验证 Issue event → GitHub-hosted control workflow → `workflow_dispatch`。
2. 读取 `case-evidence/runner-registry/<sha>.json`，确认 UL7 / O87 / ODA 注册、online/busy、labels。
3. 建立 `upgrade` 控制 Issue。
4. 以三台 `ACCEPTED` / `VERIFIED` receipt 作为升级完成唯一依据。
