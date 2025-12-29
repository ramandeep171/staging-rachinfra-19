# MCP → ChatGPT Function Adapter

## End-to-end flow
1. **Client fetches functions** via `GET /mcp/chatgpt/functions` with bearer MCP token.
2. **Adapter builds sanitized functions** from `llm.tool.registry.service`, using `ToolSanitizer` to expose only `name`, `description`, and `parameters` (`input_schema`).
3. **ChatGPT receives execution contract** with URLs, headers, and body shape; the agent uses the `Authorization` header exactly as returned (no key injection in prompts).
4. **Agent calls `POST /mcp/execute`** with `{tool: <function.name>, params: {...}, session_id}`; schema validation, rate limits, timeouts, and loop guards run in `llm.mcp.execution.router`.
5. **Optional SSE stream** via `GET /mcp/sse` keeps the session warm and publishes `ready/tools/heartbeat/close/error` events; server closes on disconnect or max duration.

## Example ChatGPT function schema
```json
{
  "name": "search_leads",
  "description": "Search CRM leads by status and owner",
  "parameters": {
    "type": "object",
    "properties": {
      "status": {"type": "string", "enum": ["new", "qualified", "won", "lost"]},
      "owner_id": {"type": "integer", "description": "Internal user ID"}
    },
    "required": ["status"],
    "additionalProperties": false
  },
  "strict": true,
  "x-mcp-tool-key": "crm.search.leads"
}
```

## Safe execution contract
- **Transport:** HTTPS only; bearer token issued per MCP connection.
- **Call contract:**
  - Method: `POST`
  - URL: `<base>/mcp/execute`
  - Headers: `Authorization: Bearer <token>`
  - Body: `{ "tool": "<function.name>", "params": { ... }, "session_id": "<optional>" }`
- **Stream contract:** optional SSE at `<base>/mcp/sse` with the same token and `session_id` query param.
- **Runtime safety:** per-tool JSON schema validation, execution timeouts, recursion guards, and distributed rate limiting remain enforced server-side; contract consumers must not alter headers or body keys outside of the documented shape.
