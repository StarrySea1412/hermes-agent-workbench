# Hermes Integration Notes

This project treats Hermes as the execution runtime behind the workbench.

## Current integration model

The backend talks to Hermes through an OpenAI-compatible gateway:

- `services/hermes_service.py`

The workbench uses Hermes for:

- multi-step chat completions
- tool calling
- session-based run execution
- runtime health checks

## Request shape

Each run builds:

1. a base system prompt for the workbench
2. optional skill text from `hermes_skills/`
3. optional fallback tool prompt text
4. attached user or workspace memories
5. user mission text

The orchestrator then loops through:

- `plan`
- `tool_call`
- `tool_result`
- `answer`
- `error`

## Session handling

Each run is assigned a session ID such as:

- `u<user_id>-run<run_id>`

That session ID is forwarded to Hermes through:

- `X-Hermes-Session-Id`

## Tool policy

Templates can restrict available tools through `allowed_tools`.

Behavior:

- empty `allowed_tools` means all registered tools
- non-empty `allowed_tools` becomes a whitelist
- fallback prompt-based tool calls are filtered by the same whitelist

## Memory policy

Runs can attach memory records by ID.

Those records are:

- scoped to the authenticated user
- injected into the runtime prompt
- surfaced again in run detail
- updated with `last_used_at` when a run executes

## Monitoring

Runtime checks are exposed through:

- `GET /api/hermes/status`
- `GET /api/hermes/monitor`
- `GET /api/hermes/skills`

The Settings page consumes these endpoints to show gateway state and local skill inventory.

## External search

`web_search` can use a live provider when the backend environment includes:

- `BRAVE_SEARCH_API_KEY`
- `SERPAPI_API_KEY`

If neither is set, the tool returns a clear configuration error to the run trace.
