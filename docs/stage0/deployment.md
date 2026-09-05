# StockReal 诊断工作台部署与操作

当前是个人诊断与持仓配置工作台，行情自动采集和方向性提示均关闭。服务器工作根 /root/stockreal。六页完整业务能力仍按 PROGRESS.md 的主任务验收。

## 服务与访问

服务器执行（实际进程始终在Docker内）：

    cd /root/stockreal
    docker compose up -d dashboard
    docker compose ps
    docker compose restart dashboard

仅监听服务器127.0.0.1:18080。在本机PowerShell启动SSH隧道：

    ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:18080:127.0.0.1:18080 root@36.134.112.19

然后访问 http://127.0.0.1:18080 。本轮已在本机后台启动同等隧道；不要重复占用该端口。隧道断开不影响服务器容器运行，重新连接即可。当前不需要云控制台开放18080。不要把Compose映射改成0.0.0.0：当前访问边界是SSH，应用尚未提供公网单用户登录/TLS。

页面“刷新本机状态”只读本地SQLite和诊断摘要，不请求行情接口；持仓“保存”仅提交个人配置。最多20只，代码格式六位.SH/SZ/BJ，参考成本可留空，观察级别为个人标签。版本冲突会保留草稿，需放弃草稿后重读并合并；不静默覆盖另一页面或终端的更改。代码格式合法不代表证券资料已验证。

应用不挂载.secrets，不输出上游URL或凭据。路径白名单、Host限制、同源写入头和Origin检查是私有访问补充，不作为公网认证替代。

## 验证和备份

    docker compose run --rm dev python -m unittest discover -s tests -q
    docker compose run --rm dev python -m stockreal.design_guard
    docker compose run --rm dev python -m stockreal.backup create

最后一条在data/backups生成权限600的SQLite一致快照与manifest，并自动在临时目录恢复副本，核对哈希、quick_check、foreign_key_check、表行数、预算与配置修订。运行库不会被覆盖。已有备份不会重写，当前不自动清理历史备份。

复验指定备份：

    docker compose run --rm dev python -m stockreal.backup verify --file /workspace/data/backups/stockreal-20260905T162933534691.db

备份只覆盖SQLite；配置、设计文件由Git工作区保存，未提交改动需单独保留。.secrets仅保留在服务器，由所有者另行安全备份，不写入Git或网页。当前工具没有生产库覆盖恢复命令；出现故障先保留现有数据库/WAL及配置，使用隔离副本验证后再制定具体切换步骤。

## 当前验收边界

- 容器健康检查200只代表工作台状态接口可读取，不代表行情契约通过。
- 手动补测7次计入本地预算；之前11次首轮诊断没有追加入本地预算，页面明确标注“已接入预算账本的请求”。供应商余额未知。
- 075/081新增样本和041部分分页结构差异仍未冻结。四个板块广度/热度/背离指标为空。
- 周末手动样本不能证明盘中时效、五日成功率或十交易日验收。日历暂无人工核对，自动采集持续关闭。
