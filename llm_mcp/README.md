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
   - Keep the generated `/mcp/*` URLs exactly as displayed (they include `?db=<name>` so stateless clients pick the right database when multiple DBs live on the same instance).
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

## License

This module is distributed under the [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html) license, consistent with the rest of the LLM stack.
