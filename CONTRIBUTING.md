# 贡献指南

## 行为准则

- 所有关键数字、日期、引用与结论都必须能追溯到原始来源。
- 不提交密钥、账户数据、未公开重大信息或受许可限制的原始数据。
- 事实、计算、假设与观点分开表达，不把估计值冒充事实。

## 开发环境

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

## 测试

```bash
python -m pytest
```

测试必须离线可运行，不依赖在线行情或财务数据服务。

## 目录约定

- `docs/`：研究标准与口径变更，属受控文档；
- `src/stock_analysis/`：可复用代码；
- `tests/`：单元测试与边界测试；
- `data/`：raw / normalized / derived / output 分层；
- `reports/`：按模板生成的研究报告。

## 口径变更流程

任何改变派生指标计算方式的变更：

1. 同步更新 `docs/data-and-metrics.md`；
2. 递增 `src/stock_analysis/config.py` 中的 `CALCULATION_VERSION`；
3. 说明对历史报告可比性的影响，以及是否需要重算已有结果；
4. 为变化补充单元测试与边界测试。

## 提交信息

建议使用 Conventional Commits，例如：

```text
feat(metrics): add annualized volatility
fix(config): reject unknown fields
docs(roadmap): mark phase 1 items done
```

