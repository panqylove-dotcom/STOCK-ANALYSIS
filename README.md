# STOCK-ANALYSIS

一个面向个人投资研究的、可复核的股票分析文档框架。

本仓库当前采用 **documentation-first（文档先行）** 方式建设：先统一研究流程、指标口径、风险规则和报告模板，再逐步接入行情、财务数据与自动化分析代码。仓库不提供自动交易服务，也不构成投资建议。

## 项目目标

STOCK-ANALYSIS 希望把一次股票研究拆成可重复、可审计的流程：

1. 明确研究问题与时间边界；
2. 收集公司、行业、财务、估值和市场数据；
3. 区分原始事实、计算结果、假设和主观判断；
4. 从基本面、估值、技术面、催化剂与风险五个维度形成结论；
5. 给出可验证的观察条件，而不是只给出“买入/卖出”标签；
6. 定期复盘结论与实际结果，持续修正研究方法。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [文档总览](docs/README.md) | 阅读路径与文档地图 |
| [研究方法](docs/methodology.md) | 标准分析流程、证据要求与评分原则 |
| [数据与指标](docs/data-and-metrics.md) | 数据来源、时间边界、常用指标与计算口径 |
| [报告模板](docs/report-template.md) | 单只股票研究报告的可复用 Markdown 模板 |
| [风险与合规](docs/risk-and-disclaimer.md) | 风险控制、局限性和免责声明 |
| [实施路线图](docs/roadmap.md) | 从文档框架到可运行工具的分阶段计划 |

## 标准研究输出

每份分析至少应包含：

- 标的、市场、币种、分析日期和数据截止时间；
- 一句话投资命题；
- 商业模式与收入驱动因素；
- 关键财务趋势及其来源；
- 相对估值或内在价值区间，并公开假设；
- 趋势、波动与流动性观察；
- 正向催化剂、核心风险和反证条件；
- 基准、中性与悲观情景；
- 后续跟踪指标和复盘日期；
- 数据缺口与结论置信度。

## 基本原则

- **时点一致**：只使用分析时点已经公开的信息，避免前视偏差。
- **来源可追溯**：关键事实应附来源、发布日期和访问日期。
- **口径一致**：同比、环比、TTM、GAAP/非 GAAP 等必须标明。
- **事实与观点分离**：引用数据、计算结果、假设和判断分别表达。
- **风险优先**：先确定可能损失和结论失效条件，再讨论潜在收益。
- **结果可复核**：所有衍生指标都应能根据公开公式重新计算。
- **不过度承诺**：数据缺失时明确说明，不用估计值冒充事实。

## 建议工作流

```text
定义问题
  ↓
确定时间与数据边界
  ↓
收集并验证证据
  ↓
计算指标与估值
  ↓
建立多情景假设
  ↓
形成结论、风险与观察条件
  ↓
按计划复盘
```

使用 [报告模板](docs/report-template.md) 新建分析时，建议把文件放在未来的 `reports/` 目录，并采用：

```text
reports/YYYY-MM-DD-MARKET-TICKER.md
```

示例：`reports/2026-09-03-NASDAQ-AAPL.md`。

## 当前状态

当前版本完成了项目文档体系和研究规范，并进入阶段 1（仓库工程化）：

- 建立了 `src/`、`tests/`、`data/`、`reports/` 目录与可安装的 Python 包（`stock-analysis`）；
- 提供了统一配置（`src/stock_analysis/config.py`）与计算版本策略；
- 实现了与 `docs/data-and-metrics.md` 口径一致的派生指标计算（收益率、波动、回撤、同比、CAGR、利润率、FCF、净负债、P/E、Sharpe 等）及离线 CLI；
- 内置确定性示例数据（`data/raw/sample_prices.csv`），测试完全离线可运行；
- 配置了 GitHub Actions CI（Python 3.10–3.12）与 MIT 许可证。

数据层（阶段 2 起步）：

- `src/stock_analysis/data/`：CSV 加载器（含来源记录）、数据清洗（校验/去重/缺失值前向填充）、数据质量与新鲜度检查；
- CLI 现在按「加载 → 校验 → 质量检查 → 计算指标」流程运行，质量不合格时返回非零退出码。

分析引擎（阶段 3）：

- `src/stock_analysis/analysis.py`：财务趋势（同比/CAGR）、DCF 多情景估值与敏感性分析、Beta/Alpha/相对收益、催化剂与风险清单、结构化 Markdown/JSON 报告；
- CLI 子命令：`stock-analysis stats <csv>`（市场指标）与 `stock-analysis report <csv>`（生成报告，`--format json` 输出 JSON）。

报告与复盘（阶段 4）：

- `src/stock_analysis/review.py`：报告快照保存/恢复、财报更新前后差异比较、观察条件、复盘日志与偏差统计（平均偏差/平均绝对偏差/命中率）；
- CLI 子命令：`stock-analysis diff <before.json> <after.json>`（财报差异）、`stock-analysis review <log.json>`（复盘摘要）、`stock-analysis report <csv> --save <path>`（保存快照）。

扩展能力（阶段 5）：

