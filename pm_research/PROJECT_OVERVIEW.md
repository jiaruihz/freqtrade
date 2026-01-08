# pm_research 项目概览与走读

> 目标：对 /home/rui/projects/pm_research 做完整走读，覆盖结构、入口、核心流程、数据模型与模块职责。

## 1. 项目定位与总体流程

这是一个 **Polymarket 只读研究/审计管线**，通过公开 API 拉取市场/事件（Gamma）与行情/订单簿（CLOB），落地 SQLite（结构兼容未来迁移至 PG 的设计），可选使用 LLM 抽取规则结构，最终计算流动性/摩擦/规则评分并产出候选列表，供人工复核。

核心流程（CLI 典型顺序）：

1) init-db：初始化数据库
2) sync：同步 Gamma 市场/事件（raw + canonical）
3) enrich：同步 CLOB 价格/订单簿
4) parse：可选 LLM 规则抽取
5) candidates：评分 + 过滤候选导出

## 2. 目录结构与职责分布

- `pm_research/cli.py`
  - CLI 入口，typer 命令集合，统一日志、命令参数与执行入口。
- `pm_research/pipeline.py`
  - 主流程编排：同步、行情/订单簿 enrich、LLM parse、评分与候选输出。
- `pm_research/gamma_client.py`
  - Gamma API 客户端：分页拉取 markets/events，规范化字段。
- `pm_research/clob_client.py`
  - CLOB API 客户端：mid/price/book 拉取，归档完整订单簿（可选）。
- `pm_research/http_client.py`
  - 通用 HTTP 客户端：限速、并发控制、缓存、重试。
- `pm_research/db.py`
  - SQLite 连接与 upsert 执行。
- `pm_research/schema.py`
  - 表结构与 UPSERT SQL 模板。
- `pm_research/storage.py`
  - 持久化与查询层（upsert + select）。
- `pm_research/parser.py`
  - LLM 解析：规则抽取 schema + 解析重试 + 落库。
- `pm_research/llm_client.py`
  - OpenAI 兼容 LLM 调用封装。
- `pm_research/llm_prompts.py`
  - LLM 提示词（系统+few-shot+用户模板）。
- `pm_research/metrics.py`
  - 订单簿/价差指标计算。
- `pm_research/scoring.py`
  - 评分权重与组合逻辑。
- `tests/`
  - LLM schema 校验、Gamma 分页、指标计算等基础测试。

## 3. 入口与命令

入口脚本在 `pyproject.toml` 中注册：

- `pmr = pm_research.cli:app`

CLI 命令概览：

- `pmr init-db`
  - 初始化 SQLite 表结构。
- `pmr sync --active true --pages 5 --page-size 100`
  - 拉取 Gamma markets + events，写入 raw 与 canonical。
- `pmr enrich --prices --orderbooks --limit 500 --top-n 20`
  - 拉取价格与订单簿 Top-N。
- `pmr parse --llm --batch 100`
  - LLM 规则抽取（如未配置 LLM 则跳过）。
- `pmr candidates --min-volume 20000 --max-spread 0.06 --output output/candidates.csv`
  - 评分并导出候选。

## 4. 配置与运行时参数

`pm_research/config.py` 从环境变量或 `.env` 读取：

- API：`GAMMA_BASE_URL`、`CLOB_BASE_URL`
- DB：`PMR_DB_PATH`
- 速率限制：`PMR_RATE_LIMIT_PER_SEC`、`PMR_MAX_CONCURRENCY`、`PMR_CACHE_TTL_SECONDS`
- Orderbook Top-N：`PMR_ORDERBOOK_TOP_N`
- 权重：`PMR_W_RULE`、`PMR_W_FRICTION`
- 打分阈值：`PMR_SPREAD_PCT_CAP`、`PMR_VOL_SCORE_THRESHOLD`、`PMR_DEPTH_SCORE_THRESHOLD`
- LLM：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、`PMR_PROMPT_VERSION`
- 订单簿归档：`PMR_ARCHIVE_BOOKS`、`PMR_ARCHIVE_DIR`

## 5. 数据模型与持久化

`pm_research/schema.py` 定义表：

- `markets_raw`：Gamma 原始市场 JSON
- `events_raw`：Gamma 原始事件 JSON
- `markets`：规范化市场主表
- `prices`：token 价格/中间价
- `orderbook_levels`：Top-N 订单簿级别
- `rule_parses`：LLM 规则解析结果
- `scores`：评分结果

