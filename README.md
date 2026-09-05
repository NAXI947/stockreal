# StockReal R3.5

当前交付：服务器 Docker 阶段 0 开发/验证工具；完整业务应用尚未实现和上线。

开发服务器：`36.134.112.19`，仓库：`/root/stockreal`；本地镜像：`D:\python\stockreal`。直接使用 `main`。
基础镜像按 SHA256 固定。没有安装 Redis、PostgreSQL，没有创建业务监听端口。

在服务器仓库目录执行：

```sh
docker compose run --rm dev
docker compose run --rm dev python -m stockreal.stage0 import
docker compose run --rm dev python -m stockreal.stage0 probe
```

第一条执行离线测试；第二条导入 117 条脱敏候选契约；第三条手动请求 11 个端点，各一次，间隔 1 秒，不自动重试。
probe 是付费接口的手动诊断工具，重复运行会产生新的接口请求；不是生产调度器。

敏感源文件放在 `.secrets/catalog-source.json` 和 `.secrets/credential-source.json`。
导入器产生 `.secrets/runtime-profiles.json`（600 权限），后续探测只使用此配置档。
凭据绑定同一端点 host/path/action/route，不跨 URL 拼接凭据，拒绝非 HTTPS、未允许主机、重定向及未替换占位符。
`contracts/endpoints.json` 不含凭据值；契约状态全部 `UNVERIFIED`。
样本和每次检查报告写入 `data/stage0/<时间>/`，摘要为 `data/stage0/latest.json`。
这两个敏感/运行目录都不提交 Git；开发容器会访问挂载目录，仅在可信服务器运行。

手动探测沿用文档样例的股票、日期和其他参数，仅把 DOC-013 的 st 固定为 100。
因此探测不代表当日实时数据，更不代表持仓已配置。HTTP 200、JSON 可解析、业务成功及字段契约通过是不同判断。
不推断金额/成交量单位，不用接收时间代替源时间，不自动将字段升级为 CONTRACT_PASS。

用户已明确：没有人工核对的日历，先关闭自动采集。当前不存在自动采集进程、调度任务、方向性信号或 QQ 推送。
后续业务开发以 `docs/source/` 下五份 R3.5 文档为输入；历史 R3.1 Agent/AGUDATA 评估不作为当前接口基线。
阶段 0 尚需交易时段/空值/异常样本、字段单位和时间语义验证、日历以及批量广度证据；完整一期还需业务实现和连续 10 个交易日验收。

详见 [阶段 0 现状与缺口](docs/stage0/status.md)。

开发进度入口：[PROGRESS](docs/PROGRESS.md)，逐项完成记录：[CHANGELOG](docs/CHANGELOG.md)。
每轮在服务器执行 `docker compose run --rm dev python -m stockreal.design_guard` 检查设计输入未偏移；`docker compose run --rm dev python -m stockreal.replay` 离线重放固定样本，不请求上游。

运行禁用状态：`docker compose run --rm dev python -m stockreal.runtime_gate`。当前固定阶段0诊断，自动采集与方向性输出始终关闭。
未来日历文件为config/trade_calendar.csv，列date,is_open，ISO日期及0/1，每天一行，覆盖当前与下一年度；核对后的文件SHA256记录到策略文件。仅文件存在不能代表人工核对，也不能自动启动采集；需用户明确启用并完成生产前置条件后再开发调度接线。

诊断审计入库：`docker compose run --rm dev python -m stockreal.audit_store`，目标data/stockreal.db。此命令离线写入117条契约摘要和11条质量诊断，不采集行情、不生成或推送信号。重复同一报告不重复写批次或质量事件。数据库版本3包含endpoint_contract/job_run/data_quality_event及api_daily_budget，Signal/Outbox属于下一存储切片。

本轮进度：P1-02a/b/c离线实现完成，P1-02d真实HTTP接线及稳定性尚未完成。

- SQLite连接、迁移、查询、事务、回滚和关闭在同一个专用线程执行，仍由单写入协程顺序提交；不增加服务或数据库。
- api_daily_budget按Asia/Shanghai日期，在发请求前预占调用额度；普通请求60000、预留20000、硬上限80000；缓存命中不扣额，重试逐次计额，失败/取消不退额（保守计数）。历史日期记录不因重启或日期切换被清零。
- gateway_core只接收注入的传输函数，当前仓库没有其真实HTTP适配器或自动执行循环。测试使用模拟响应，生产可用标志始终false。
- 内部保守初值：host与endpoint并发2、软令牌桶4次/秒突发2、首轮/重试抖动0~0.25秒、最多2次重试。来源没有冻结的频率值须在P1-02d观测后配置化，不把这些初值当成供应商限制。
- Retry-After超过60秒时返回RETRY_DEFERRED，不提前重试；实际延迟队列、暂停恢复和跨重启请求去重由P1-02d接线验收。
- 缓存按端点、主机、账号配置引用、契约版本、参数、时段和策略隔离；源时间缺失不能由接收时间替换；过期或失败回退标STALE。
- `docker compose run --rm dev python -m stockreal.schedule_plan`只查看任务提案，不调用上游。窗口reset_token用于未来执行器按时段重置，盘后once_key用于未来执行器去重，本轮不宣称其已常驻执行。

时段计划的股票代码校验仅为语法/容量校验，证券真实性仍需instrument_master契约；没有为用户虚构持仓。
当前默认日历缺失且用户禁用自动采集，输出空任务列表。后续方向性业务开发仍需阶段0通过。


当前已部署六页个人诊断工作台，含持仓配置编辑。通过SSH隧道访问本机 http://127.0.0.1:18080 ，启动与备份说明见 [部署操作](docs/stage0/deployment.md)。默认持仓为空，没有自动行情任务。SQLite v3新增holdings_revision，记录完整配置修订和乐观并发版本。

有限字段补测工具：docker compose run --rm dev python -m stockreal.contract_evidence --manual。最多7次真实请求，使用受限游标/日期覆盖并预占持久预算，不属于自动采集。原stage0 probe仍是旧手动工具，尚未接入预算，不建议重复运行；后续手动补证据优先使用受限工具。

当前107项Docker测试通过，字段契约通过数仍为0。板块广度按R3.5明确降级，不将完整分页等同于字段语义或原子截面通过。

离线字段审阅：docker compose run --rm dev python -m stockreal.contract_review。校验已有样本哈希并定位结构差异，不请求行情。带来源哈希的注释映射保存在contracts/field-candidates.json，全部为未验证候选。
