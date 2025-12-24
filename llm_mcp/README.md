# LLM MCP for Odoo 19 Enterprise

Model Context Protocol (MCP) integration that lets the Odoo 19 Enterprise LLM stack connect to external tool providers over stdio or internal services.

## Overview

`llm_mcp` extends the `llm` and `llm_tool` modules with a server registry and a process manager capable of:

- Spawning MCP-compliant processes over standard I/O and keeping them alive.
- Listing remote tools and importing their schemas into the native `llm.tool` model.
- Executing MCP tools from Odoo chatter threads, passing arguments, and propagating results back to the assistant.
- Streaming tool execution events to the UI through the existing mail message bus.

## Odoo 19 Enterprise Setup Checklist

1. **Install prerequisites** – deploy `llm` and `llm_tool` first and run `pip install -r requirements.txt` to ensure the shared Python dependencies are available.
2. **Install the module** – execute `./odoo-bin -c odoo.conf -i llm_mcp --stop-after-init` or install it from the Apps dashboard.
3. **Grant access** – give administrators the *LLM Manager* group so they can create MCP servers and manage imported tools.
4. **Restart the service** – reload the Odoo service so that the MCP bus bridge threads are registered in the registry.
5. **Smoke test** – open *LLM → Configuration → MCP Servers*; the list view should load without tracebacks in `odoo19e.log`.

## Configuring an MCP Server

1. **Create a server record**
   - Go to *LLM → Configuration → MCP Servers*.
   - Choose the transport (`Standard IO` for external processes, `Internal` for in-database tooling).
   - Provide the command, arguments, and mark the server as *Active*.
2. **Start and validate**
   - Click **Start Server**; the process manager will spawn the command and initialize the MCP handshake.
   - Use **List Tools** to fetch remote tool definitions. Imported tools are linked via `mcp_server_id` and visible under *LLM → Configuration → Tools*.
3. **Assign usage**
   - Attach the imported tools to assistants, server actions, or allow the default tool set to include them automatically.
4. **Stop or restart**
   - Use **Stop Server** to terminate the stdio bridge cleanly. The manager ensures the process is killed and the registry state is reset.

## Execution Flow

1. A chatter message produced by an LLM response contains a `tool_call`.
2. `llm_tool` posts a tool message with status `requested`.
3. If the tool points to an MCP server (`implementation = 'mcp'`), the bridge serializes the call and sends it to the external process.
4. Responses are written back to `body_json`, and the tool message status is updated to `completed` or `error`.

## Validation & Troubleshooting

- **CLI validation**  
  ```bash
  ./odoo-bin shell -c odoo.conf -d <db_name> <<'PY'
  env['llm.mcp.server'].search([], limit=1).start_server()
  PY
  ```
  Confirms the server can be launched without UI interaction.
- **Log monitoring** – follow `tail -f odoo19e.log` while starting/stopping servers to ensure no `UserError` or subprocess exceptions are raised.
- **Tool sync issues** – rerun **List Tools**; stale tools are cleaned automatically, and new tools are created or updated with the latest schema.
- **Access control** – only users in *LLM Manager* may create servers; regular users can execute imported tools but cannot modify server definitions.

## Technical Specifications

- **Name**: LLM MCP
- **Version**: 19.0.1.0.0
- **Dependencies**: `base`, `mail`, `llm`, `llm_tool`
- **Transport Supported**: `internal`, `stdio`
- **Key Models**:
  - `llm.mcp.server` – server definitions, status, and tool synchronization.
  - `llm.mcp.bus.manager` – stdio process supervision and JSON-RPC routing.
  - `llm.mcp.bus.bridge` – optional bus bridge for forwarding notifications.
  - `llm.tool` (extended) – adds the `mcp_server_id` link and `mcp_execute`.

## Deployment Proxy Configuration

Use an explicit streaming-friendly reverse proxy in front of the MCP routes to keep Server-Sent Events compatible with ChatGPT and GenSpark clients. The following nginx snippet is copy/paste ready; adjust host/port values to match your Odoo upstream:

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;

    # TLS configuration elided

    location /mcp/ {
        proxy_pass http://odoo:8069;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;

        proxy_http_version 1.1;
        proxy_buffering off;              # required for SSE
        proxy_request_buffering off;
        proxy_read_timeout 3600s;         # allow long-lived streams
        proxy_send_timeout 3600s;
        send_timeout 3600s;
        proxy_connect_timeout 30s;
        keepalive_timeout 75s;

        # ensure SSE headers survive proxying
        add_header Cache-Control "no-cache";
        add_header Connection "keep-alive";
        add_header X-Accel-Buffering "no";
    }
}
```

## Cloudflare / CDN Notes

- Disable features that buffer or coalesce responses: **Rocket Loader**, HTML/JS minification, and **Automatic Platform Optimization (APO)** should be off for the MCP hostname.
- Set **Caching** to *Bypass* for `/mcp/*` and `/.well-known/*` paths; SSE must never be cached.
- Ensure **WebSockets**/**HTTP/2** is allowed; Cloudflare will proxy SSE over HTTP/2 without buffering when *Proxying* is enabled and buffering features are off.
- Raise **Response Timeout** to at least 100 seconds and **Idle Timeout** to 3600 seconds so heartbeat-driven SSE streams remain open. Align any Cloudflare rate limits with the application defaults (see below) to avoid double-throttling.

