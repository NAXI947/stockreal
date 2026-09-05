# StockReal 工作约束

- 单用户个人项目，使用现有 main，不创建分支或 worktree。
- 实际开发执行、测试和部署均在 36.134.112.19 的 Docker 内进行，工作根 /root/stockreal。
- 本地 D:\python\stockreal 为同一 Git 仓库。同步前检查双方改动，禁止覆盖未知更改。
- R3.5 五份文档为当前输入；旧 tmp/ 下 R3.1 评估仅为历史材料。
- 凭据不得输出日志、进入 Git 或前端；.secrets 为服务器专用运行配置。
- 用户确认暂无人工核对的交易日历，自动采集保持关闭，不能自行启用。
- 阶段 0 字段契约未通过前不启用生产方向性提示。HTTP 200 不等于 CONTRACT_PASS。
- 服务端口需分别检查 Linux 监听/防火墙和云控制台放行；遇到外部阻塞及时反馈。
- 不建设多租户、微服务、Redis、PostgreSQL、自动交易、AI 问股或二三期功能。

- 每轮开发先读 docs/PROGRESS.md，开工标记进行中；每完成一项立即更新该表及 docs/CHANGELOG.md，附设计依据、测试命令、结果和遗留项。
- 设计输入哈希记录在 docs/design-baseline.json；修改设计或一期范围须记录并反馈，不以测试通过替代外部验收。
