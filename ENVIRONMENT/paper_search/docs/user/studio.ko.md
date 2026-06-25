# LangGraph Studio

그래프를 LangGraph Studio에서 노드 단위로 실행하고 살펴볼 수 있습니다.

```bash
uv run --extra studio langgraph dev --allow-blocking
```

`--allow-blocking`은 필수입니다: SearchAgent 파이프라인은 **동기(synchronous)**
방식(파일 I/O, urllib, sleep)이라, dev 서버 기본값인 `blockbuster`가 이벤트 루프의
blocking I/O를 막아 `BlockingError`를 냅니다.

로컬 dev 서버가 시작되고 Studio URL을 출력합니다(예:
`https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024`). 열어서 실행
입력을 JSON으로 제공합니다.

```json
{"material": "RuO2", "reaction": "HER", "extra_terms": [],
 "research_context": {}, "harness_errors": [], "resume_events": []}
```

Studio에서는 9개 노드를 단계별로 진행하고, 각 노드 이후의 state를 들여다보며, 입력을
바꿔 재실행할 수 있습니다.

Studio에서 [풀 에이전트](full-agent.md)로 구동하려면 `.env`에
`PAPER_SEARCH_PROVIDER=openai`, `anthropic`, 또는 `openai-oauth`를 설정하세요. 없으면
deterministic으로 동작합니다. 진입점은 `langgraph.json` →
`paper_search.agent.studio:make_graph`이며, 런타임 services를 빌드해 컴파일된 그래프를
반환합니다.

!!! note
    Studio의 dev 서버는 자체 serializer로 state를 직렬화하며 `Paper` / `SurfaceClaim`
    dataclass에 대해 "unregistered type" 경고를 남길 수 있습니다. 현재 LangGraph
    버전에서는 정상 동작합니다.

!!! warning "Failed to fetch / 연결 안 됨"
    호스티드 Studio 페이지는 HTTPS인데 dev 서버는 `http://127.0.0.1:2024`입니다.
    HTTPS→localhost를 막는 브라우저(Safari, Brave, Firefox)는 *"Failed to fetch"*가
    납니다. URL을 **Chrome**(localhost 허용)에서 열거나, 서버를
    `langgraph dev --allow-blocking --tunnel`로 띄워 출력되는 HTTPS 터널 URL을 쓰세요.

## Agent Chat UI

이 그래프는 [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui)와도
동작합니다. state에 `messages` 채널이 있어서, `intake` 노드가 채팅 메시지에서
material/reaction(및 연구 방향)을 파싱하고, 에이전트가 리포트를 assistant 메시지로
답합니다.

1. 그래프 서버 시작: `uv run --extra studio langgraph dev --allow-blocking`.
2. Agent Chat UI 실행(`npx create-agent-chat-app`, 또는 호스티드
   [agentchat.vercel.app](https://agentchat.vercel.app)).
3. deployment URL `http://localhost:2024`, graph ID `catalyst_literature`로 연결.
4. 예: *"RuO2 HER, 내구성 좋은 표면 위주로"* 라고 치면 intake가 material/reaction을
   뽑고 실행 결과를 답합니다(full 모드는 `report.md`도 작성).

full 에이전트로 돌리려면 `.env`에 `PAPER_SEARCH_PROVIDER=openai`, `anthropic`, 또는
`openai-oauth`를 설정하세요. 없으면 deterministic으로 동작합니다.

## MCP 서버

에이전트는 [MCP](https://modelcontextprotocol.io) 도구로도 노출되어, MCP를 지원하는
클라이언트(Claude, Codex 등)가 호출할 수 있습니다.

```bash
uv run --extra mcp paper-search-mcp
```

stdio MCP 서버(`paper_search.mcp_server`)가 시작되며
`propose_surface_models(material, reaction, prompt?, provider?, model?, out_dir?)`
도구를 노출합니다. 그래프를 실행해 제안(mode, rounds, 카운트, opportunity 리포트,
full 모드에서는 `report_markdown`)을 반환합니다.

## Studio 없이

- **정적 다이어그램:** `compiled.get_graph().draw_mermaid()`로 노드 그래프를 Mermaid로
  렌더링합니다.
- **코드에서 실시간 진행:** `CatalystLiteratureGraph(config).stream(material, reaction)`이
  그래프 실행 중 노드별 state 업데이트를 yield합니다.

노드 맵은 [에이전트 그래프](../architecture/agent-graph.md)를 참고하세요.
