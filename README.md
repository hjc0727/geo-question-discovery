# GEO 品牌与行业问题发现 Skill

输入品牌名称和产品或服务描述，或直接输入行业名。Skill 会从描述提取自然问法，扩展品牌及别名、已确认竞品及比较词，在知乎和小红书采集带来源的问题。仓库包含 Codex Skill、本地 MCP 连接器和测试。

## 使用

1. 安装 Codex 和 [uv](https://docs.astral.sh/uv/)。使用小红书站内搜索还需要 Google Chrome。
2. 克隆仓库，在仓库根目录运行 `uv sync --locked`，再用 Codex 打开该目录。项目配置会注册 `geo_research` MCP 服务。
3. 知乎搜索读取 Codex 启动环境里的 `ZHIHU_ACCESS_SECRET`。可选的博查网页搜索读取 `BOCHA_API_KEY`。请将密钥留在本地。
4. 小红书站内搜索首次运行下列命令，在专用 Chrome 窗口登录，再回终端按回车保存会话。

   ```sh
   uv run --locked python -m geo_connector.xhs_browser login
   ```

5. 在 Codex 输入 `$geo-question-discovery 品牌：示例品牌；产品或服务描述：面向小团队的在线项目管理工具；目标：50 条`。品牌官网、别名、产品列表和目标数量可按需提供。也可输入 `$geo-question-discovery 服装`，或单独试跑站内搜索：

   ```sh
   uv run --locked python -m geo_connector.xhs_browser search "通勤白衬衫" "梨形牛仔裤" "冲锋衣软壳硬壳" --detail-limit 3 --comments
   ```

站内搜索读取浏览器可见的笔记。遇到登录、验证或访问限制时，工具会返回状态。采集证据可包含标题、摘要、正文和可见评论。问题清单区分平台原问与归纳问法，并标注原问位置、品牌或竞品点名和来源链接。

## 测试

```sh
uv run --locked python -m unittest discover -s tests -v
```

浏览器测试使用本地模拟页面，需要 Chrome，无需登录账号。真实站内覆盖取决于账号和当时的小红书页面。
