# MCP Setup

Read this reference only when the SpriteGameGen server is missing, disconnected,
or being installed.

## Prerequisites

- Python 3.11 or newer
- `uv`
- An MCP client that supports local stdio servers
- Provider configuration only for creative calls

From the repository's `backend` directory:

```text
uv sync --locked --extra dev
```

The installed entrypoint is:

```text
Windows: <repo>\backend\.venv\Scripts\sprite-mcp.exe
POSIX:   <repo>/backend/.venv/bin/sprite-mcp
```

## Client Registration

Configure a local stdio MCP server using the absolute entrypoint path. MCP
clients use different configuration keys; this common `mcpServers` shape is an
example, not a universal client schema:

```json
{
  "mcpServers": {
    "sprite-game": {
      "command": "/absolute/path/to/backend/.venv/bin/sprite-mcp",
      "env": {
        "SPRITE_ENV_FILE": "/absolute/path/to/backend/.env",
        "PROJECTS_DIR": "/absolute/path/to/projects"
      }
    }
  }
}
```

Use the host client's documented equivalent for `command` and `env`. Some
clients represent the command as an array and others split executable and
arguments.

`SPRITE_ENV_FILE` must be absolute. Keep `PROJECTS_DIR` absolute too so a client
launched from a foreign working directory uses the intended store. Do not place
credentials directly in the skill or commit them to source control.

## Provider Configuration

The server starts and supports discovery, project reads, resource reads,
curation, recipes, and exports without provider credentials.

Creative operations require at least one configured provider:

- Azure GPT Image: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and
  `AZURE_OPENAI_DEPLOYMENT`
- Gemini through Vertex AI: `GOOGLE_APPLICATION_CREDENTIALS`,
  `GOOGLE_CLOUD_PROJECT`, and usually `GOOGLE_CLOUD_REGION=global`
- ComfyUI: explicit loopback `COMFYUI_URL` and trusted operator-owned
  `COMFYUI_WORKFLOW_DESCRIPTOR`

The live `get_capabilities` result, not environment-variable presence, decides
whether a provider is currently usable.

## Verification

From the repository root, run the credential-free protocol smoke test:

```text
Windows: backend\.venv\Scripts\python.exe scripts\smoke_mcp.py
POSIX:   backend/.venv/bin/python scripts/smoke_mcp.py
```

It launches the installed stdio entrypoint from a foreign working directory,
checks the exact direct tool inventory, and calls `get_capabilities` without
cloud credentials.

If the smoke test passes but the host exposes no SpriteGameGen tools, fix the
host's MCP registration or restart the host so it reloads configuration. If the
tools appear and only creative calls fail, inspect `get_capabilities` for the
provider's `unavailable_reason`; this is not an MCP startup failure.
