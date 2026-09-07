# 文档总览

本目录定义 STOCK-ANALYSIS 的研究标准、数据口径、报告结构和实施路线。它是项目当前阶段的主要交付物。

## 推荐阅读顺序

1. [研究方法](methodology.md)：了解从问题定义到复盘的完整流程。
2. [数据与指标](data-and-metrics.md)：统一数据时间边界、来源优先级与计算口径。
3. [报告模板](report-template.md)：按固定结构创建单只股票研究报告。
4. [风险与合规](risk-and-disclaimer.md)：理解模型、数据与投资决策的限制。
5. [实施路线图](roadmap.md)：查看后续代码化、测试和自动化计划。

## 文档约定

- “事实”必须能追溯到原始来源。
- “计算”必须给出输入、公式和单位。
- “假设”必须可调整，不能伪装成已知事实。
- “观点”必须说明成立条件和反证条件。
- “最新”必须附具体日期和时区。
- 缺失值保留为空或标记为未知，不默认填零。
- 对不同市场、币种、会计准则的数据比较前先完成标准化。

## 建议目录结构

```text
.
├── README.md
├── docs/
│   ├── README.md
│   ├── methodology.md
│   ├── data-and-metrics.md
│   ├── report-template.md
│   ├── risk-and-disclaimer.md
│   └── roadmap.md
├── src/stock_analysis/  # 可复用代码（配置、模型、指标、数据层、分析引擎、复盘、CLI）
├── tests/               # 单元测试与边界测试
├── data/                # raw / normalized / derived / output 分层
├── reports/             # 按日期保存研究报告
├── scripts/             # 数据生成等辅助脚本
├── pyproject.toml       # 包配置与测试配置
└── .github/workflows/   # CI
```

## 版本原则

重大方法变化应说明：

- 变更内容；
- 变更原因；
- 对历史报告可比性的影响；
- 是否需要重新计算已有结果。

返回 [项目首页](../README.md)。
