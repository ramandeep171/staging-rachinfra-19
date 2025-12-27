# MCP Connection Manual Verification Checklist

## 1) Token generation works & masked
- [ ] Open **LLM Configuration → MCP Connections** and create or select a connection.
- [ ] Click **Generate Token** and copy the one-time token from the popup (format `mcp_<slug>_<uid>_<random>`).
- [ ] Confirm the form now shows the token masked (e.g., `****abcd`) and that reopening the record never reveals the full token.

## 2) SSE connects using MCP Connection token
- [ ] From a shell, connect with curl: `curl -H "Authorization: Bearer <TOKEN>" -H "Accept:text/event-stream" "https://<domain>/mcp/sse?db=<database>"`.
- [ ] Verify response headers include `Content-Type: text/event-stream`, `Cache-Control: no-cache`, and `Connection: keep-alive`.
- [ ] Observe an initial `event: tools` payload followed by periodic `event: ping` heartbeats without the connection closing.

## 3) Revoked token fails
- [ ] Edit the connection and set **Revoked** to true (or deactivate the record).
- [ ] Repeat the SSE curl request with the same token and confirm it returns **401 Unauthorized** and no events stream.

## 4) Multiple connections resolve correctly
- [ ] Create two active connections for different companies or tokens and generate distinct tokens for each.
- [ ] Call `/mcp/tools` with each token separately and confirm each request resolves to the matching connection (check `last_used_at` updates on the corresponding record only).
- [ ] Ensure a token from Company A cannot access tools restricted to Company B if multi-company rules apply.

## 5) Old system parameter still works
- [ ] Ensure no MCP connection token matches the bearer value.
- [ ] Set the legacy system parameter/env token as previously configured.
- [ ] Call `/mcp/tools` or `/mcp/sse` with the legacy token and confirm access succeeds while a warning about legacy token usage is logged.
