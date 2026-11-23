# 输出协议

将 JSON 写入本次运行目录的 input.json，形状如下。

- industry 为行业名。
- sources 是来源状态对象。每源至少说明 method 和 status，有查询日志时一并保留。
- evidence 是记录列表。每条含 url、title、excerpt、source（zhihu 或 xiaohongshu）、method（zhihu_api、bocha_index、xhs_browser 或 host_web_search）、query。excerpt 用实际可获取的短片段。小红书站内记录带 evidence_kind，区分 title、search_snippet 和 body。知乎来源尽量保留官方链接参数。
- questions 是候选问题列表。每条含 question、category、origin（explicit 或 inferred）、evidence_urls。显式问题的题干应出现在至少一条来源标题或片段中。归纳问题保留原始证据片段，由执行者判断是否支持题意。模型先做语义合并，导出器再做确定性校验。

在项目根目录执行以下命令。导出器拒绝无匹配证据的条目，合并同一品类的重复题干，输出 questions.csv 和 report.json。

```sh
python3 -m geo_connector.report <运行目录>/input.json <运行目录>
```
