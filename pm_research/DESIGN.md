# 描述 + 思路

## 描述
本系统是一个 **只读研究型粗筛** 管线，用于从 Polymarket 公共数据中提取市场规则结构、计算流动性与摩擦指标、并导出候选研究清单。系统仅用于研究和审计，不提供任何交易或下注建议。

## 思路
1. **数据发现（Gamma API）**
   - 通过 `GET /markets` 和 `GET /events` 分页拉取公开市场与事件元数据。
   - 同步时将原始 JSON 全量落库（`markets_raw/events_raw`），并 upsert 写入 `markets` 表。

2. **价格与订单簿（CLOB API）**
   - 对 `clobTokenIds` 批量查询 `midprice/price/book`。
   - 实现速率限制、429 退避、并发控制。
   - 订单簿只保留 top N 档，避免无限扩张；可选 gzip 归档原始 book。

3. **规则结构化（LLM Extractor）**
   - 通过 OpenAI-compatible API 进行“Extractor-only”解析。
   - 输出严格 JSON（Pydantic 校验），仅包含规则结构与不确定性标记。

4. **指标计算与粗筛**
   - 计算 spread、spread_pct_mid、depth_1%/2% 和 liquidity_score。
   - 依据清晰度、争议风险、触发类型与摩擦指标进行粗筛排序。

5. **候选导出**
   - 输出候选 CSV（并可扩展为 Markdown）。
   - 列包含市场元数据、指标、LLM 解析字段与备注，供人工复核。
