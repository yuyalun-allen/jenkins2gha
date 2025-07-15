# Jenkins to CodeArts 迁移工具

## Quick start

推荐使用 [`uv`](https://github.com/astral-sh/uv) python 项目构建工具运行本工具。

1. 安装依赖

```sh
uv install
```

2. 配置大语言模型（Optional）

编辑 .env 文件，输入 llm endpoint 和对应的 secret key。

**注意：**  ⚠️ llm api 必须是 openai compatible 的。

`.env`
```sh
LLM_URL=https://api.deepseek.com
SK=your-secret-api-key
MODEL=deepseek-chat
```

**注意：** ⚠️ 若未配置大语言模型，若配置中存在未实现转换规则的配置项则会给出 LLM Error！

3. 运行工具

```sh
uv run app.py
```

