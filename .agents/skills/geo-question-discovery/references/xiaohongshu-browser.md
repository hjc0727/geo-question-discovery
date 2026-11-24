# 小红书站内搜索使用说明

需要本机 Chrome 和项目已使用的 uv。首次从 GEO 项目目录执行：

```sh
uv run --locked python -m geo_connector.xhs_browser login
```

在打开的专用 Chrome 窗口完成小红书登录，确认网页里能正常搜索，再回到终端按回车保存。登录状态只保存在项目本机的 .xhs-browser 目录。这个目录排除在版本管理之外，请勿共享。

之后在 GEO 项目使用 `$geo-question-discovery 服装`。可以单独测试搜索：

```sh
uv run --locked python -m geo_connector.xhs_browser search "通勤白衬衫" "梨形牛仔裤" "冲锋衣软壳硬壳"
```

工具逐词使用网页搜索框，读取已显示的笔记卡片，按需打开少量笔记读取可见正文。一批 1–3 个词，每词默认最多 5 条，结果为 JSON。每条记录保留标题、笔记链接、证据和证据类型。导出的链接移除了查询参数；部分笔记在另一设备可能仍需登录或在站内用标题定位。

- setup_required 或 login_required：完成专用窗口登录，再重跑。
- verification_required 或 access_limited：本次采集停止。请通过正常页面完成所需操作。
- browser_unavailable：检查 Chrome 是否已安装，关闭正在占用专用会话的窗口。
- search_ui_unavailable 或 results_unavailable：检查站内页面是否能手动搜索，网页改版时更新选择器。
- empty：页面明确显示无结果。换更短或更通用的词后再测。

需要看正文和评论时，调用 `search_xiaohongshu_browser`，设置 `include_comments=true` 和 `detail_limit=3`，或使用：

```sh
uv run --locked python -m geo_connector.xhs_browser search "贝捷迈" "色绒 术后又肿" --limit 8 --detail-limit 3 --comments
```

`detail_limit` 每词 0–5，默认 2。评论采样只读取当前可见正文型笔记下最多 6 条已展示的评论文字，不展开评论线程。返回 `comments: []` 表示进行了采样但当时未读到；缺少该字段表示该笔记未采样。若连接器仍暴露旧工具参数，使用上面的 CLI。遇到登录时可开启专用窗口让用户登录，随后继续；站内无法使用时用博查或公开网页补查，并记录实际来源。
