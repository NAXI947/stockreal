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

诊断审计入库：`docker compose run --rm dev python -m stockreal.audit_store`，目标data/stockreal.db。此命令离线写入117条契约摘要和11条质量诊断，不采集行情、不生成或推送信号。重复同一报告不重复写批次或质量事件。数据库版本1只包含endpoint_contract/job_run/data_quality_event，Signal/Outbox属于下一存储切片。
