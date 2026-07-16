# aura-openclaw

Python-native, MIT-licensed **OpenClaw-compatible** control plane for [A.U.R.A.](https://github.com/qweqwe13123/jarvis).

Inspired by [OpenClaw](https://github.com/openclaw/openclaw) (MIT). This is **not** a fork of the TypeScript gateway — it implements the same architectural ideas for the PyQt desktop stack:

- **Gateway** — local WebSocket control plane (default port `18789`)
- **Channels** — desktop UI, Telegram, external OpenClaw bridge
- **Skills** — pluggable always-on capabilities loaded from `runtime/skills/`
- **Sessions** — maps to A.U.R.A. orchestrator + local session files

## Install (development)

```bash
pip install -e packages/aura-openclaw
```

## Embedded gateway

```python
from aura_openclaw.gateway.embedded import AuraGateway

gw = AuraGateway(chat_handler=my_handler)
gw.start()  # ws://127.0.0.1:18789
```

## External OpenClaw

If the official Node OpenClaw gateway is running, use the client:

```python
from aura_openclaw.gateway.client import OpenClawClient

client = OpenClawClient("ws://127.0.0.1:18789")
await client.connect()
await client.chat_send(session_key="main", text="Hello")
```

## License

MIT — see [LICENSE](LICENSE).