`pm_research/db.py` 提供：

- `get_connection()`：开启 SQLite（WAL 模式）
- `init_db()`：执行 `CREATE_TABLES_SQL`
- `upsert_many()`：基于 UPSERT SQL 批量写入

`pm_research/storage.py` 提供：

- `save_*()`：统一 upsert 到各表
- `get_*()`：关键读取
  - `get_active_token_ids()`
  - `get_markets_for_parsing()`
  - `get_markets_with_tokens()`
  - `get_latest_price()`
  - `get_latest_orderbook()`
  - `get_rule_parse_record()` / `get_rule_parse_samples()`

## 6. Gamma 数据同步

`pm_research/gamma_client.py`：

- `fetch_paginated()`
  - Gamma API 的 offset/limit 分页方式，直到无数据或到达 page 上限。
- `normalize_market()`
  - 统一字段：`market_id/slug/question/description/rules/category/active/resolved/end_at_utc/volume/liquidity/clob_token_ids_json` 等。
  - UTC 时间转换。
- `fetch_markets()`、`fetch_events()`
  - 入口封装。

`pm_research/pipeline.py` 中 `sync_gamma()`：

- 拉取 markets/events → `save_markets_raw`/`save_events_raw`
- 规范化后写入 `markets`

## 7. CLOB 行情与订单簿

`pm_research/clob_client.py`：

- `fetch_price_and_book(token_id, top_n, archive_books)`
  - 拉 `/midprice`, `/price`, `/book`
  - 计算 mid/bid/ask、spread、spread_pct_mid
  - 订单簿仅存 Top-N 层
  - 可选 gzip 归档完整 book
- `enrich_token_batch()`
  - 并发拉取多个 token

`pm_research/pipeline.py` 的 `enrich_prices_orderbooks()`：

- 读取 active token IDs
- `clob_client.enrich_token_batch()` 并写入 prices / orderbook_levels

## 8. HTTP 客户端能力

`pm_research/http_client.py` 关键机制：

- 令牌桶限速（RateLimiter）
- 并发控制（Semaphore）
- 缓存（TTL）
- 429 自动重试（指数退避）

这是所有外部 API 访问的基础保障。

## 9. LLM 规则解析

`pm_research/parser.py`：

- `RuleParse` Pydantic schema
- `parse_market_with_llm()`
  - 调用 LLM，解析 JSON
  - 若失败可重试一次并加强约束
- `save_rule_parse_records()`
  - 持久化解析结果

`pm_research/llm_client.py`：

- OpenAI 兼容 `/v1/chat/completions`
- LLM 配置缺失时直接 raise，pipeline 捕获后跳过

`pm_research/llm_prompts.py`：

- SYSTEM + few-shot + user prompt
- 要求严格输出 JSON，不输出交易建议

## 10. 指标计算与评分

`pm_research/metrics.py`：

- 计算 spread / spread_pct_mid
- 深度：1%/2% bid/ask depth

`pm_research/scoring.py`：

- `liquidity_score()`
  - volume / depth / spread 的组合
- `friction_score()`
  - liquidity + spread 组合
- `rule_score()`
  - clarity + dispute_risk + trigger_type bonus
- `total_score()`
  - 基于权重 `w_rule / w_friction`

## 11. 候选生成

`pm_research/pipeline.py`：

- `compute_scores_and_candidates()`
  - 读取 markets + price + orderbook + rule_parse
  - 计算 metrics + scores
  - 过滤条件：active/未解决/volume/ spread/ clarity/ dispute_risk
  - 输出候选 + 保存 scores

## 12. 测试覆盖

`tests/` 主要覆盖：

- `test_metrics.py`：指标计算
- `test_llm_schema.py`：LLM schema 校验
- `test_gamma_pagination.py`：Gamma 分页逻辑

## 13. 关键入口小结

- **核心入口**：`pm_research/cli.py` → `pipeline.py`
- **数据入口**：Gamma & CLOB client
- **评分入口**：`compute_scores_and_candidates()`
- **输出**：CSV/Markdown 候选列表

## 14. 可能的扩展方向（观察）

- DB 层已是 PG-friendly，可平滑迁移。
- LLM 抽取 schema 可扩展 prompt_version 与 schema_version。
- scoring 权重与阈值已配置化，方便调参。
- 订单簿归档机制可用于后续回放分析。

---

如需：
- 逐文件更细致逐行讲解
- 添加时序图/数据流图
- 生成模块依赖图

可以继续告诉我目标。
