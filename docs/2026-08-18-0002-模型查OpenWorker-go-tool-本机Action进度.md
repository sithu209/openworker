# 案例 0002：模型查询 OpenWorker → go-tool → 本机 Action 进度

日期：2026-08-18（Asia/Taipei）

状态：`KNOWLEDGE PATH REPAIRED / REAL ACTION DISPATCH NEXT`

## 1. 本轮目标

案例不允许维护者或大模型预先记住工具调用方式。正确路径必须是：

```text
用户：继续案例
→ 大模型查询 OpenWorker 当前 CaseWorklist
→ 得到 canonical next step / allowed_actions / acceptance / assigned_host
→ 大模型查询 go-tool-runtime
→ 得到 owning repo / workflow / canonical inputs / local_action / 验收规则
→ 大模型通过正式本机 Action 执行工具
→ 读取 run / jobs / logs / receipt / artifact
→ 按 Worklist acceptance 验收
→ 再查询下一步
```

## 2. OpenWorker 查询结果

0002 manifest 已能告诉模型：

- workspace：`D:\AI-Example\0002`
- assigned host：`DESKTOP-ODAQN0D`
- 第一阶段简报步骤：`0002-025`
- allowed action：`presentation.openmaic`
- acceptance：`storyboard_pptx / storyboard_manifest / storyboard_pptx_sha256 / slide_count / reopen_receipt / image_count`
- `0002-030` 图片生成依赖 `0002-027` 用户批准，因此不得抢跑。

## 3. go-tool 查询发现的缺口

原 `presentation.openmaic` capability 已有：

- owning repo：`liuxb99/openmaic-fork`
- workflow：`operator-presentation-generate.yml`
- canonical inputs
- `execution.mode = local_action`
- PPTX reopen / slide count / SHA / workspace boundary validations

但对案例 0002 第一阶段而言仍缺：

1. 没有明确告诉模型无配图阶段如何机器验收。
2. OpenMAIC Action 最终 receipt 没有 OOXML media count，无法证明 PPTX 真正没有嵌入图片。
3. 没有 0002 对应 operator guide 将 OpenWorker acceptance 与正式 Action contract 接起来。

## 4. 本轮修复

### OpenMAIC owning repo

commit：`66ed96eb1cd7bbb809016fa3c07feb762871889e`

正式 `operator-presentation-generate.yml` 的最终机器 receipt 新增 `artifact.media_count`，通过重新打开 PPTX OOXML 并统计 `ppt/media/*` 实体文件取得。

因此：

```text
0002-025 text-only storyboard PPTX → media_count == 0
0002-055 illustrated storyboard PPTX → media_count > 0
```

不再靠 request 内容或人工猜测是否有图。

### go-tool-runtime

commit：`9d0c5e760f5512f4fdde9155a872cbf8d1366b4b`

新增：

`docs/operator-capabilities/0002_presentation.openmaic_ZH.md`

内容明确说明模型何时使用、owning repo/workflow、canonical inputs、第一阶段与第二阶段验收、receipt 字段、失败 evidence。

commit：`cb27fab91e5370fb0cdaffc6ed6ba62635c32488`

更新 `capabilities.d/openmaic-presentation.yaml`，让模型查询 capability 本身即可发现 0002 guide 与 `media_count` 阶段规则。

## 5. 当前真实停点

现在知识链已经可以形成：

```text
OpenWorker 0002-025
→ allowed_action=presentation.openmaic
→ go-tool capability
→ owning repo=openmaic-fork
→ workflow=operator-presentation-generate.yml
→ execution=local_action
→ workspace/host/request/output inputs
→ media_count=0 第一阶段验收
```

下一步必须是真实派送 owning repo 的本机 Action，在 ODA 上生成第一版无配图 storyboard PPTX。

本轮所用 ChatGPT GitHub Connector 当前没有暴露 `workflow_dispatch` 写操作，因此本文件不把“修改 workflow / 提交代码”冒充 REAL Action 执行，也不创建案例专用 push workflow 绕过模型使用正式本机 Action的要求。

## 6. 下一步 REAL 验收

实际 Action 跑完必须取得：

- Action run id
- runner / `COMPUTERNAME=DESKTOP-ODAQN0D`
- normalized inputs
- `presentation/storyboard.pptx`
- manifest
- `slide_count > 0`
- PPTX SHA256
- reopen success
- `media_count == 0`

全部成立才可 PASS `0002-025`，然后 OpenWorker canonical next step 必须是 `0002-027`，等待用户审核，不得进入 ComfyX IMAGE。
