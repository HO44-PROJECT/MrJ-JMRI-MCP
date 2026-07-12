# jmri-mcp

MCP (Model Context Protocol) server for [JMRI](https://www.jmri.org/) —
control your DCC model railroad by voice or chat, through any MCP client:
Claude Desktop, Claude Code, [xiaozhi](https://github.com/78/xiaozhi-esp32)
voice assistants, etc.

```
pip install jmri-mcp
```

See the [project repository](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP)
for full documentation, including
[docs/llm-setup.md](https://github.com/HO44-PROJECT/MrJ-JMRI-MCP/blob/main/docs/llm-setup.md)
for wiring this server into Claude Desktop/Code or xiaozhi/Kira.

Looking for a plain terminal client instead? See
[`jmri-cli`](https://pypi.org/project/jmri-cli/).

## Third-party code

This package includes `xiaozhi_wrapper`, adapted from the MCP pipe example in
[xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) (MIT License, Copyright
(c) 2025 Shenzhen Xinzhi Future Technology Co., Ltd. and Project
Contributors) — see `src/xiaozhi_wrapper/__init__.py`'s module docstring for
the full notice.
