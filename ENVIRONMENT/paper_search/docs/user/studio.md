# LangGraph Studio

The graph can be run and inspected node-by-node in LangGraph Studio.

```bash
uv run --extra studio langgraph dev --allow-blocking
```

`--allow-blocking` is required: SearchAgent's pipeline is **synchronous**
(file I/O, urllib, sleeps), and the dev server otherwise runs `blockbuster`,
which rejects blocking I/O on the event loop (`BlockingError`).

This starts the local dev server and prints a Studio URL, e.g.
`https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`. Open it and
provide the run input as JSON:

```json
{"material": "RuO2", "reaction": "HER", "extra_terms": [],
 "research_context": {}, "harness_errors": [], "resume_events": []}
```

Studio lets you step through the nine nodes, inspect the state after each, and
re-run with edited inputs.

Set `PAPER_SEARCH_PROVIDER=openai`, `anthropic`, or `openai-oauth` in `.env` to
drive the [full agent](full-agent.md) in Studio; otherwise it runs
deterministically. The entrypoint is `langgraph.json` →
`paper_search.agent.studio:make_graph`, which builds runtime services and
returns the compiled graph.

!!! note
    Studio's dev server serializes state with its own serializer and may log an
    "unregistered type" warning for the `Paper` / `SurfaceClaim` dataclasses. It
    works on the current LangGraph version.

!!! warning "Failed to fetch / cannot connect"
    The hosted Studio page is HTTPS but the dev server is `http://127.0.0.1:2024`.
    Browsers that block HTTPS→localhost (Safari, Brave, Firefox) show
    *"Failed to fetch"*. Open the URL in **Chrome** (allows localhost), or start
    the server with `langgraph dev --allow-blocking --tunnel` and use the printed
    HTTPS tunnel URL.

## Agent Chat UI

The graph also works with [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui),
because its state carries a `messages` channel: an `intake` node parses the
material/reaction (and research direction) from your chat message, and the agent
replies with the report as an assistant message.

1. Start the graph server: `uv run --extra studio langgraph dev --allow-blocking`.
2. Run Agent Chat UI (`npx create-agent-chat-app`, or the hosted
   [agentchat.vercel.app](https://agentchat.vercel.app)).
3. Point it at the deployment URL `http://localhost:2024` with graph ID
   `catalyst_literature`.
4. Chat, e.g. *"RuO2 HER, prioritize durable surfaces"* — intake extracts the
   material/reaction and the run replies with the proposal (full mode also writes
   `report.md`).

Set `PAPER_SEARCH_PROVIDER=openai`, `anthropic`, or `openai-oauth` in `.env` for
the full agent; otherwise it runs deterministically.

## MCP server

The agent is also exposed as an [MCP](https://modelcontextprotocol.io) tool, so
MCP-aware clients (Claude, Codex, etc.) can call it:

```bash
uv run --extra mcp paper-search-mcp
```

This starts a stdio MCP server (`paper_search.mcp_server`) exposing
`propose_surface_models(material, reaction, prompt?, provider?, model?, out_dir?)`,
which runs the graph and returns the proposal (mode, rounds, counts, opportunity
report, and `report_markdown` in full mode).

## Without Studio

- **Static diagram:** `compiled.get_graph().draw_mermaid()` renders the node
  graph as Mermaid.
- **Live progress in code:** `CatalystLiteratureGraph(config).stream(material,
  reaction)` yields per-node state updates as the graph runs.

See [Agent graph](../architecture/agent-graph.md) for the node map.
