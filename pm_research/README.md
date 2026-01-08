# Polymarket 研究型粗筛系统（read-only）

本项目提供一个 **只读研究与审计** 的数据管线：
- 拉取 Polymarket 公共数据（Gamma API / CLOB API）
- 本地落库（SQLite，Postgres-friendly schema）
- LLM 规则结构化（仅抽取规则结构，不输出下注建议）
- 计算摩擦与流动性指标
- 产出候选研究清单（供人工复核）

> 严格禁止：任何下单、签名、资金操作或“买YES/买NO”建议。

## 安装

```bash
cd pm_research
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

## 环境配置

复制并编辑 `.env.example`：

```bash
cp .env.example .env
```

必须配置 LLM 相关环境变量（OpenAI 兼容接口）：
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

## 典型运行顺序

```bash
pmr sync --active true --pages 5 --page-size 100
pmr enrich --prices --orderbooks --limit 500
pmr parse --llm --batch 100
pmr candidates --min-volume 20000 --max-spread 0.06 --output candidates.csv
```

## 常见问题

- **429 限流**：客户端实现了指数退避与速率限制，可适当调低并发或批大小。
- **分页**：Gamma API 使用 `limit/offset` 直到无数据。
- **字段缺失**：部分市场字段可能为空，落库时会保持 NULL/空字符串。
- **SQLite 文件膨胀**：订单簿仅存 top N（默认 20），如需全量可启用 gzip 归档到 `./archive/books/`。

## 运行测试

```bash
pytest -q
```
