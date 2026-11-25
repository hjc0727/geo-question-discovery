# 输出协议

在独立运行目录保留查询词、原始搜索结果和用于导出的 `input.json`。只写与题目核验有关的文字和链接。

- `industry` 是本次研究主题，可以是品牌加背景或行业。 `entities` 可设置 `brand`（确切品牌名）、`competitors`（已确认名称列表），以及供报告保留的别名和背景。竞品点名需要题干实际出现已确认的名称。
- 两种入口都传 `discovery`，其中 `mode` 为 `brand_discovery` 或 `seed_expansion`。可在 `brand_research` 保留核实的官网、主要产品及服务、竞品依据，在 `query_plan` 保留查询词、关联种子及执行状态。种子扩展传 `seeds` 对象，以种子编号为键、原题为值，例如 `{"S01":"团队协作软件怎么选？"}`。
- `max_questions` 设为用户要求的数量；未指定时导出器默认上限 30。
- `sources` 按平台记方法、查询、成功和失败数、原始与去重结果数。知乎记专栏数、回答数及唯一原问题数；小红书记标题、正文覆盖、评论样本。把原问、归纳、品牌点名原问、竞品点名原问分别统计。少量样本只能说明本轮覆盖。
- `evidence` 每条含 `url`、`title`、`excerpt`、`source`、`method`、`query`。来源和方法使用连接器原值。小红书保留 `evidence_kind` 和 `comments`，其中评论为可见文字列表。合并同 URL 的证据时保留更完整的正文与去重评论。知乎答案作为原题标题的证据时可保留其 API 链接，清单中另提供父问题链接。
- `questions` 每条含 `question`、`category`、`origin`（`explicit` 或 `inferred`）、`evidence_urls`。原问必须指定 `origin_location`（`title`、`body` 或 `comment`），知乎 API 返回的原问用 `title`。原话尽量保持完整，尤其不要把上下文中的品牌写进原题。如果对象只能从所处笔记识别，使用可选的 `context` 记录，例如「匹米替尼（笔记上下文）」。导出器按题干判断点名，引用的评论只从实际采样评论列表校验。
- 在种子扩展入口，为新增题填写 `seed_ids`，例如 `["S01"]`；独立的补充发现用空列表。CSV 加入关联种子编号，报告统计各种子的新增题数。多个种子可关联同一道题，合计不能当作清单去重后的数量。导出器排除与种子题干文字相同的问题；语义等价需在筛选时识别。两种入口的原题均需匹配知乎 API 返回的完整问答题干和可核验的原问题 URL。

在项目根目录运行，得到 `questions.csv` 和 `report.json`：

```sh
python3 -m geo_connector.report <运行目录>/input.json <运行目录>
```
