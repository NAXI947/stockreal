# 2026-09-05 阶段 0 现状与缺口

## 入口判断

Observed：本地与服务器初始 HEAD 均为 367565c，均仅跟踪 .gitignore。远端无应用源码、数据库或容器；因此不存在待保护的旧业务实现。
Observed：Docker Compose v5.5.1，Linux x86_64，约 15 GiB 内存，系统盘约 105 GiB 可用。SSH 偶发握手关闭，重试可成功。
Observed：本地接口资产 117 条；凭据/资料已通过 SSH 复制到本用户指定的服务器，专用目录权限 700、凭据文件 600。
Inference：本次属于新建项目的实施前验证，不属于旧系统重构。wff-x 入口核查结束，未伪造 PhaseX 成功包或 WFF P1/P2 审批。
Route：R3.5 是外部需求/技术设计输入。当前阶段 0 工具按明确工程请求建设；如继续正式 WFF 生命周期，应先将 R3.5 输入送入 wff-req，不能宣称已有正式 P2/P3。

## 本次真实验证

所有代码生成、测试、导入和实时请求均在服务器 Python Docker 容器内执行。
117 条脱敏候选契约导入成功；8 个离线测试覆盖绑定、缺凭据、主机/传输限制、脱敏、重复 ID、变长行、HTTP 429。
2026-09-05 10:41 Asia/Shanghai 手动采集 11 个端点；这是周六的单次样本，沿用资产样例参数，不是交易时段验收。
以下延迟仅是单次观测，不是 P95 或稳定性结论。

| 端点 | HTTP | 传输观测 | 毫秒 | 字段契约 |
| --- | --- | --- | --- | --- |
| LHV-DOC-009 | 200 | JSON_RECEIVED | 199 | UNVERIFIED |
| LHV-DOC-008 | 200 | JSON_RECEIVED | 209 | UNVERIFIED |
| LHV-DOC-013 | 200 | JSON_RECEIVED | 199 | UNVERIFIED |
| LHV-DOC-075 | 200 | JSON_RECEIVED | 96 | UNVERIFIED |
| LHV-DOC-041 | 200 | JSON_RECEIVED | 189 | UNVERIFIED |
| LHV-DOC-081 | 200 | JSON_RECEIVED | 95 | UNVERIFIED |
| LHV-DOC-036 | 200 | JSON_RECEIVED | 157 | UNVERIFIED |
| LHV-DOC-038 | 200 | JSON_RECEIVED | 112 | UNVERIFIED |
| LHV-DOC-103 | 200 | JSON_RECEIVED | 93 | UNVERIFIED |
| LHV-DOC-108 | 200 | JSON_RECEIVED | 83 | UNVERIFIED |
| LHV-DOC-090 | 200 | JSON_RECEIVED | 85 | UNVERIFIED |

Observed：9 个 LongHuVIP 响应 errcode="0"；DOC-036/038 code=20000。未把不同端点的 code/status 统一解释为业务错误码。
Observed：DOC-075 dadanjinge=[]，DOC-081 List=[]；尚未证明是非交易日、样例日期、权限或其他原因造成。
Observed：DOC-041 返回 60 行、每行 19 列；只有当前页，不能宣称已取得完整板块宇宙或 N_up/N_valid 字段。
Observed：DOC-013 返回 32 行、每行 6 列；列数观测不等于单位、方向、时间和窗口完整性验证。
Unknown：DOC-075 的累计/区间语义、DOC-041 广度、各二维数组的完整列映射、时间字段语义、交易时段的缺失和异常行为。

## 保持关闭的能力

- 用户确认暂无日历：自动采集关闭。日历需要覆盖当前和下一年度并人工核对。
- CONTRACT_PASS=0：方向性提示关闭；市场/板块/候选公式未进入生产。
- QQ 未配置且本轮未发送消息。
- 未部署 Web 应用，因此本轮不需要控制台放行新端口，也不能宣称公网访问验收通过。

## 下一阶段验收输入

1. 对样例参数和日期进行显式契约化，补齐正常、空数据、异常和交易时段样本，验证单位/源时间/分页及 schema drift。
2. 确认批量板块广度；不足则按 R3.5 使 Breadth/Heat/Divergence 为 NULL，禁止逐板 DOC-046 补广度。
3. 冻结可用字段，补充调度预算、SQLite 单写入/Outbox、风控和信号回放测试，再开发一期业务与 Web。
4. 日历未核对前继续手动诊断；生产上线需要最近 5 个交易日成功率和连续 10 个交易日完整验收，当前尚不具备。

总体状态：开发容器和首批手动诊断完成；阶段 0 未验收；一期未实现、未上线。
