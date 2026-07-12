# Claude Code with GitHub Copilot as Model Provider

Guidance for how to connect [GitHub Copilot](https://github.com/features/copilot) as a model provider for Claude Code, using [copilot-gateway](https://github.com/feiskyer/copilot-gateway) ([npm](https://www.npmjs.com/package/copilot-gateway)).

> NOTICE: calling GitHub Copilot is not against its policy as this is officially supported per doc [here](https://docs.github.com/en/copilot/how-tos/build-copilot-extensions/building-a-copilot-agent-for-your-copilot-extension/using-copilots-llm-for-your-agent). And actually, there are lots of AI tools (e.g. Aider and Cline VSCode extension) already support GitHub Copilot as one of the LLM providers.

## 1) Install Claude Code

```sh
npm install -g @anthropic-ai/claude-code
```

Copilot Gateway itself doesn't need a global install — run it directly with `npx`.

## 2) Start copilot-gateway and authenticate to GitHub Copilot

```
$ npx copilot-gateway@latest start --proxy-env
...
Please visit https://github.com/login/device and enter code XXXX-XXXX to authenticate
...
```

Once succeeds, the server listens on `http://localhost:4141` and exposes both OpenAI (`/v1/chat/completions`, `/v1/responses`, `/v1/models`, `/v1/embeddings`) and Anthropic (`/v1/messages`) compatible endpoints. List available models with:

```sh
curl -s http://localhost:4141/v1/models | jq -r '.data[].id'
```

Useful `start` options (run `npx copilot-gateway@latest start --help` for the full list):

| Option | Description |
| --- | --- |
| `--port, -p` | Port to listen on (default: 4141) |
| `--account-type, -a` | Account type: individual, business, enterprise |
| `--proxy-env` | Initialize proxy from environment variables |
| `--claude-code, -c` | Generate a ready-to-paste Claude Code launch command |
| `--rate-limit, -r` | Rate limit in seconds between requests |
| `--api-key` | Require API keys for incoming requests |

## 3) Create Claude Code configure file `~/.claude/settings.json` with the following contents

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:4141",
    "ANTHROPIC_AUTH_TOKEN": "sk-dummy",
    "ANTHROPIC_MODEL": "claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5-mini",
    "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
    "CLAUDE_CODE_ATTRIBUTION_HEADER": "0"
  }
}
```

Model names must match what your gateway actually serves — check with the `/v1/models` request above and replace as needed.

Alternatively, run with `--claude-code` to get a ready-to-paste launch command without editing settings:

```sh
npx copilot-gateway@latest start --claude-code
```

## 4) Run claude

Open another terminal and then run `claude` at your will. DO read its [best practices](https://www.anthropic.com/engineering/claude-code-best-practices) for fully leveraging its capabilities.

## Alternative config

If the above-configured file doesn't work, use the env variable directly:

```sh
export ANTHROPIC_BASE_URL="http://localhost:4141"
export ANTHROPIC_AUTH_TOKEN="sk-dummy"
export ANTHROPIC_MODEL="claude-sonnet-4-6"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="gpt-5-mini"
export DISABLE_NON_ESSENTIAL_MODEL_CALLS="1"
export CLAUDE_CODE_ATTRIBUTION_HEADER="0"

claude
```

## Docker

Pre-built images are published to `ghcr.io/feiskyer/copilot-gateway` on every release:

```sh
docker run -p 4141:4141 ghcr.io/feiskyer/copilot-gateway:latest

# Persist auth across restarts with a bind mount
mkdir -p ./copilot-data
docker run -p 4141:4141 \
  -v $(pwd)/copilot-data:/root/.local/share/copilot-gateway \
  ghcr.io/feiskyer/copilot-gateway:latest
```

## Usage monitoring

Check your Copilot usage/quota without starting the server:

```sh
npx copilot-gateway@latest check-usage
```
