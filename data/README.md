# 数据目录

按 `docs/data-and-metrics.md` 的数据分层保存：

```text
data/
├── raw/        # 来源原样数据，不覆盖、不手工改写
├── normalized/ # 统一日期、币种、单位、复权和字段名称
├── derived/    # 由明确公式计算的指标
└── output/     # 图表、表格和报告
```

当前包含确定性生成的示例数据（`raw/sample_prices.csv`），由
`scripts/generate_sample_data.py` 生成，可复现且不依赖在线服务。

示例数据用于：

- CLI 离线演示（`python -m stock_analysis.cli data/raw/sample_prices.csv --ticker SAMPLE`）；
- 数据加载器、清洗与质量检查的单元测试。

注意：示例数据为合成行情，日期到 2026-12-17，不代表任何真实标的；
质量检查中的"数据新鲜度"项对示例数据会显示滞后，属预期现象。

`review_sample.json` 为示例复盘日志（2 条预测记录），可用于演示
`python -m stock_analysis.cli review data/review_sample.json`。

真实数据来源优先级与质量检查见 `docs/data-and-metrics.md`。

