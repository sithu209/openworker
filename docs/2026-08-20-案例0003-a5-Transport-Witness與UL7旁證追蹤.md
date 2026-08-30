# 案例0003 — a5 Transport Witness 與 UL7 旁證追蹤

- 日期：2026-08-20（Asia/Taipei）
- Case：0003 / 玉井橋 / YUJING BRIDGE
- 固定機：DESKTOP-UL7V2VV
- runner label：UL7
- workspace：D:\AI-Work\jobs\0003-YUJING-BRIDGE
- 密語：CASE0003.ORTHOPHOTO.CONTINUE
- current request：case0003-orthophoto-20260820-a5

## 1. 已有 REAL authority
request a2 已取得 DirectWork durable evidence：work_id=dw-20260820T072026-2b13548d00bf965a；accepted PASS；claimed PASS（slot=4 / DESKTOP-UL7V2VV）；running PASS（pid=21080）；terminal failed；exit_code=1。因此歷史上已證明 GitHub short transport → UL7 → DirectWork /v1/work → durable queue → claim → slot → executor 真實成立，a2 不可描述為 DirectWork 沒接案。

## 2. a3 / a4 / a5 transport 缺口
a3 已部署 self-diagnosing payload，但 a3 receipt 未觀察到；a4 retrigger 亦無 receipt。a5 新增 UL7 transport witness，commit 5dec37d5a5836c3409d60dd4b2b9d110bce1d6c4；witness 與 a5 business receipt多次 fresh recheck 均未觀察到。因此 GAP-0003-TRANSPORT-01 仍 OPEN，但現在不再猜 business root cause。

## 3. O87 fresh authority
2026-08-20 15:42（Asia/Taipei），Case0006 O87 remote-admission receipt commit 241b58b0cc4d340da6eaf1e1e335564204546085 證明 O87 self-hosted runner仍可消費新 job，且能跨機 POST durable work 到 ODA DirectWork：work_id=dw-20260820T074210-48814d97fcd6d9ee，accepted→claimed(slot4)→running(pid2824)→succeeded，exit0。因此不是所有 self-hosted runners 都掛。

## 4. O87→UL7 LAN service probe：UL7 DirectWork FRESH ONLINE
Case0003 O87 probe receipt：diagnostics/case0003/case0003-o87-probe-ul7-services-20260820-r01.json，GitHub run id 32346394659。

Fresh evidence（15:57 +08）：observer runner DESKTOP-O87PJNR-R001；UL7 DNS=100.78.110.79；http://DESKTOP-UL7V2VV:8787/v1/node/status 回 HTTP200，內容明確為 online=true、max_workers=4、free_workers=4、busy_workers=0、queued_works=0、upgrade_verified=true，commit/target_commit=ec38bdd3b2cbd90089e1ad1fe9f4269b3ee12c32。UL7 同時觀察到 ODA peer online（64ms）與 O87 peer online（56ms）。

8787/health 回404僅表示 route不存在；/v1/node/status 已提供 positive authority。遠端 8848 /health 與 /api/information/runners/current 回401，代表 LAN request 到達但需要授權，不能當 service offline。

結論：已排除 UL7 主機斷線、UL7 DirectWork offline、worker 滿載與 queue 堵塞。

## 5. GAP-0003-TRANSPORT-01 scope 已收斂
UL7 host + DirectWork fresh online，但 Case0003 UL7 GitHub transport witness不出現，所以最可疑層已收斂為：UL7 GitHub self-hosted runner listener/service、repo registration、label assignment 或 job routing。此時不得清 DirectWork queue（queued_works=0），也不得修改 Terrain_To_DXF producer。

## 6. 直接繞過 UL7 GitHub runner 做本機 runner-service diagnostic
為避免故障中的 UL7 GitHub listener 自證，已由 O87 使用 UL7 DirectWork /v1/work 投遞本機 infrastructure diagnostic。

request：case0003-ul7-runner-service-diagnose-20260820-r01
master atomic commit：ed91f74e2090cccbd09bf8628fb114c4b784bd1a

Fresh durable receipt 已回：

- work_id=dw-20260820T080044-6c5b5ca111f88506
- target machine=DESKTOP-UL7V2VV
- accepted seq37
- claimed seq38 / slot=1
- running seq39 / pid=32476
- succeeded seq40
- exit_code=0
- artifact=D:\AI-Work\jobs\0003-YUJING-BRIDGE\evidence\case0003-ul7-runner-service-diagnose.json
- artifact size=36242 bytes
- SHA256=a198be91fca748da8cd6391d3726b6697274ccbc456871d61139c53ca7c9346c

所以 UL7 DirectWork 不只 health online，還能 fresh 接受並執行新的 durable infrastructure work。

該 artifact 包含 Win32_Service actions.runner.*、service state/start mode/account/PID/path、runner dirs、Runner.Listener.exe/.runner config 與 executor identity。因 DirectWork artifacts listing只回 metadata，已再部署 O87 artifact-fetch workflow，把該 JSON 內容經 UL7 DirectWork artifact HTTP endpoint回寫：diagnostics/case0003/case0003-ul7-runner-service-diagnose-content-r01.json。部署 branch fast-forward commit 96a19b5acd6a176f3494e1ae83898e6a6c232227；截至本段更新內容 receipt尚未觀察到。

## 7. go-tool 8848 負面知識
127.0.0.1:8848 是 per-machine local-work queue-only profile；codebase/git/knowledge/actions disabled允許且預期。不得再把 /tools disabled 當完整 query runtime故障。遠端8848回401只代表需要授權。

## 8. 最新 acceptance matrix
```text
a2 DirectWork ingress                 PASS
a2 durable queue                      PASS
a2 claim / slot                       PASS (slot 4)
a2 executor                           PASS (pid 21080)
a2 business                           FAIL (exit 1)
a3/a4/a5 GitHub transport receipts    NOT OBSERVED
O87 self-hosted runner                FRESH PASS
O87→UL7 DNS                            PASS (100.78.110.79)
UL7 DirectWork node status             PASS / online=true
UL7 workers                            4 free / 0 busy
UL7 queued works                       0
UL7 peers ODA/O87                      ONLINE
UL7 durable runner diagnostic          PASS
UL7 diagnostic work_id                dw-20260820T080044-6c5b5ca111f88506
UL7 diagnostic artifact               PASS 36242 bytes / SHA256 recorded
UL7 GitHub runner listener             SUSPECT / DETAILS FETCHING
Fresh orthophoto                       NOT PROVEN
Drive publish                          NOT STARTED
ChatGPT exact-image visual QA          NOT STARTED
```

## 9. 下一步 gate
優先讀 case0003-ul7-runner-service-diagnose-content-r01.json。若 DirectWork-specific UL7 GitHub runner service stopped，啟動該 service；若 running，核對 .runner repo binding、runner name/labels、listener PID；只修精確服務，不無差別重裝。修好後發 a6 request驗 transport witness，然後才恢復正射 business chain。
