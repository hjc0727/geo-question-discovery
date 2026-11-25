# GEO 品牌与行业问题发现 Skill

输入品牌名即可开始。Skill 会核实官网、产品服务和竞品，再调用知乎 API 采集问题。提供已有行业问题时，Skill 会沿种子扩搜，标明新增问题关联的种子。两种入口都输出带来源的 CSV。

## 使用

1. 安装 Codex 和 [uv](https://docs.astral.sh/uv/)。使用小红书站内搜索还需要 Google Chrome。
2. 克隆仓库，在仓库根目录运行 `uv sync --locked`，再用 Codex 打开该目录。项目配置会注册 `geo_research` MCP 服务。
3. 知乎搜索读取 Codex 启动环境里的 `ZHIHU_ACCESS_SECRET`。可选的博查网页搜索读取 `BOCHA_API_KEY`。请将密钥留在本地。
4. 小红书站内搜索首次运行下列命令，在专用 Chrome 窗口登录，再回终端按回车保存会话。

   ```sh
   uv run --locked python -m geo_connector.xhs_browser login
   ```

5. 在 Codex 输入 `$geo-question-discovery 品牌：示例品牌`。也可补官网、产品服务、竞品和目标条数。提供种子问题时，例如 `$geo-question-discovery 品牌：示例品牌；种子问题：团队协作工具怎么迁移历史任务？`。

这两种流程默认只查知乎。清单区分原题与归纳题，报告记录覆盖和来源。小红书浏览器工具可[单独使用](.agents/skills/geo-question-discovery/references/xiaohongshu-browser.md)。

## 测试

```sh
uv run --locked python -m unittest discover -s tests -v
```

浏览器测试使用本地模拟页面，需要 Chrome，无需登录账号。真实站内覆盖取决于账号和当时的小红书页面。