## Environment Variables & Limits

Operational defaults are defined in the gateway controller and are safe for production use. Tune only if you fully control the proxy and client behavior:

- **SSE heartbeat interval**: 15s (`HEARTBEAT_INTERVAL`) keeps connections warm without excessive chatter; lowering increases bandwidth, raising risks idle timeouts.【F:llm_mcp/controllers/mcp_gateway.py†L54-L74】【F:llm_mcp/controllers/mcp_gateway.py†L586-L629】
- **Max concurrent SSE streams per IP**: 3 (`SSE_MAX_PER_IP`) prevents runaway tabs; increase only when trusted clients need parallel sessions.【F:llm_mcp/controllers/mcp_gateway.py†L54-L74】
- **No-auth rate limit**: 60 requests per 60s (`RATE_LIMIT_NO_AUTH` / `RATE_LIMIT_WINDOW`) protects discovery endpoints; align with CDN/WAF rate limits to avoid duplicate blocking.【F:llm_mcp/controllers/mcp_gateway.py†L54-L74】
- **OAuth token TTL**: 300s (`OAUTH_TOKEN_TTL`) balances short-lived credentials with user convenience; keep short when fronted by shared proxies.【F:llm_mcp/controllers/mcp_gateway.py†L54-L74】

If you must override these, export environment variables that your Odoo entrypoint can read before importing `llm_mcp` and set the class attributes accordingly (e.g., `MCPGatewayController.HEARTBEAT_INTERVAL = int(os.getenv(...))`). Keep nginx/CDN timeouts above the heartbeat interval so the stream stays alive.

## Operator Runbook

- **Healthy signals**
  - Access logs include `"outcome": "ok"` with `auth_mode` set (oauth/bearer/no_auth) for `/mcp/tools`, `/mcp/execute`, and `/mcp/sse` calls.【F:llm_mcp/controllers/mcp_gateway.py†L76-L115】
  - SSE lifecycle logs show `sse_open` on connect and `sse_closed` with short durations under normal UI usage.【F:llm_mcp/controllers/mcp_gateway.py†L631-L705】
  - OAuth token issuance logs at INFO with `oauth_token_issued` and redacted payloads; last issuance timestamp advances under load.【F:llm_mcp/controllers/mcp_gateway.py†L116-L176】【F:llm_mcp/controllers/mcp_gateway.py†L705-L750】

- **Abnormal patterns**
  - Bursts of `sse_cap_rejected` or `rate_limit_no_auth` indicate abusive clients or missing CDN throttles.【F:llm_mcp/controllers/mcp_gateway.py†L631-L705】
  - `oauth_token_invalid` or `oauth_token_expired` warnings mean clients reuse stale tokens; check OAuth token TTL and client refresh behavior.【F:llm_mcp/controllers/mcp_gateway.py†L116-L176】【F:llm_mcp/controllers/mcp_gateway.py†L586-L629】
  - `no_auth_execute_blocked` suggests unauthenticated callers hitting execute; confirm Authorization headers are forwarded by the proxy.【F:llm_mcp/controllers/mcp_gateway.py†L116-L176】

- **Common incidents and first response**
  - **SSE disconnect storms**: look for upstream 499/504 in proxy logs and `sse_closed` durations near zero. Increase `proxy_read_timeout`, verify Cloudflare idle timeout, and ensure heartbeat interval is below those thresholds.
  - **OAuth token failures**: search for `oauth_token_invalid` warnings; confirm the proxy forwards `Authorization` headers untouched and that clients request new tokens within the 300s TTL.
  - **Rate-limit spikes**: `rate_limit_no_auth` warns of excessive discovery traffic. Raise CDN/WAF rate limits to match app thresholds or temporarily lift `RATE_LIMIT_NO_AUTH` while investigating.

## Deployment Checklist

- **Before go-live**
  - Apply the nginx snippet (or equivalent) with buffering disabled and `Authorization` headers forwarded.
  - Disable CDN buffering/caching for `/mcp/*` and ensure idle/response timeouts exceed the heartbeat interval.
  - Confirm environment limits (heartbeat, stream caps, rate limits, OAuth TTL) are aligned with proxy timeouts.

- **After deploy validation**
  - Run a tool discovery request without auth (expect 200) and an execute call with bearer/OAuth (expect success) through the proxy.
  - Initiate an SSE session and verify the first event is `ready`; observe `sse_open`/`sse_closed` logs with reasonable durations.
  - Confirm OAuth token issuance logs appear once `/oauth/token` is used.

- **During an incident**
  - Inspect logs for `rate_limit_no_auth`, `sse_cap_rejected`, or repeated `oauth_token_invalid` to triage cause.
  - Check proxy/CDN timeouts and buffering settings; revert to the documented nginx configuration if mismatched.
  - Temporarily lower client load or adjust `SSE_MAX_PER_IP`/rate limits (with matching CDN changes) while root cause is addressed.