- `src/stock_analysis/markets.py`：多市场注册表（按市场设置年交易日数与时区）、带来源记录的汇率换算；
- `src/stock_analysis/industry.py`：行业专用指标插件框架（内置 software/bank/retail/semiconductor/insurance/generic）；
- `src/stock_analysis/portfolio.py`：组合权重、HHI 集中度、有效持仓数、最大单一暴露、Pearson 相关系数矩阵；
- `src/stock_analysis/dashboard.py`：只读静态 HTML 仪表盘（无 JavaScript、无交易功能）；
- `src/stock_analysis/audit.py`：JSONL 审计日志与数据许可检查（再分发/分析动作控制）；
- `src/stock_analysis/models.py`：`FinancialMetric` 增加 `standard` 字段登记会计准则（如 CAS/IFRS/US GAAP）；`analysis.py` 提供 `assert_same_standards` / `assert_same_currencies`，在比较类计算前拦截会计准则或币种混用（CLI 违例退出码 4）；
- CLI 子命令：
  - `stock-analysis dashboard <snapshot.json>... --out dashboard.html`；
  - `stock-analysis portfolio <portfolio.json>`：组合暴露与相关性分析（要求单币种，示例见 `data/portfolio_sample.json`）；
  - `stock-analysis stats/report ... --audit <path.jsonl>`：将本次 analyze 动作追加写入审计 JSONL，数据许可不允许时拒绝并以退出码 4 结束。

在线行情源（阶段 2 补完）：

- `src/stock_analysis/data/fetchers.py`：akshare A 股日线适配器（可选依赖 `pip install "stock-analysis[akshare]"`，默认前复权，含重试与指数退避、来源与许可登记）；
- CLI 子命令：`stock-analysis fetch 600000 --start YYYY-MM-DD --end YYYY-MM-DD --out data/raw/x.csv`；

法定披露来源（阶段 2 收尾）：

- `src/stock_analysis/data/disclosures.py`：A 股法定披露适配器，覆盖巨潮资讯（cninfo，证监会指定披露平台）、上交所（sse）、深交所（szse）公告检索；零第三方依赖（标准库 urllib），全部网络调用可注入 mock，测试完全离线；
- 本地核验登记：`register_local_disclosure` 对手动下载的公告文件计算 SHA-256 并追加到 JSONL 索引（`data/disclosures/` 为运行产物，不入库）；
- CLI 子命令：
  - `stock-analysis disclose list 600000 --source cninfo|sse|szse --start YYYY-MM-DD --end YYYY-MM-DD`（公告元数据检索）；
  - `stock-analysis disclose register 公告.pdf --ticker 600000 --title "..." --disclosed-on YYYY-MM-DD`（本地核验登记）；
  - `stock-analysis disclose check 600000 --source cninfo|sse|szse [--index PATH] [--days 30] [--today YYYY-MM-DD]`（增量检查：以索引内该标的最新披露日期为基线列出新公告；索引无记录时回看最近 N 天。只读，新公告需人工核验后用 register 登记）；
- 接口为 best-effort 适配：官方页面/接口可能变更；第三方与检索数据不能替代公告原文人工核验。

用户增强功能（研究闭环补强）：

- `src/stock_analysis/financials.py`：财务工作簿 JSON 约定格式（`data/financials/<TICKER>.json`，含币种/来源/报告期格式校验与年报缺口提示），示例见 `data/financials/SAMPLE.json`；
- `src/stock_analysis/watchlist.py`：从报告快照与复盘日志聚合观察条件，生成只读跟踪清单；
- CLI 子命令：
  - `stock-analysis report <csv> --financials <path>`：用财务工作簿自动填充报告的财务趋势（币种不一致时拒绝并退出码 1）；
  - `stock-analysis report <csv> --observe "描述|触发判据|阈值"`（可多次）：随报告快照持久化观察条件；
  - `stock-analysis watch <snapshot.json>... [--review-log log.json] [--stale-days 90] [--today YYYY-MM-DD]`：观察条件跟踪清单，长期未复盘的「待观察」项标注建议复盘；
  - `stock-analysis review summary <log.json>`：复盘摘要（旧用法 `review <log.json>` 保持兼容）；
  - `stock-analysis review add <log.json> --ticker ... --review-date YYYY-MM-DD [--obs "描述|判据|阈值"] [--predicted X --actual X] [--thesis ...] [--note ...]`：追加一条复盘记录（日志不存在则创建）。

运行方式：

```bash
pip install -e ".[dev]"
python -m pytest
python -m stock_analysis.cli stats data/raw/sample_prices.csv --ticker SAMPLE
python -m stock_analysis.cli report data/raw/sample_prices.csv --ticker SAMPLE
python -m stock_analysis.cli review data/review_sample.json
python -m stock_analysis.cli portfolio data/portfolio_sample.json
python -m stock_analysis.cli report data/raw/sample_prices.csv --ticker SAMPLE --financials data/financials/SAMPLE.json
python -m stock_analysis.cli watch reports/snapshot.json --review-log data/review_sample.json
python -m stock_analysis.cli disclose check 600000 --source cninfo
python -m stock_analysis.cli disclose list 600000 --source cninfo --start 2026-08-01 --end 2026-09-05
```

尚未包含真实行情采集、财务数据接入、回测或交易模块。后续实现计划见 [路线图](docs/roadmap.md)。

## 免责声明

本仓库仅用于教育、研究和信息整理，不构成投资建议、证券推荐、收益承诺或任何形式的招揽。金融市场存在本金损失风险；使用者应独立核实数据并根据自身情况作出决定。完整说明见 [风险与合规](docs/risk-and-disclaimer.md)。

## License

本项目采用 [MIT License](LICENSE)。
