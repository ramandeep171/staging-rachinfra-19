# MCP Context Packing Controls

## Rules
- Inline results up to **4096 bytes**; add `_context_packing` metadata with byte count for observability.
- Above 4 KB, **summarize + hash** the payload: first 1024 bytes kept as `summary`, include `sha256`, `bytes`, and `inline_limit`.
- Persist full oversized payloads to a private Odoo attachment linked to the tool for audit/debug; only the hash + attachment ref is returned to the LLM.
- Never mutate error envelopes; execution errors flow through unchanged.

## Flow (text)
`runner result → context packer → if >4KB → summary + sha256 + attachment ref → response`

## Example Output
```json
{
  "packed_result": {
    "summary": "{\"records\":[{...truncated...}]",
    "sha256": "a4dafe5b6c7f9c3e9b01d0f5b1f9229f1f4f79cba3a9b80a1d93d6f8d557af91",
    "bytes": 18342,
    "inline_limit": 4096,
    "truncated": true,
    "packed": true,
    "storage": {
      "attachment_id": 123,
      "sha256": "a4dafe5b6c7f9c3e9b01d0f5b1f9229f1f4f79cba3a9b80a1d93d6f8d557af91",
      "bytes": 18342,
      "name": "mcp-result-42-20241008"
    },
    "original_type": "dict"
  },
  "_context_packing": {
    "summary": "{\"records\":[{...truncated...}]",
    "sha256": "a4dafe5b6c7f9c3e9b01d0f5b1f9229f1f4f79cba3a9b80a1d93d6f8d557af91",
    "bytes": 18342,
    "inline_limit": 4096,
    "truncated": true,
    "packed": true,
    "storage": {
      "attachment_id": 123,
      "sha256": "a4dafe5b6c7f9c3e9b01d0f5b1f9229f1f4f79cba3a9b80a1d93d6f8d557af91",
      "bytes": 18342,
      "name": "mcp-result-42-20241008"
    },
    "original_type": "dict"
  }
}
```

## Client Guidance
- Use `packed_result.summary` for prompt injection; fetch full payload via attachment only for human review.
- Treat `_context_packing.packed` as the guardrail signal when building the LLM context.