## End-to-End Smoke Validation (no Odoo UI required)

Run the following from a shell pointed at your MCP proxy host (replace `https://mcp.example.com` and bearer values as needed). Expected outputs are described inline so you can quickly confirm the path is healthy end-to-end.

```bash
BASE="https://mcp.example.com"

echo "1) OAuth discovery (.well-known)" && \
curl -sS "$BASE/.well-known/oauth-authorization-server" | jq .authorization_endpoint && \
curl -sS "$BASE/.well-known/openid-configuration" | jq .issuer
# Expect non-empty URLs; status 200.

echo "2) Soft OAuth token issuance" && \
ACCESS_TOKEN=$(curl -sS -X POST "$BASE/oauth/token" -d 'grant_type=client_credentials&client_id=test' | jq -r .access_token) && \
echo "   issued token: ${ACCESS_TOKEN:0:8}..."
# Expect an access_token string; status 200.

echo "3) SSE stream (first event should be ready)" && \
curl -sS -H "Authorization: Bearer $ACCESS_TOKEN" "$BASE/mcp/sse" --max-time 10 | head -n 2
# Expect lines:
# event: ready
# data: {"ready":true,...}

echo "4) Tool discovery" && \
curl -sS "$BASE/mcp/tools" | jq '.tools | type'
# Expect "array"; status 200 even without Authorization.

echo "5) Execute call (returns result or MCP error envelope)" && \
curl -sS -X POST -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"tool_name": "ping", "arguments": {"text": "hello"}}' \
  "$BASE/mcp/execute" | jq '{result, error} '
# Expect either a result payload or {"error": {"code":..., "message":...}} with HTTP 200.
```

## Client Onboarding Playbook

| Client | URL to supply | Auth mode | Headers / steps | Common mistakes & fixes |
| --- | --- | --- | --- | --- |
| **ChatGPT MCP Apps** | SSE: `https://mcp.example.com/mcp/sse`<br>Tools: `https://mcp.example.com/mcp/tools`<br>Execute: `https://mcp.example.com/mcp/execute` | Prefer **OAuth**. Use `/oauth/token` to mint an access token; paste the token as Bearer in the MCP app. | Ensure `Authorization: Bearer <token>` is forwarded by the reverse proxy. Use the `.well-known` URLs when ChatGPT requests OAuth discovery. | Missing `Authorization` header or proxy stripping it → ready event never arrives. Disable proxy buffering. |
| **GenSpark** | Same URLs as above. | **OAuth** or existing **Bearer** tokens both work. | Provide the OAuth discovery URLs in the GenSpark MCP config; set Bearer token with `/oauth/token` response. | Token TTL is short (default 300s); configure GenSpark to refresh periodically. Ensure CORS preflight is allowed. |
| **Claude Desktop / Cursor** | Same URLs; both support MCP over SSE. | **Bearer** tokens typically easiest; OAuth tokens are accepted. | Add `Authorization: Bearer <token>` header in client settings; keep SSE URL pointed at `/mcp/sse`. | Local proxies or VPNs that buffer responses can block ready events—turn off response buffering/caching. |

## Go / No-Go Checklist

**Infrastructure**
- [ ] Reverse proxy uses `proxy_buffering off`, `proxy_read_timeout >= 3600s`, forwards `Authorization`, and keeps `Connection: keep-alive`.
- [ ] CDN/WAF rules bypass caching for `/mcp/*` and `/.well-known/*`; idle timeout exceeds heartbeat interval.
- [ ] SSL certificates valid; MCP host reachable from target clients.

**Authentication**
- [ ] `/mcp/tools` works without Authorization; `/mcp/execute` requires Bearer/OAuth.
- [ ] `/oauth/token` returns an access token; `.well-known` endpoints resolve.
- [ ] Ready event appears immediately on `/mcp/sse` with a valid token.

**Limits & Safety**
- [ ] SSE concurrent cap and no-auth rate limits align with CDN/WAF settings.
- [ ] Heartbeat interval below all upstream idle timeouts.
- [ ] Observability logs reachable (INFO level) and free of repeated warnings.

**Observability**
- [ ] Recent logs include `oauth_token_issued`, `sse_open`, and successful `/mcp/tools` access entries.
- [ ] No persistent `oauth_token_invalid`, `rate_limit_no_auth`, or `sse_cap_rejected` messages in the last 15 minutes.

## Regression Safety Notes

- **Risky areas**: SSE framing (ready-first output), Authorization header forwarding, and OAuth token issuance. Upstream buffering/caching changes can also break MCP readiness.
- **What to retest after upgrades**: rerun the smoke script above; verify `.well-known` endpoints, `/oauth/token`, `/mcp/sse` ready event, `/mcp/tools`, and `/mcp/execute` with a token. Confirm headers in the proxy still match the documented nginx snippet.
- **Post-deploy quick health**: check for `sse_open`/`sse_closed` in logs with reasonable durations and recent `oauth_token_issued`. Run a no-auth `/mcp/tools` call and an authenticated `/mcp/execute` to ensure auth gates are intact.

## License

This module is distributed under the [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html) license, consistent with the rest of the LLM stack.
