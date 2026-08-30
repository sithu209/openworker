# Case 0003 玉井橋 — 空 Drive Revision 與 Fresh Review Gate 修復

日期：2026-08-18（Asia/Taipei）

Case：`0003` / 玉井橋

固定機器：`DESKTOP-UL7V2VV` / `UL7`

固定工作目錄：`D:\AI-Work\jobs\0003-YUJING-BRIDGE`

## 1. 本批發現的新缺口

Google Drive 出現新 revision：

```text
OpenWorker-Case-0003-rev_6e6e40bd0c53
folder id = 1ZA2IDh5zGzrwgYxhhHaaGFK1b6Lx2-y8
```

但 connector 實際打開後確認：

```text
review-bundle/  -> 空
 evidence/      -> 空
```

因此「revision folder 已建立」不能視為 publication 成功，更不能進入 ChatGPT visual review。

本案例新增 fail-closed 原則：

> Drive revision 必須含非空 immutable review bundle 與 review artifacts；空資料夾只能算 transport skeleton，不得推進 WorkLedger review gate。

## 2. 舊 fresh-review gate 已過時

舊 workflow：

```text
.github/workflows/case-0003-fresh-review-revision-ul7.yml
```

硬編碼：

```text
CASE0003_EXPECTED_SCENEX_SHA = f193a008d143c6b210f2051d3f1dc16304eb282ce5e62cdad7ed670f19845a3d
```

這個 SHA 早於後續 SceneX semantic visibility + clockwise winding 修復，不能再作為 current repaired SceneX authority。

## 3. 新 fresh-review gate

修復 commit：

```text
aba028be60c35dada197a82c4789697d74ed67d6
fix(case0003): bind fresh review to current SceneX evidence and launcher
```

隨後依 review transport / BAT physical acceptance 分離原則整理為：

```text
1cfc93e144ddf36c9a6a67df1056bf98b7349762
fix(case0003): separate Drive visual review from BAT physical acceptance
```

現在 fresh-review 不再信任硬編碼 SceneX SHA，而是要求 UL7 當前實體成果：

```text
scenex\terrain-browse.png
scenex\terrain-browse-evidence.json
scenex\scenex-workspace.json
Open-Case0003-SceneX.bat
scenex\scenex-launcher-evidence.json
```

並 fail-closed 驗證：

```text
terrain-browse-evidence.ok == true
active_chunk_count > 0
terrain_geometry_count > 0
actual screenshot SHA == scenex-workspace.json screenshot.sha256
launcher evidence check_only == PASS
actual BAT SHA == launcher evidence launcher.sha256
```

只有全部通過，才允許呼叫 `case0003_review_handoff.py` 建立新的 immutable review revision。

## 4. Fresh review bundle 必須為 current exact output

新的 workflow 會要求 bundle 至少包含非空：

```text
manifest.json
manifest.sha256
review-request.json
artifacts\scenex-browse.png
artifacts\scenex-evidence.json
artifacts\blender-render.png
artifacts\delivery-index.html
artifacts\mechanical-acceptance.json
```

而且：

```text
workspace current scenex\terrain-browse.png SHA
==
review bundle artifacts\scenex-browse.png SHA
```

不相等就 fail closed。

## 5. BAT 與 Drive review 的責任分離

BAT 是 Case 0003 最後的本機人工作品驗收成果：

```text
D:\AI-Work\jobs\0003-YUJING-BRIDGE\Open-Case0003-SceneX.bat
```

它必須實體存在於 UL7 workspace 並通過：

```text
Open-Case0003-SceneX.bat --check-only
CASE0003_SCENEX_LAUNCHER_CHECK_PASS
```

Drive review 的核心責任則是 multimodal visual/semantic review。

因此最終 CLOSED 條件為兩條 gate 同時成立：

```text
A. Drive exact revision -> ChatGPT visual review PASS -> WorkLedger PASS -> Delivery Revision PASS
B. UL7 physical BAT exists -> BAT check-only PASS -> real SceneX project + exact Case0003 Region Pack 可打開
```

任一條缺失，都不得稱 Case 0003 CLOSED。

## 6. 目前狀態

```text
DTM / AOI              PASS，保持不動
Blender                 REAL visible PASS，保持不動
SceneX semantic repair  已進 master
SceneX winding repair   已進 master
SceneX fresh REAL rerun 已觸發
BAT launcher workflow   已建立
舊 rev_0851...          TOOL_GAP historical evidence
rev_6e6e40bd0c53        EMPTY TRANSPORT SKELETON，不可審查
fresh-review gate       已升級，不再綁舊 SHA
下一步                 等待/取得由新 gate 建出的非空 exact revision，實際看 SceneX 新 PNG
```

## 7. 後續操作規則

1. 不重跑 DTM / AOI / Blender。
2. 不再審 `rev_0851...`。
3. 不把 `rev_6e6...` 空資料夾當成功 publication。
4. 下一個 revision 必須是 current SceneX exact output。
5. ChatGPT 必須實際看新 PNG 才能 PASS。
6. PASS 後才能 apply WorkLedger review receipt 與建立 Delivery Revision。
7. 最後必須在 UL7 雙擊 `Open-Case0003-SceneX.bat` 可進真正 SceneX 看成果。
