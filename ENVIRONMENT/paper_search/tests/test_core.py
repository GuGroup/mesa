from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import os
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from paper_search.cache import PaperCache, SourceDownloader
from paper_search.config import PipelineConfig, ResearchConfig
from paper_search.dedup import dedupe_papers
from paper_search.extraction import extract_surface_claims
from paper_search.http import HttpClient, RetryPolicy
from paper_search.models import DownloadedSource, Paper, ParseRun, SourceLink, SurfaceClaim
from paper_search.opportunities import build_opportunity_report
from paper_search.parsers.jats import JatsParser
from paper_search.parsers.opendataloader import OpenDataLoaderParser
from paper_search.parsers.router import ParserRouter
from paper_search.agent.graph import CatalystLiteratureGraph, _route_after_gap
from paper_search.agent.llm import parse_json_response, provider_enabled
from paper_search.agent.nodes._helpers import new_record
from paper_search.agent.nodes.evidence_extraction import evidence_extraction_node
from paper_search.agent.nodes.intake import intake_node
from paper_search.agent.nodes.parse import parse_node
from paper_search.agent.nodes.relevance_grading import relevance_grading_node
from paper_search.agent.nodes.resolve_download import resolve_download_node
from paper_search.agent.nodes.search import search_node
from paper_search.agent.services import AgentServices
from paper_search.config import LlmConfig
from paper_search.planner import build_queries
from paper_search.resolvers import UnpaywallResolver
from paper_search.search import CrossrefSearch, OpenAlexSearch, SemanticScholarSearch
from paper_search.servers import ManagedServer, ManagedServerConfig
from paper_search.utils import normalize_doi, write_json


class CoreTests(unittest.TestCase):
    def test_normalize_doi(self) -> None:
        self.assertEqual(normalize_doi("https://doi.org/10.123/ABC."), "10.123/abc")
        self.assertEqual(normalize_doi("doi: 10.123/ABC"), "10.123/abc")

    def test_dedupe_papers_merges_sources(self) -> None:
        papers = [
            Paper(
                paper_id="a",
                doi="10.123/ABC",
                title="A paper",
                source_databases=["crossref"],
                topics=["Catalysis"],
                citation_count=4,
                provider_metadata={"crossref": {"score": 10}},
            ),
            Paper(
                paper_id="b",
                doi="https://doi.org/10.123/abc",
                title="A paper",
                abstract="abstract",
                source_databases=["openalex"],
                authors=["A. Researcher"],
                topics=["Surface science"],
                citation_count=9,
                is_open_access=True,
                oa_url="https://example.org/paper.pdf",
                provider_metadata={"openalex": {"oa_status": "gold"}},
            ),
        ]
        deduped = dedupe_papers(papers)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].abstract, "abstract")
        self.assertEqual(deduped[0].source_databases, ["crossref", "openalex"])
        self.assertEqual(deduped[0].authors, ["A. Researcher"])
        self.assertEqual(deduped[0].topics, ["Catalysis", "Surface science"])
        self.assertEqual(deduped[0].citation_count, 9)
        self.assertEqual(deduped[0].is_open_access, True)
        self.assertEqual(deduped[0].oa_url, "https://example.org/paper.pdf")
        self.assertIn("crossref", deduped[0].provider_metadata)
        self.assertIn("openalex", deduped[0].provider_metadata)

    def test_http_client_retries_429_with_retry_after(self) -> None:
        calls = []
        sleeps = []

        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            if len(calls) == 1:
                headers = Message()
                headers["Retry-After"] = "0"
                raise HTTPError(
                    request.full_url,
                    429,
                    "Too Many Requests",
                    headers,
                    io.BytesIO(b"rate limited"),
                )
            return _FakeResponse(
                request.full_url,
                200,
                {"content-type": "application/json"},
                b'{"ok": true}',
            )

        client = HttpClient(
            retry_policy=RetryPolicy(max_attempts=2),
            opener=opener,
            sleeper=lambda seconds: sleeps.append(seconds),
        )
        response = client.get("https://example.org/test")
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [])
        self.assertEqual(client.retry_events[0]["status"], 429)
        self.assertEqual(client.retry_events[0]["sleep_seconds"], 0.0)

    def test_jats_parser_and_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml = root / "paper.xml"
            xml.write_text(
                """
                <article>
                  <front>
                    <article-meta>
                      <title-group><article-title>RuO2 HER surfaces</article-title></title-group>
                      <abstract><p>RuO2 is studied for HER.</p></abstract>
                    </article-meta>
                  </front>
                  <body>
                    <sec>
                      <title>Results</title>
                      <p>RuO2(110) surface shows HER activity with an overpotential of 42 mV.</p>
                    </sec>
                  </body>
                </article>
                """,
                encoding="utf-8",
            )
            run = JatsParser().parse("paper1", xml, root / "parses")
            self.assertEqual(run.status, "ok")
            claims = extract_surface_claims(
                blocks_path=run.output_path,
                material="RuO2",
                reaction="HER",
                output_dir=root / "extraction",
            )
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0].surface_text, "(110)")
            self.assertEqual(claims[0].value, "42")
            self.assertEqual(claims[0].unit, "mV")

    def test_elsevier_full_text_body_is_extracted(self) -> None:
        # An authenticated Elsevier full-text response is a ce:/xocs: document
        # whose body lives in <ce:para> under <ce:section>, not JATS <body>/<p>.
        # The parser must mine those paragraphs (and skip the abstract) so the
        # body clears the content-quality gate instead of yielding a stub.
        from paper_search.parsers.xml_blocks import parse_xml_blocks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            xml = root / "elsevier.xml"
            xml.write_text(
                """
                <full-text-retrieval-response
                    xmlns:ce="http://www.elsevier.com/xml/common/dtd"
                    xmlns:xocs="http://www.elsevier.com/xml/xocs/dtd">
                  <originalText>
                    <xocs:doc>
                      <xocs:serial-item>
                        <article>
                          <ce:abstract>
                            <ce:abstract-sec>
                              <ce:simple-para>Abstract: RuO2 for HER.</ce:simple-para>
                            </ce:abstract-sec>
                          </ce:abstract>
                          <body>
                            <ce:sections>
                              <ce:section>
                                <ce:section-title>Results</ce:section-title>
                                <ce:para>RuO2(110) surface shows HER activity with an overpotential of 42 mV.</ce:para>
                                <ce:para>Additional discussion of the measured trends across facets.</ce:para>
                              </ce:section>
                            </ce:sections>
                          </body>
                        </article>
                      </xocs:serial-item>
                    </xocs:doc>
                  </originalText>
                </full-text-retrieval-response>
                """,
                encoding="utf-8",
            )
            blocks = parse_xml_blocks(xml, "paper1", "jats")
            paragraphs = [b for b in blocks if b.block_type == "paragraph"]
            texts = [b.text for b in paragraphs]
            self.assertTrue(
                any("overpotential of 42 mV" in t for t in texts),
                f"body paragraph missing: {texts}",
            )
            self.assertTrue(any("Additional discussion" in t for t in texts))
            # The abstract paragraph must be excluded from the body blocks.
            self.assertFalse(any("Abstract: RuO2" in t for t in texts))
            # The Results section title is carried on the body paragraphs.
            self.assertTrue(
                any(b.section == "Results" for b in paragraphs),
                f"section title missing: {[b.section for b in paragraphs]}",
            )

    def test_abstract_only_is_not_a_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "claims.json"
            write_json(output, [])
            self.assertEqual(output.exists(), True)

    def test_managed_server_without_command_returns_existing_url(self) -> None:
        config = ManagedServerConfig(base_url="http://localhost:8070")
        with ManagedServer(config) as url:
            self.assertEqual(url, "http://localhost:8070")

    def test_managed_server_start_failure_is_optional(self) -> None:
        config = ManagedServerConfig(
            base_url="http://127.0.0.1:9",
            start_cmd="definitely-not-a-real-grobid-command",
        )
        server = ManagedServer(config)
        with server as url:
            self.assertIsNone(url)
        self.assertIsNotNone(server.startup_error)

    def test_parser_router_starts_grobid_lazily(self) -> None:
        config = ManagedServerConfig(
            base_url="http://127.0.0.1:9",
            start_cmd="definitely-not-a-real-grobid-command",
        )
        with ParserRouter(grobid_server_config=config) as router:
            self.assertFalse(router.grobid_initialized)
            self.assertIsNone(router.grobid_startup_error)

    def test_opendataloader_parser_uses_configured_cli_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            parser = OpenDataLoaderParser(command_template="false {input} {output_dir}")
            with patch.object(parser, "_run_python_api", return_value="api failed"):
                run = parser.parse("paper1", pdf, root / "out")
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.parser_name, "opendataloader")

    def test_opportunity_report_suggests_descriptor_gap(self) -> None:
        claims = [
            SurfaceClaim(
                paper_id="paper1",
                material="RuO2",
                reaction="HER",
                surface_text="(110)",
                evidence_text="RuO2(110) surface shows HER activity at 42 mV.",
                claim_type="activity",
                confidence=0.8,
                value="42",
                unit="mV",
            )
        ]
        report = build_opportunity_report(claims, material="RuO2", reaction="HER")
        self.assertEqual(report["surface_count"], 1)
        surface = report["candidate_surfaces"][0]
        self.assertEqual(surface["surface"], "(110)")
        self.assertEqual(surface["status"], "activity_evidence_descriptor_gap")
        self.assertIn("descriptor", surface["missing_claim_types"])
        suggestion_types = {
            suggestion["calculation_type"]
            for suggestion in report["calculation_suggestions"]
        }
        self.assertIn("descriptor_calculation", suggestion_types)
        self.assertEqual(report["run_level_gaps"], [])

    def test_opportunity_report_uses_research_context_for_priority(self) -> None:
        claims = [
            SurfaceClaim(
                paper_id="paper1",
                material="RuO2",
                reaction="HER",
                surface_text="(110)",
                evidence_text="RuO2(110) surface shows HER activity at 42 mV.",
                claim_type="activity",
                confidence=0.8,
                value="42",
                unit="mV",
            )
        ]
        research = ResearchConfig(
            prompt="Prioritize durability and dissolution gaps for collaborators.",
            constraints=["DFT budget is limited"],
        )
        report = build_opportunity_report(
            claims,
            material="RuO2",
            reaction="HER",
            research=research,
        )
        stability = [
            suggestion
            for suggestion in report["calculation_suggestions"]
            if suggestion["calculation_type"] == "surface_stability"
        ][0]
        self.assertEqual(stability["priority"], "high")
        self.assertEqual(
            report["research_context"]["prompt"],
            "Prioritize durability and dissolution gaps for collaborators.",
        )

    def test_planner_uses_research_prompt_terms(self) -> None:
        research = ResearchConfig(
            prompt="Prioritize durability and alkaline electrolyte stability gaps.",
        )
        queries = build_queries("RuO2", "HER", research=research)
        self.assertTrue(any("durability" in query for query in queries))

    def test_pipeline_config_reads_omegaconf_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "paper-search.yaml"
            config_path.write_text(
                """
                email: config@example.org
                search:
                  per_query_limit: 3
                  max_papers: 7
                http:
                  timeout: 45
                  retry:
                    max_attempts: 6
                    backoff_seconds: [1, 2, 3]
                execution:
                  resume: false
                llm:
                  provider: openai
                  model: gpt-test
                research:
                  prompt: YAML prompt
                  decision_criteria:
                    - close descriptor gaps
                """,
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = PipelineConfig.from_sources(
                    output_dir=root / "out",
                    config_path=config_path,
                    per_query_limit=5,
                    research_prompt="CLI prompt",
                    cwd=root,
                )
            self.assertEqual(config.email, "config@example.org")
            self.assertEqual(config.per_query_limit, 5)
            self.assertEqual(config.max_papers, 7)
            self.assertEqual(config.timeout, 45)
            self.assertEqual(config.http_retry.max_attempts, 6)
            self.assertEqual(config.http_retry.backoff_seconds, [1.0, 2.0, 3.0])
            self.assertEqual(config.resume, False)
            self.assertIsNotNone(config.llm)
            self.assertEqual(config.llm.provider, "openai")
            self.assertEqual(config.llm.model, "gpt-test")
            self.assertEqual(config.research.prompt, "CLI prompt")
            self.assertEqual(config.research.decision_criteria, ["close descriptor gaps"])

    def test_pipeline_config_defaults_streamlined_parser_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                config = PipelineConfig.from_sources(output_dir=root / "out", cwd=root)
            self.assertIsNone(config.grobid_url)
            self.assertIsNone(config.grobid_start_cmd)
            self.assertEqual(config.grobid_startup_timeout, 120)
            self.assertEqual(
                config.opendataloader_cmd,
                "opendataloader-pdf {input} {output_dir}",
            )

    def test_pipeline_config_supports_oc_env_interpolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "paper-search.yaml"
            config_path.write_text(
                """
                email: ${oc.env:PAPER_SEARCH_EMAIL,""}
                semantic_scholar:
                  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
                """,
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "PAPER_SEARCH_EMAIL": "env@example.org",
                    "SEMANTIC_SCHOLAR_API_KEY": "semantic-key",
                },
                clear=True,
            ):
                config = PipelineConfig.from_sources(
                    output_dir=root / "out",
                    config_path=config_path,
                    cwd=root,
                )
            self.assertEqual(config.email, "env@example.org")
            self.assertEqual(config.semantic_scholar_api_key, "semantic-key")

    def test_pipeline_config_auto_loads_workdir_config_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.yaml").write_text(
                """
                search:
                  max_papers: 11
                parsers:
                  grobid:
                    startup_timeout: 5
                """,
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = PipelineConfig.from_sources(
                    output_dir=root / "out",
                    cwd=root,
                )
            self.assertEqual(config.max_papers, 11)
            self.assertEqual(config.grobid_startup_timeout, 5)

    def test_pipeline_config_loads_workdir_dotenv_for_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text(
                """
                PAPER_SEARCH_EMAIL=dotenv@example.org
                SEMANTIC_SCHOLAR_API_KEY=dotenv-semantic-key
                OPENAI_API_KEY=dotenv-openai-key
                """,
                encoding="utf-8",
            )
            config_path = root / "paper-search.yaml"
            config_path.write_text(
                """
                email: ${oc.env:PAPER_SEARCH_EMAIL,""}
                semantic_scholar:
                  api_key: ${oc.env:SEMANTIC_SCHOLAR_API_KEY,""}
                """,
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                config = PipelineConfig.from_sources(
                    output_dir=root / "out",
                    config_path=config_path,
                    cwd=root,
                )
                self.assertEqual(os.environ["OPENAI_API_KEY"], "dotenv-openai-key")
            self.assertEqual(config.email, "dotenv@example.org")
            self.assertEqual(config.semantic_scholar_api_key, "dotenv-semantic-key")

    def test_cache_reads_papers_and_surface_claims_for_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = PaperCache(root)
            paper = Paper(paper_id="paper1", title="A paper", doi="10.123/a")
            write_json(root / "papers.json", [paper.to_dict()])
            write_json(
                cache.extraction_dir(paper) / "surface_claims.json",
                [
                    SurfaceClaim(
                        paper_id="paper1",
                        material="RuO2",
                        reaction="HER",
                        surface_text="(110)",
                        evidence_text="evidence",
                        claim_type="activity",
                    ).to_dict()
                ],
            )
            self.assertEqual(cache.read_papers()[0].paper_id, "paper1")  # type: ignore[index]
            claims = cache.read_surface_claims(paper)
            self.assertIsNotNone(claims)
            self.assertEqual(claims[0].surface_text, "(110)")  # type: ignore[index]

    def test_graph_continues_after_per_paper_stage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # checkpoint=True exercises state serialization (Paper/SurfaceClaim
            # round-trip) through the LangGraph checkpointer. max_search_rounds=1
            # keeps this a single pass; relevance_filter=False skips grading.
            config = PipelineConfig(
                output_dir=root,
                max_papers=2,
                checkpoint=True,
                max_search_rounds=1,
                relevance_filter=False,
            )
            graph = CatalystLiteratureGraph(config)
            papers = [
                Paper(paper_id="bad", title="Bad parse"),
                Paper(paper_id="good", title="Good parse"),
            ]

            class _FakeSearch:
                name = "fake"

                def search(self, query, limit):
                    return list(papers)

            class _FakeResolver:
                name = "fake"

                def resolve(self, doi):
                    return [
                        SourceLink(
                            url="https://example.org/source.xml",
                            source_type="oa_xml",
                            resolver="test",
                        )
                    ]

            def fake_download(paper, links):
                source_path = root / f"{paper.paper_id}.xml"
                source_path.write_text("<article />", encoding="utf-8")
                return DownloadedSource(
                    paper_id=paper.paper_id,
                    source_type="oa_xml",
                    resolver="test",
                    source_url=links[0].url,
                    local_path=source_path,
                    checksum="checksum",
                )

            services = AgentServices.create(config)
            services.search_clients = [_FakeSearch()]
            services.resolvers = [_FakeResolver()]
            services.downloader.download_first_available = fake_download  # type: ignore[method-assign]
            services.parser_router = _FakeParserRouter(root)  # type: ignore[assignment]

            self.assertFalse(services.full_mode)
            checkpointer = graph._make_checkpointer()
            self.assertIsNotNone(checkpointer)
            compiled = graph.build(services, checkpointer=checkpointer)
            final = compiled.invoke(
                {
                    "material": "RuO2",
                    "reaction": "HER",
                    "extra_terms": [],
                    "research_context": {},
                    "full_mode": False,
                    "harness_errors": [],
                    "resume_events": [],
                },
                config={"configurable": {"thread_id": "test-thread"}},
            )
            result = final["result"]
            statuses = {item["paper"]["paper_id"]: item["status"] for item in result["processed"]}
            self.assertEqual(result["mode"], "deterministic")
            self.assertEqual(statuses["bad"], "extract_error")
            self.assertEqual(statuses["good"], "ok")
            self.assertEqual(result["surface_claim_count"], 1)
            self.assertEqual(result["harness"]["error_count"], 1)
            self.assertEqual(result["harness"]["errors"][0]["stage"], "extract")
            self.assertEqual((root / "run_manifest.json").exists(), True)

    def test_gap_driven_loop_accumulates_and_terminates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(
                output_dir=root,
                max_papers=10,
                max_search_rounds=2,
                relevance_filter=False,
                resume=False,
            )
            graph = CatalystLiteratureGraph(config)
            paper_a = Paper(paper_id="A", title="Paper A")
            paper_b = Paper(paper_id="B", title="Paper B")
            paper_c = Paper(paper_id="C", title="Paper C")
            gap_markers = ("descriptor", "binding", "free energy", "stability", "dissolution")

            class _RoundFakeSearch:
                name = "fake"

                def search(self, query, limit):
                    q = query.lower()
                    if any(m in q for m in gap_markers):
                        return [paper_c]  # round-2 gap-targeted hit
                    return [paper_a, paper_b]

            class _FakeResolver:
                name = "fake"

                def resolve(self, doi):
                    return [
                        SourceLink(
                            url="https://example.org/s.xml",
                            source_type="oa_xml",
                            resolver="t",
                        )
                    ]

            def fake_download(paper, links):
                path = root / f"{paper.paper_id}.xml"
                path.write_text("<article />", encoding="utf-8")
                return DownloadedSource(
                    paper_id=paper.paper_id,
                    source_type="oa_xml",
                    resolver="t",
                    source_url=links[0].url,
                    local_path=path,
                    checksum="c",
                )

            services = AgentServices.create(config)
            services.search_clients = [_RoundFakeSearch()]
            services.resolvers = [_FakeResolver()]
            services.downloader.download_first_available = fake_download  # type: ignore[method-assign]
            services.parser_router = _FakeParserRouter(root)  # type: ignore[assignment]
            compiled = graph.build(services)
            final = compiled.invoke(
                {
                    "material": "RuO2",
                    "reaction": "HER",
                    "extra_terms": [],
                    "research_context": {},
                    "full_mode": False,
                    "harness_errors": [],
                    "resume_events": [],
                },
                config={"recursion_limit": 60},
            )
            result = final["result"]
            self.assertEqual(result["rounds"], 2)  # looped once, then stopped
            self.assertEqual(result["paper_count"], 3)  # A,B then C accumulated
            # one claim per paper; 3 (not 5) proves round-2 did not re-extract A,B
            self.assertEqual(result["surface_claim_count"], 3)
            statuses = {r["paper"]["paper_id"]: r["status"] for r in result["processed"]}
            self.assertEqual(statuses, {"A": "ok", "B": "ok", "C": "ok"})

    def test_route_after_gap_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(
                output_dir=Path(tmp), max_search_rounds=3, min_new_papers_to_continue=1
            )
            services = AgentServices.create(config)
            route = _route_after_gap(services)
            base = {
                "round": 1,
                "coverage": {"has_gaps": True},
                "new_papers_last_round": 2,
                "gap_queries": ["q"],
            }
            self.assertEqual(route(base), "query_planner")
            self.assertEqual(route({**base, "new_papers_last_round": 0}), "report_writer")
            self.assertEqual(route({**base, "round": 3}), "report_writer")
            self.assertEqual(
                route({**base, "coverage": {"has_gaps": False}}), "report_writer"
            )
            self.assertEqual(route({**base, "gap_queries": []}), "report_writer")

    def test_relevance_grading_drops_off_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp))  # relevance_filter on, provider none
            services = AgentServices.create(config)
            papers = [
                Paper(paper_id="r1", title="RuO2(110) HER activity"),
                Paper(
                    paper_id="off",
                    title="Cobalt oxide ORR catalyst",
                    abstract="Co3O4 spinel for oxygen reduction.",
                ),
            ]
            out = relevance_grading_node(
                {"papers": papers, "graded": {}, "material": "RuO2", "reaction": "HER"},
                services=services,
            )
            self.assertTrue(out["graded"]["r1"])
            self.assertFalse(out["graded"]["off"])

    def test_relevance_grading_recall_floor_overrides_llm_drop(self) -> None:
        # An LLM that drops everything must NOT be able to drop a clear
        # target-material match in lenient mode (the floor), while a non-material
        # paper it drops stays dropped.
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp))
            services = AgentServices.create(config)
            services.full_mode = True  # type: ignore[misc]
            services.chat_model = _FakeChatModel("[]")  # grades nothing relevant
            papers = [
                Paper(
                    paper_id="ruo2-oer",
                    title="Impact of Ni doping on RuO2 electrocatalyst for OER",
                    abstract="RuO2 surface stability under oxygen evolution.",
                ),
                Paper(
                    paper_id="other",
                    title="Cobalt oxide ORR catalyst",
                    abstract="Co3O4 spinel for oxygen reduction.",
                ),
            ]
            out = relevance_grading_node(
                {"papers": papers, "graded": {}, "material": "RuO2", "reaction": "HER"},
                services=services,
            )
            # RuO2 named -> floor rescues it despite the LLM "off-topic" verdict.
            self.assertTrue(out["graded"]["ruo2-oer"])
            # No target material -> LLM drop stands.
            self.assertFalse(out["graded"]["other"])

    def test_field_scope_adds_reaction_centric_queries(self) -> None:
        from paper_search.planner import build_queries

        off = build_queries("RuO2", "HER", field_scope="off")
        react = build_queries("RuO2", "HER", field_scope="reaction")
        fam = build_queries("RuO2", "HER", field_scope="reaction+family")
        # Field queries are reaction-centric and material-agnostic.
        self.assertTrue(any("descriptor" in q and "RuO2" not in q for q in react))
        self.assertGreater(len(react), len(off))
        self.assertGreater(len(fam), len(react))
        # Off scope keeps only the original material-bound queries.
        self.assertFalse(any("RuO2" not in q for q in off))

    def test_relevance_field_floor_keeps_same_reaction_other_system(self) -> None:
        # field_scope on: an LLM that drops everything must not drop a same-reaction
        # paper on a different system that carries a surface/descriptor signal.
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp), field_scope="reaction")
            services = AgentServices.create(config)
            services.full_mode = True  # type: ignore[misc]
            services.chat_model = _FakeChatModel("[]")
            papers = [
                Paper(
                    paper_id="field",
                    title="Pt(111) hydrogen adsorption free energy descriptor for HER",
                    abstract="DFT d-band center analysis of HER on Pt surfaces.",
                ),
                Paper(
                    paper_id="noise",
                    title="Lithium-ion battery cathode degradation",
                    abstract="Capacity fade in NMC cells.",
                ),
            ]
            out = relevance_grading_node(
                {"papers": papers, "graded": {}, "material": "RuO2", "reaction": "HER"},
                services=services,
            )
            self.assertTrue(out["graded"]["field"])   # transferable field paper
            self.assertFalse(out["graded"]["noise"])  # unrelated -> dropped

        # field_scope off: the same field paper is NOT rescued.
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp), field_scope="off")
            services = AgentServices.create(config)
            services.full_mode = True  # type: ignore[misc]
            services.chat_model = _FakeChatModel("[]")
            out = relevance_grading_node(
                {
                    "papers": [
                        Paper(
                            paper_id="field",
                            title="Pt(111) hydrogen adsorption free energy for HER",
                            abstract="DFT d-band center HER.",
                        )
                    ],
                    "graded": {},
                    "material": "RuO2",
                    "reaction": "HER",
                },
                services=services,
            )
            self.assertFalse(out["graded"]["field"])

    def test_relevance_filter_modes(self) -> None:
        from paper_search.agent.nodes.relevance_grading import _mode, _rule_relevant

        # normalization (incl. legacy bool)
        self.assertEqual(_mode(True), "lenient")
        self.assertEqual(_mode(False), "off")
        self.assertEqual(_mode("off"), "off")
        self.assertEqual(_mode("strict"), "strict")
        self.assertEqual(_mode("lenient"), "lenient")

        # reaction-on-topic but material absent: lenient keeps, strict drops
        p = Paper(
            paper_id="x",
            title="Hydrogen evolution reaction on metal oxides",
            abstract="HER electrocatalysis study",
        )
        self.assertTrue(_rule_relevant(p, "RuO2", "HER", "lenient"))
        self.assertFalse(_rule_relevant(p, "RuO2", "HER", "strict"))

        # off mode keeps everything (even clearly off-topic)
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp), relevance_filter="off")
            services = AgentServices.create(config)
            out = relevance_grading_node(
                {
                    "papers": [Paper(paper_id="o", title="Lithium battery", abstract="x")],
                    "graded": {},
                    "material": "RuO2",
                    "reaction": "HER",
                },
                services=services,
            )
            self.assertTrue(out["graded"]["o"])

    def test_intake_rule_parses_material_and_reaction(self) -> None:
        from langchain_core.messages import HumanMessage

        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp))  # provider none -> rule parse
            services = AgentServices.create(config)
            out = intake_node(
                {"messages": [HumanMessage(content="RuO2 HER durability gaps")]},
                services=services,
            )
            self.assertEqual(out["material"], "RuO2")
            self.assertEqual(out["reaction"], "HER")
            # already-provided material/reaction => no-op
            self.assertEqual(
                intake_node(
                    {"material": "Pt", "reaction": "ORR", "messages": [HumanMessage(content="x")]},
                    services=services,
                ),
                {},
            )

    def test_chat_mode_runs_from_messages_and_replies(self) -> None:
        from langchain_core.messages import AIMessage, HumanMessage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(output_dir=root, max_search_rounds=1, resume=False)
            graph = CatalystLiteratureGraph(config)
            paper = Paper(paper_id="p1", title="RuO2(110) HER surfaces")

            class _FakeSearch:
                name = "fake"

                def search(self, query, limit):
                    return [paper]

            class _FakeResolver:
                name = "fake"

                def resolve(self, doi):
                    return [
                        SourceLink(
                            url="https://example.org/s.xml",
                            source_type="oa_xml",
                            resolver="t",
                        )
                    ]

            def fake_download(p, links):
                path = root / f"{p.paper_id}.xml"
                path.write_text("<article />", encoding="utf-8")
                return DownloadedSource(
                    paper_id=p.paper_id,
                    source_type="oa_xml",
                    resolver="t",
                    source_url=links[0].url,
                    local_path=path,
                    checksum="c",
                )

            services = AgentServices.create(config)
            services.search_clients = [_FakeSearch()]
            services.resolvers = [_FakeResolver()]
            services.downloader.download_first_available = fake_download  # type: ignore[method-assign]
            services.parser_router = _FakeParserRouter(root)  # type: ignore[assignment]
            compiled = graph.build(services)
            final = compiled.invoke(
                {
                    "messages": [HumanMessage(content="RuO2 HER surface modeling")],
                    "extra_terms": [],
                    "research_context": {},
                    "full_mode": False,
                    "harness_errors": [],
                    "resume_events": [],
                },
                config={"recursion_limit": 40},
            )
            # intake parsed material/reaction from the chat message
            self.assertEqual(final["result"]["material"], "RuO2")
            self.assertEqual(final["result"]["reaction"], "HER")
            # the agent replied with an AIMessage in the transcript
            self.assertTrue(any(isinstance(m, AIMessage) for m in final["messages"]))

    def test_mcp_server_module_is_import_safe(self) -> None:
        # Importable even without the mcp extra; building the server needs it.
        import paper_search.mcp_server as mcp_server

        self.assertTrue(hasattr(mcp_server, "build_server"))

    @unittest.skipUnless(
        importlib.util.find_spec("mcp"), "mcp extra not installed"
    )
    def test_mcp_server_exposes_tool(self) -> None:
        from paper_search.mcp_server import build_server

        server = build_server()
        tools = asyncio.run(server.list_tools())
        self.assertIn("propose_surface_models", {t.name for t in tools})

    def test_resolve_output_dir_defaults_to_session(self) -> None:
        from paper_search.config import resolve_output_dir

        # explicit --out always wins
        self.assertEqual(
            resolve_output_dir(Path("/tmp/explicit"), "RuO2", "HER"),
            Path("/tmp/explicit"),
        )
        with patch.dict(os.environ, {"SEARCHAGENT_HOME": "/tmp/sahome"}, clear=False):
            auto = resolve_output_dir(None, "RuO2", "HER")
            self.assertEqual(auto.parent, Path("/tmp/sahome") / "sessions")
            self.assertTrue(auto.name.startswith("ruo2_her_"))
            named = resolve_output_dir(None, "RuO2", "HER", session="myrun")
            self.assertEqual(named, Path("/tmp/sahome") / "sessions" / "myrun")

    def test_blocks_to_text_accepts_str_path(self) -> None:
        from paper_search.agent.nodes._helpers import blocks_to_text

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jats.blocks.json"
            write_json(
                path,
                [
                    {"paper_id": "x", "block_type": "paragraph",
                     "text": "RuO2(110) HER activity.", "section": "Results"},
                    {"paper_id": "x", "block_type": "paragraph", "text": "Second block."},
                ],
            )
            # Regression: parse node passes str(blocks_path); read_json needs Path.
            for arg in (str(path), path):
                text = blocks_to_text(arg)
                self.assertIn("RuO2(110) HER activity.", text)
                self.assertIn("Second block.", text)

    def test_graph_compiles_with_default_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp))
            graph = CatalystLiteratureGraph(config)
            services = AgentServices.create(config)
            compiled = graph.build(services)
            node_names = set(compiled.get_graph().nodes)
            for name in ("query_planner", "evidence_extraction", "report_writer"):
                self.assertIn(name, node_names)

    def test_parse_json_response_handles_fences_and_garbage(self) -> None:
        self.assertEqual(parse_json_response("```json\n[1, 2]\n```"), [1, 2])
        self.assertEqual(parse_json_response('[{"a": 1}]'), [{"a": 1}])
        self.assertEqual(parse_json_response("prefix [3] suffix"), [3])
        self.assertIsNone(parse_json_response("no json here"))

    def test_provider_enabled_requires_key(self) -> None:
        self.assertFalse(provider_enabled(LlmConfig(provider="none")))
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(provider_enabled(LlmConfig(provider="anthropic")))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x"}, clear=True):
            self.assertTrue(provider_enabled(LlmConfig(provider="anthropic")))

    def test_full_mode_llm_extraction_parses_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(output_dir=root)
            services = AgentServices.create(config)
            services.full_mode = True
            services.provider = "anthropic"
            payload = json.dumps(
                [
                    {
                        "surface_text": "(110)",
                        "evidence_text": "RuO2(110) shows HER activity at 42 mV.",
                        "claim_type": "activity",
                        "value": "42",
                        "unit": "mV",
                        "confidence": 0.8,
                    }
                ]
            )
            services.chat_model = _FakeChatModel(payload)  # type: ignore[assignment]

            paper = Paper(paper_id="p1", title="RuO2 HER", doi=None)
            record = new_record(paper)
            record["status"] = "parsed"
            state = {
                "material": "RuO2",
                "reaction": "HER",
                "research_context": {},
                "papers": [paper],
                "processed": [record],
                "parsed_texts": {"p1": "RuO2(110) shows HER activity at 42 mV."},
                "blocks_paths": {},
                "claims": [],
                "harness_errors": [],
                "resume_events": [],
            }
            out = evidence_extraction_node(state, services=services)
            claims = out["claims"]
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0].surface_text, "(110)")
            self.assertEqual(claims[0].claim_type, "activity")
            self.assertEqual(claims[0].value, "42")
            self.assertEqual(out["processed"][0]["status"], "ok")
            self.assertTrue(
                (services.cache.extraction_dir(paper) / "surface_claims.json").exists()
            )

    def test_llm_extraction_captures_field_level_claim(self) -> None:
        # A claim about a DIFFERENT system/reaction with a descriptor + method but
        # no facet must still be kept, enum-normalized, and tagged as transferable.
        with tempfile.TemporaryDirectory() as tmp:
            config = PipelineConfig(output_dir=Path(tmp))
            services = AgentServices.create(config)
            services.full_mode = True
            services.provider = "anthropic"
            payload = json.dumps(
                [
                    {
                        "system": "Pt(111)",
                        "reaction": "her",  # lowercase -> normalized to HER
                        "surface_text": None,
                        "descriptor": "ΔG_H",  # not in vocab -> 'other'
                        "method": "DFT_CHE",  # case-insensitive match
                        "claim": "Near-thermoneutral H binding maximizes HER rate.",
                        "evidence_text": "Pt(111) binds H near 0 eV, optimal for HER.",
                        "claim_type": "descriptor_activity_relation",
                        "confidence": 0.7,
                    }
                ]
            )
            services.chat_model = _FakeChatModel(payload)  # type: ignore[assignment]
            paper = Paper(paper_id="p9", title="HER descriptors", doi=None)
            record = new_record(paper)
            record["status"] = "parsed"
            state = {
                "material": "RuO2",
                "reaction": "HER",
                "research_context": {},
                "papers": [paper],
                "processed": [record],
                "parsed_texts": {"p9": "Pt(111) binds H near 0 eV, optimal for HER."},
                "blocks_paths": {},
                "claims": [],
                "harness_errors": [],
                "resume_events": [],
            }
            c = evidence_extraction_node(state, services=services)["claims"][0]
            self.assertEqual(c.system, "Pt(111)")
            self.assertEqual(c.method, "dft_che")
            self.assertEqual(c.descriptor, "other")  # unknown token folded
            self.assertEqual(c.claim_type, "descriptor_activity_relation")
            self.assertEqual(c.surface_text, "")  # no facet, still kept
            # Different material, same reaction -> transferable field evidence.
            self.assertEqual(c.relation_to_target, "same_reaction")

    def test_parse_gate_marks_title_only_as_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(output_dir=root, resume=False)
            services = AgentServices.create(config)

            class _StubRouter:
                def parse(self, paper, source, output_dir):
                    output_dir.mkdir(parents=True, exist_ok=True)
                    blocks_path = output_dir / "jats.blocks.json"
                    # Title-only stub, like an unauthenticated Elsevier coredata.
                    write_json(
                        blocks_path,
                        [
                            {
                                "paper_id": paper.paper_id,
                                "parse_id": "jats",
                                "block_type": "title",
                                "text": "Dynamic electron buffering at Ru/RuO2 "
                                "heterointerfaces during HER",
                            }
                        ],
                    )
                    return [
                        ParseRun(
                            paper_id=paper.paper_id,
                            parser_name="jats",
                            output_format="blocks_json",
                            output_path=blocks_path,
                            status="ok",
                        )
                    ]

            services.parser_router = _StubRouter()  # type: ignore[assignment]

            paper = Paper(paper_id="p1", title="T", doi=None)
            record = new_record(paper)
            record["status"] = "downloaded"
            source = DownloadedSource(
                paper_id="p1",
                source_type="oa_xml",
                resolver="crossref_tdm",
                source_url="https://api.elsevier.com/content/article/x",
                local_path=root / "x.xml",
                checksum="c",
            )
            state = {
                "papers": [paper],
                "processed": [record],
                "downloaded_sources": {"p1": source.to_dict()},
                "blocks_paths": {},
                "parsed_texts": {},
                "harness_errors": [],
                "resume_events": [],
            }
            out = parse_node(state, services=services)
            self.assertEqual(out["processed"][0]["status"], "full_text_unavailable")
            self.assertNotIn("p1", out["parsed_texts"])
            self.assertLess(out["processed"][0]["parsed_char_count"], 500)

    def test_grobid_parse_error_returns_failed_run_not_raises(self) -> None:
        from paper_search.parsers.grobid import GrobidParser

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf = root / "p.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            parser = GrobidParser("http://localhost:8070")
            # GROBID answered HTTP 200 with a non-TEI body (e.g. an error page);
            # parse_xml_blocks raises ET.ParseError. It must become a failed
            # ParseRun so the router can still fall back to OpenDataLoader.
            with patch.object(
                parser, "_process_pdf", return_value=b"Access denied: rate limited"
            ):
                run = parser.parse("p1", pdf, root / "out")
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.parser_name, "grobid")

    def test_best_blocks_path_skips_empty_parse(self) -> None:
        from paper_search.parsers.router import best_blocks_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grobid_blocks = root / "grobid.blocks.json"
            odl_blocks = root / "opendataloader.blocks.json"
            write_json(grobid_blocks, [])
            write_json(odl_blocks, [{"paper_id": "p", "text": "x"}])
            runs = [
                ParseRun(
                    paper_id="p",
                    parser_name="grobid",
                    output_format="blocks_json",
                    output_path=grobid_blocks,
                    status="ok",
                    parse_quality={"block_count": 0},
                ),
                ParseRun(
                    paper_id="p",
                    parser_name="opendataloader",
                    output_format="blocks_json",
                    output_path=odl_blocks,
                    status="ok",
                    parse_quality={"block_count": 3},
                ),
            ]
            # An empty (0-block) GROBID parse must not win over a non-empty one.
            self.assertEqual(best_blocks_path(runs), odl_blocks)

    def test_search_ignores_empty_cached_papers_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(output_dir=root, resume=True, max_papers=5)
            services = AgentServices.create(config)
            # A prior failed round-1 search left an empty papers.json behind.
            write_json(root / "papers.json", [])

            class _FakeSearch:
                name = "fake"

                def search(self, query, limit):
                    return [Paper(paper_id="p1", title="RuO2 HER")]

            services.search_clients = [_FakeSearch()]
            out = search_node({"queries": ["q"], "round": 1}, services=services)
            # It re-searched instead of reusing the empty cache.
            self.assertEqual([p.paper_id for p in out["papers"]], ["p1"])
            self.assertNotIn(
                {"stage": "search", "status": "reused_papers_json"},
                out.get("resume_events", []),
            )

    def test_resolve_download_ignores_stale_errors_without_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(output_dir=root, resume=False)
            services = AgentServices.create(config)
            paper = Paper(paper_id="p1", title="T", doi="10.1/a")
            # Stale error log from a previous run must be ignored with --no-resume.
            write_json(
                services.cache.sources_dir(paper) / "download_errors.json",
                [{"url": "x", "error_type": "E", "error": "old"}],
            )

            class _FakeResolver:
                name = "fake"

                def resolve(self, doi):
                    return [
                        SourceLink(
                            url="https://x/p.pdf", source_type="oa_pdf", resolver="t"
                        )
                    ]

            services.resolvers = [_FakeResolver()]
            services.downloader.download_first_available = lambda p, links: None
            out = resolve_download_node(
                {"papers": [paper], "graded": {}, "processed": []}, services=services
            )
            record = out["processed"][0]
            self.assertEqual(record["download_errors"], [])
            self.assertEqual(record["status"], "full_text_unavailable")

    def test_resolve_download_does_not_cache_total_resolver_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = PipelineConfig(output_dir=root, resume=True)
            services = AgentServices.create(config)
            paper = Paper(paper_id="p1", title="T", doi="10.1/a")

            class _BoomResolver:
                name = "boom"

                def resolve(self, doi):
                    raise RuntimeError("resolver down")

            services.resolvers = [_BoomResolver()]
            services.downloader.download_first_available = lambda p, links: None
            out = resolve_download_node(
                {"papers": [paper], "graded": {}, "processed": []}, services=services
            )
            # Every resolver errored -> [] must not be persisted, so a later
            # resume re-resolves instead of trusting a transient no-link verdict.
            self.assertFalse(
                (services.cache.sources_dir(paper) / "resolved_links.json").exists()
            )
            self.assertTrue(out["processed"][0]["resolver_errors"])

    def test_resolver_chain_skips_fallback_when_oa_found(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.resolve_download import _resolve

        class _Primary:
            name = "primary"

            def resolve(self, doi):
                return [
                    SourceLink(
                        url="https://oa/p.pdf", source_type="oa_pdf", resolver="primary"
                    )
                ]

        class _Fallback:
            name = "fallback"
            fallback = True

            def __init__(self):
                self.called = False

            def resolve(self, doi):
                self.called = True
                return [
                    SourceLink(
                        url="https://sh/p.pdf", source_type="oa_pdf", resolver="fallback"
                    )
                ]

        fb = _Fallback()
        services = SimpleNamespace(resolvers=[_Primary(), fb])
        links, errors = _resolve(services, Paper(paper_id="p", title="T", doi="10.1/a"))
        # OA link found -> the unreliable fallback (Sci-Hub) is never contacted.
        self.assertFalse(fb.called)
        self.assertEqual([link.resolver for link in links], ["primary"])

    def test_recover_fulltext_retries_fallback_once(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.parse import _recover_fulltext

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = Paper(paper_id="p", title="T", doi="10.1/a")

            class _Fallback:
                name = "scihub"
                fallback = True

                def __init__(self):
                    self.calls = 0

                def resolve(self, doi):
                    self.calls += 1
                    return [
                        SourceLink(
                            url="https://sh/p.pdf",
                            source_type="oa_pdf",
                            resolver="scihub",
                        )
                    ]

            fb = _Fallback()
            downloads: list[bool] = []

            def fake_download(paper, links, force=False):
                downloads.append(force)
                path = root / "recovered.xml"
                path.write_text("<article />", encoding="utf-8")
                return DownloadedSource(
                    paper_id=paper.paper_id,
                    source_type="oa_pdf",
                    resolver="scihub",
                    source_url=links[0].url,
                    local_path=path,
                    checksum="x",
                )

            services = SimpleNamespace(
                resolvers=[fb],
                downloader=SimpleNamespace(download_first_available=fake_download),
                parser_router=_FakeParserRouter(root),
                cache=SimpleNamespace(parses_dir=lambda p: root / "parses"),
                config=SimpleNamespace(min_full_text_chars=2000),
                full_mode=False,
            )

            record = {
                **new_record(paper),
                "status": "full_text_unavailable",
            }
            processed = [record]
            blocks_paths: dict[str, str] = {}
            parsed_texts: dict[str, str] = {}
            harness_errors: list[dict[str, str]] = []

            _recover_fulltext(
                services, processed, {paper.paper_id: paper}, blocks_paths,
                parsed_texts, harness_errors,
            )

            self.assertEqual(record["status"], "parsed")
            self.assertTrue(record["fallback_attempted"])
            self.assertEqual(record["recovered_via"], "scihub")
            self.assertEqual(downloads, [True])  # forced past the resume cache
            self.assertIn(paper.paper_id, blocks_paths)

            # A second pass must not re-attempt the (now satisfied) recovery.
            _recover_fulltext(
                services, processed, {paper.paper_id: paper}, blocks_paths,
                parsed_texts, harness_errors,
            )
            self.assertEqual(fb.calls, 1)

    def test_scihub_resolver_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Default: Sci-Hub on -> exactly one fallback resolver is wired in.
            on = AgentServices.create(PipelineConfig(output_dir=root))
            self.assertEqual(
                sum(1 for r in on.resolvers if getattr(r, "fallback", False)), 1
            )
            # Disabled: no fallback resolver appears.
            off = AgentServices.create(
                PipelineConfig(output_dir=root, scihub_enabled=False)
            )
            self.assertFalse(
                any(getattr(r, "fallback", False) for r in off.resolvers)
            )

    def test_oa_index_links_prefer_provider_pdf(self) -> None:
        from paper_search.resolvers import oa_links_from_paper

        paper = Paper(
            paper_id="p",
            title="A preprint",
            doi="10.26434/chemrxiv-2024-abcde",
            oa_url="https://arxiv.org/abs/2401.00001",  # landing page (no ext)
            provider_metadata={
                "openalex": {
                    "pdf_url": "https://arxiv.org/pdf/2401.00001",
                    "landing_page_url": "https://arxiv.org/abs/2401.00001",
                }
            },
        )
        links = oa_links_from_paper(paper)
        # The direct PDF is surfaced; the abstract landing page is dropped.
        self.assertEqual([link.url for link in links], ["https://arxiv.org/pdf/2401.00001"])
        self.assertEqual(links[0].source_type, "oa_pdf")
        self.assertEqual(links[0].resolver, "oa_index")
        self.assertTrue(links[0].is_best)

    def test_oa_index_accepts_pdf_url_with_query_string(self) -> None:
        from paper_search.resolvers import oa_links_from_paper

        # Research Square / repository PDFs often carry a cache-busting query.
        paper = Paper(
            paper_id="p",
            title="Preprint with query-string PDF",
            oa_url="https://www.researchsquare.com/article/rs-1/v1.pdf?c=1631870895000",
        )
        links = oa_links_from_paper(paper)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].source_type, "oa_pdf")

    def test_oa_index_skips_landing_page_only(self) -> None:
        from paper_search.resolvers import oa_links_from_paper

        paper = Paper(
            paper_id="p",
            title="No direct PDF",
            oa_url="https://example.org/landing",  # not a pdf/xml
        )
        # Nothing that looks like full text -> no link (avoid saving HTML stubs).
        self.assertEqual(oa_links_from_paper(paper), [])

    def test_resolve_surfaces_preprint_oa_when_doi_resolvers_empty(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.resolve_download import _resolve

        class _EmptyPrimary:
            name = "unpaywall"

            def resolve(self, doi):
                return []  # arXiv DataCite DOI is absent from Unpaywall/Crossref

        paper = Paper(
            paper_id="p",
            title="arXiv preprint",
            doi="10.48550/arXiv.2401.00001",
            oa_url="https://arxiv.org/pdf/2401.00001",
        )
        services = SimpleNamespace(resolvers=[_EmptyPrimary()])
        links, errors = _resolve(services, paper)
        # The OA PDF the search index already had is now a primary source even
        # though the DOI-based resolver found nothing.
        self.assertEqual([link.resolver for link in links], ["oa_index"])
        self.assertEqual(links[0].url, "https://arxiv.org/pdf/2401.00001")
        self.assertEqual(errors, [])

    def test_primary_resolve_never_calls_fallback(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.resolve_download import _resolve

        class _EmptyPrimary:
            name = "primary"

            def resolve(self, doi):
                return []

        class _Fallback:
            name = "fallback"
            fallback = True

            def __init__(self):
                self.called = False

            def resolve(self, doi):
                self.called = True
                return [
                    SourceLink(
                        url="https://sh/p.pdf", source_type="oa_pdf", resolver="fallback"
                    )
                ]

        fb = _Fallback()
        services = SimpleNamespace(resolvers=[_EmptyPrimary(), fb])
        links, _ = _resolve(services, Paper(paper_id="p", title="T", doi="10.1/a"))
        # Fallback (Sci-Hub) is deferred to the parse-node recovery pass; the
        # primary resolve stage must never contact it, even with no primary link.
        self.assertFalse(fb.called)
        self.assertEqual(links, [])

    def test_resolve_fallback_links_uses_only_fallback_resolvers(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.resolve_download import resolve_fallback_links

        class _Primary:
            name = "primary"

            def __init__(self):
                self.called = False

            def resolve(self, doi):
                self.called = True
                return [
                    SourceLink(
                        url="https://oa/p.pdf", source_type="oa_pdf", resolver="primary"
                    )
                ]

        class _Fallback:
            name = "fallback"
            fallback = True

            def resolve(self, doi):
                return [
                    SourceLink(
                        url="https://sh/p.pdf", source_type="oa_pdf", resolver="fallback"
                    )
                ]

        primary = _Primary()
        services = SimpleNamespace(resolvers=[primary, _Fallback()])
        links, _ = resolve_fallback_links(
            services, Paper(paper_id="p", title="T", doi="10.1/a")
        )
        # The recovery pass only contacts fallback resolvers; primary OA
        # resolvers were already exhausted in the resolve stage.
        self.assertFalse(primary.called)
        self.assertEqual([link.resolver for link in links], ["fallback"])

    def test_resolve_fallback_links_empty_without_fallback(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.resolve_download import resolve_fallback_links

        class _Primary:
            name = "primary"
            fallback = False

            def resolve(self, doi):
                return [
                    SourceLink(
                        url="https://oa/p.pdf", source_type="oa_pdf", resolver="primary"
                    )
                ]

        services = SimpleNamespace(resolvers=[_Primary()])
        links, errors = resolve_fallback_links(
            services, Paper(paper_id="p", title="T", doi="10.1/a")
        )
        # Sci-Hub is configurable: with no fallback resolver configured the recovery
        # pass is a no-op.
        self.assertEqual(links, [])
        self.assertEqual(errors, [])

    def test_http_get_max_attempts_override_fails_fast(self) -> None:
        calls: list[int] = []
        sleeps: list[float] = []

        def opener(request, timeout):
            calls.append(1)
            raise HTTPError(
                request.full_url, 503, "busy", Message(), io.BytesIO(b"err")
            )

        client = HttpClient(
            retry_policy=RetryPolicy(max_attempts=4),
            opener=opener,
            sleeper=lambda seconds: sleeps.append(seconds),
        )
        # Per-call override beats the policy's 4 attempts: one try, no backoff.
        with self.assertRaises(RuntimeError):
            client.get("https://example.org/x", max_attempts=1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])


def _canned_http(payload: dict) -> HttpClient:
    body = json.dumps(payload).encode("utf-8")

    def opener(request, timeout):
        return _FakeResponse(
            request.full_url, 200, {"content-type": "application/json"}, body
        )

    return HttpClient(opener=opener)


class SearchClientTests(unittest.TestCase):
    def test_crossref_search_parses_items(self) -> None:
        http = _canned_http(
            {
                "message": {
                    "items": [
                        {
                            "DOI": "10.1/ABC",
                            "title": ["RuO2 HER surfaces"],
                            "container-title": ["J. Catalysis"],
                            "publisher": "ACS",
                            "URL": "https://doi.org/10.1/abc",
                            "score": 12.5,
                            "author": [{"given": "A.", "family": "Researcher"}],
                            "type": "journal-article",
                            "subject": ["Catalysis"],
                            "is-referenced-by-count": 7,
                            "published-print": {"date-parts": [[2021, 3, 1]]},
                        },
                        {"title": []},  # skipped: no title
                    ]
                }
            }
        )
        papers = CrossrefSearch(http).search("ruo2 her", limit=5)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper.doi, "10.1/abc")
        self.assertEqual(paper.title, "RuO2 HER surfaces")
        self.assertEqual(paper.year, 2021)
        self.assertEqual(paper.journal, "J. Catalysis")
        self.assertEqual(paper.citation_count, 7)
        self.assertEqual(paper.source_databases, ["crossref"])

    def test_openalex_search_parses_results(self) -> None:
        http = _canned_http(
            {
                "results": [
                    {
                        "title": "RuO2 HER surfaces",
                        "doi": "https://doi.org/10.1/ABC",
                        "publication_year": 2021,
                        "primary_location": {
                            "source": {
                                "display_name": "J. Cat",
                                "host_organization_name": "ACS",
                            }
                        },
                        "open_access": {
                            "is_oa": True,
                            "oa_url": "https://x.org/p.pdf",
                            "oa_status": "gold",
                        },
                        "id": "https://openalex.org/W1",
                        "cited_by_count": 9,
                        "type": "article",
                        "abstract_inverted_index": None,
                    }
                ]
            }
        )
        papers = OpenAlexSearch(http).search("ruo2 her", limit=5)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper.doi, "10.1/abc")
        self.assertEqual(paper.year, 2021)
        self.assertTrue(paper.is_open_access)
        self.assertEqual(paper.oa_url, "https://x.org/p.pdf")
        self.assertEqual(paper.citation_count, 9)
        self.assertEqual(paper.source_databases, ["openalex"])

    def test_semantic_scholar_search_parses_data(self) -> None:
        http = _canned_http(
            {
                "data": [
                    {
                        "paperId": "P1",
                        "title": "RuO2 HER surfaces",
                        "year": 2021,
                        "venue": "J Cat",
                        "url": "https://s2/p",
                        "externalIds": {"DOI": "10.1/ABC"},
                        "citationCount": 9,
                        "influentialCitationCount": 2,
                        "authors": [{"name": "A. Researcher"}],
                        "publicationTypes": ["JournalArticle"],
                        "fieldsOfStudy": ["Chemistry"],
                        "isOpenAccess": True,
                        "openAccessPdf": {"url": "https://x.org/p.pdf", "status": "GREEN"},
                    }
                ]
            }
        )
        papers = SemanticScholarSearch(http).search("ruo2 her", limit=5)
        self.assertEqual(len(papers), 1)
        paper = papers[0]
        self.assertEqual(paper.doi, "10.1/abc")
        self.assertEqual(paper.citation_count, 9)
        self.assertEqual(paper.influential_citation_count, 2)
        self.assertTrue(paper.is_open_access)
        self.assertEqual(paper.oa_url, "https://x.org/p.pdf")

    def test_unpaywall_resolver_parses_oa_locations(self) -> None:
        best = {
            "url_for_pdf": "https://x.org/p.pdf",
            "license": "cc-by",
            "version": "publishedVersion",
            "host_type": "publisher",
            "evidence": "oa repository",
        }
        http = _canned_http(
            {
                "best_oa_location": best,
                "oa_locations": [
                    {"url_for_pdf": "https://x.org/p.pdf"},  # duplicate -> deduped
                    {"url": "https://y.org/landing"},  # non-pdf/xml -> skipped
                ],
            }
        )
        links = UnpaywallResolver(http, email="x@example.org").resolve("10.1/abc")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].url, "https://x.org/p.pdf")
        self.assertEqual(links[0].resolver, "unpaywall")
        self.assertEqual(links[0].license, "cc-by")
        self.assertTrue(links[0].is_best)

    def test_semantic_scholar_throttles_to_rate_limit(self) -> None:
        clock = [100.0]
        sleeps: list[float] = []

        def fake_sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds

        http = _canned_http({"data": []})
        s2 = SemanticScholarSearch(
            http,
            api_key="k",
            min_request_interval=1.1,
            sleeper=fake_sleep,
            monotonic=lambda: clock[0],
        )
        s2.search("a")  # first request: no wait
        s2.search("b")  # within 1.1s window: must sleep ~1.1s
        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], 1.1, places=6)

    def test_search_query_cap_limits_slow_client(self) -> None:
        from types import SimpleNamespace

        from paper_search.agent.nodes.search import _search

        class _RecordingClient:
            def __init__(self, name, query_cap=None):
                self.name = name
                self.query_cap = query_cap
                self.seen: list[str] = []

            def search(self, query, limit=20):
                self.seen.append(query)
                return []

        capped = _RecordingClient("semantic_scholar", query_cap=2)
        uncapped = _RecordingClient("crossref")
        services = SimpleNamespace(
            config=SimpleNamespace(per_query_limit=10, search_max_concurrency=4),
            search_clients=[capped, uncapped],
        )
        _search(services, ["q1", "q2", "q3", "q4"])
        # Capped client only ran the first 2 queries; uncapped ran all 4.
        self.assertEqual(capped.seen, ["q1", "q2"])
        self.assertEqual(sorted(uncapped.seen), ["q1", "q2", "q3", "q4"])

    def test_unpaywall_resolver_requires_email(self) -> None:
        http = _canned_http({"best_oa_location": {"url_for_pdf": "https://x.org/p.pdf"}})
        self.assertEqual(UnpaywallResolver(http, email=None).resolve("10.1/abc"), [])

    def test_scihub_resolver_returns_parseable_pdf_type(self) -> None:
        from paper_search.resolvers import SciHubResolver

        html = (
            "<html><head><title>RuO2 paper</title></head><body>"
            '<embed id="pdf" src="//mirror.sci-hub.se/x/paper.pdf#navpanes=0&view=FitH">'
            "</body></html>"
        )

        def opener(request, timeout):
            return _FakeResponse(
                request.full_url, 200, {"content-type": "text/html"}, html.encode("utf-8")
            )

        links = SciHubResolver(HttpClient(opener=opener)).resolve("10.1/abc")
        self.assertEqual(len(links), 1)
        # The #fragment hides the .pdf suffix; the resolver must still type it
        # oa_pdf so the parser router parses it (a bare "pdf" is unsupported).
        self.assertEqual(links[0].source_type, "oa_pdf")
        self.assertTrue(links[0].url.startswith("https://"))

    def test_scihub_client_posts_when_get_returns_empty(self) -> None:
        from paper_search.resolvers import ScihubClient

        html = (
            "<html><head><title>RuO2 paper</title></head><body>"
            '<object type="application/pdf" data="/storage/x/paper.pdf"></object>'
            "</body></html>"
        )
        calls: list[tuple[str, str]] = []
        session = _FakeCurlSession(
            [
                # First mirror GET answers 200 with an empty body (DDoS-Guard).
                _CurlResp(200, b""),
                # POST fallback to the same mirror yields the real page.
                _CurlResp(200, html.encode("utf-8")),
            ],
            calls,
        )
        client = ScihubClient(session=session, discover=False)
        link = client.resolve_pdf_link("10.1/abc")
        self.assertIsNotNone(link)
        self.assertEqual(link.source_type, "oa_pdf")
        self.assertEqual(link.url, "https://sci-hub.se/storage/x/paper.pdf")
        # GET then POST against the same mirror.
        self.assertEqual([m for m, _ in calls[:2]], ["GET", "POST"])

    def test_build_settings_scopes_paperqa_index_to_work_dir(self) -> None:
        from paper_search.agent import paperqa_index as pq
        from paper_search.config import LlmConfig, PaperQAConfig

        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "paperqa"
            # embedding pinned so default auto-select (env/torch) is not exercised.
            settings = pq.build_settings(
                LlmConfig(provider="none"),
                PaperQAConfig(embedding="st-multi-qa-MiniLM-L6-cos-v1"),
                work_dir=work,
            )
            idx = settings.agent.index
            # Per-session index, not the shared ~/.pqa, and no recursive CWD crawl.
            self.assertEqual(idx.paper_directory, str(work))
            self.assertEqual(idx.index_directory, str(work / "index"))
            self.assertFalse(idx.recurse_subdirectories)

    def test_parse_mirror_domains_dedupes_and_normalizes(self) -> None:
        from paper_search.resolvers.scihub import parse_mirror_domains

        html = (
            '<a href="https://sci-hub.ru/">ru</a>'
            '<a href="http://www.sci-hub.ru/">dup</a>'
            '<a href="https://sci-hub.st">st</a>'
            '<a href="https://sci-hub.pub/about">excluded</a>'
            '<a href="https://example.org">noise</a>'
        )
        self.assertEqual(
            parse_mirror_domains(html),
            ["https://sci-hub.ru", "https://sci-hub.st"],
        )

    def test_scihub_client_discovers_mirrors_then_resolves(self) -> None:
        from paper_search.resolvers import ScihubClient

        source_html = '<a href="https://sci-hub.box/">box</a>'
        page_html = (
            "<html><head><title>p</title></head><body>"
            '<embed id="pdf" src="/storage/x/p.pdf">'
            "</body></html>"
        )
        calls: list[tuple[str, str]] = []
        session = _FakeCurlSession(
            [
                _CurlResp(200, source_html.encode("utf-8")),  # mirror discovery
                _CurlResp(200, page_html.encode("utf-8")),  # sci-hub.box page
            ],
            calls,
        )
        client = ScihubClient(session=session)
        link = client.resolve_pdf_link("10.1/abc")
        self.assertIsNotNone(link)
        # Discovered mirror leads, and the DOI is fetched from it.
        self.assertEqual(client.mirrors[0], "https://sci-hub.box")
        self.assertEqual(calls[0], ("GET", "https://www.sci-hub.pub/"))
        self.assertEqual(calls[1], ("GET", "https://sci-hub.box/10.1/abc"))
        self.assertEqual(link.url, "https://sci-hub.box/storage/x/p.pdf")

    def test_scihub_client_explicit_mirrors_skip_discovery(self) -> None:
        from paper_search.resolvers import ScihubClient

        page_html = (
            '<html><body><embed id="pdf" src="/p.pdf"></body></html>'
        )
        calls: list[tuple[str, str]] = []
        session = _FakeCurlSession([_CurlResp(200, page_html.encode("utf-8"))], calls)
        client = ScihubClient(session=session, mirrors=["https://sci-hub.test"])
        client.resolve_pdf_link("10.1/abc")
        # No discovery call; the pinned mirror is used directly.
        self.assertEqual(calls[0], ("GET", "https://sci-hub.test/10.1/abc"))

    def test_source_downloader_fetches_scihub_link_via_client(self) -> None:
        # The scihub link must be pulled through the impersonating client, not
        # the stdlib HttpClient (which would re-hit DDoS-Guard without cookies).
        def opener(request, timeout):  # pragma: no cover - must not be called
            raise AssertionError("scihub link must not use the stdlib HttpClient")

        class _Client:
            def __init__(self) -> None:
                self.fetched: list[str] = []

            def fetch(self, url):
                self.fetched.append(url)
                return b"%PDF-1.7\nbody", "application/pdf", url

        client = _Client()
        with tempfile.TemporaryDirectory() as tmp:
            downloader = SourceDownloader(
                HttpClient(opener=opener),
                PaperCache(Path(tmp)),
                resume=False,
                scihub_client=client,
            )
            paper = Paper(paper_id="p1", title="T", doi="10.1/abc")
            link = SourceLink(
                url="https://sci-hub.se/storage/x/paper.pdf#view=FitH",
                source_type="oa_pdf",
                resolver="scihub",
            )
            source = downloader.download_first_available(paper, [link])
            self.assertIsNotNone(source)
            self.assertEqual(client.fetched, [link.url])
            self.assertTrue(source.local_path.read_bytes().startswith(b"%PDF-"))

    def test_source_downloader_injects_elsevier_key(self) -> None:
        captured: list[dict[str, str]] = []

        def opener(request, timeout):
            captured.append(dict(request.headers))
            return _FakeResponse(
                request.full_url, 200, {"content-type": "text/xml"}, b"<xml/>"
            )

        http = HttpClient(opener=opener)
        with tempfile.TemporaryDirectory() as tmp:
            downloader = SourceDownloader(
                http,
                PaperCache(Path(tmp)),
                resume=False,
                elsevier_api_key="secret-key",
                elsevier_inst_token="inst-tok",
            )
            paper = Paper(paper_id="p1", title="T", doi="10.1016/j.x")
            link = SourceLink(
                url="https://api.elsevier.com/content/article/PII:S123",
                source_type="oa_xml",
                resolver="crossref_tdm",
            )
            source = downloader.download_first_available(paper, [link])
        self.assertIsNotNone(source)
        headers = captured[0]
        self.assertEqual(headers.get("X-els-apikey"), "secret-key")
        self.assertEqual(headers.get("X-els-insttoken"), "inst-tok")
        self.assertIn("xml", headers.get("Accept", "").lower())

    def test_source_downloader_skips_elsevier_key_for_other_hosts(self) -> None:
        captured: list[dict[str, str]] = []

        def opener(request, timeout):
            captured.append(dict(request.headers))
            return _FakeResponse(
                request.full_url, 200, {"content-type": "application/pdf"}, b"%PDF-1.4"
            )

        http = HttpClient(opener=opener)
        with tempfile.TemporaryDirectory() as tmp:
            downloader = SourceDownloader(
                http,
                PaperCache(Path(tmp)),
                resume=False,
                elsevier_api_key="secret-key",
            )
            paper = Paper(paper_id="p2", title="T", doi="10.1/abc")
            link = SourceLink(
                url="https://example.org/p.pdf",
                source_type="oa_pdf",
                resolver="unpaywall",
            )
            downloader.download_first_available(paper, [link])
        self.assertNotIn("X-els-apikey", captured[0])

    def _downloader_for(self, tmp: str, opener):
        return SourceDownloader(
            HttpClient(opener=opener), PaperCache(Path(tmp)), resume=False
        )

    def test_source_downloader_rejects_empty_body(self) -> None:
        def opener(request, timeout):
            return _FakeResponse(
                request.full_url, 200, {"content-type": "text/html"}, b""
            )

        with tempfile.TemporaryDirectory() as tmp:
            downloader = self._downloader_for(tmp, opener)
            paper = Paper(paper_id="p1", title="T", doi="10.1/abc")
            link = SourceLink(
                url="https://sci-hub.example/p.pdf",
                source_type="oa_pdf",
                resolver="scihub",
            )
            source = downloader.download_first_available(paper, [link])
            # An empty body is a failed download, not a 0-byte "pdf".
            self.assertIsNone(source)
            sources = Path(tmp) / "papers" / "p1" / "sources"
            self.assertFalse(list(sources.glob("original_*")))
            errors = downloader.cache.read_download_errors(paper)
            self.assertTrue(errors)

    def test_source_downloader_rejects_html_for_pdf_link(self) -> None:
        def opener(request, timeout):
            return _FakeResponse(
                request.full_url,
                200,
                {"content-type": "text/html"},
                b"<!DOCTYPE html><html><title>Just a moment...</title></html>",
            )

        with tempfile.TemporaryDirectory() as tmp:
            downloader = self._downloader_for(tmp, opener)
            paper = Paper(paper_id="p2", title="T", doi="10.1/abc")
            link = SourceLink(
                url="https://sci-hub.example/p.pdf",
                source_type="oa_pdf",
                resolver="scihub",
            )
            self.assertIsNone(downloader.download_first_available(paper, [link]))

    def test_source_downloader_rejects_html_for_xml_link(self) -> None:
        def opener(request, timeout):
            return _FakeResponse(
                request.full_url,
                200,
                {"content-type": "text/html"},
                b"<!DOCTYPE html><html><body>login</body></html>",
            )

        with tempfile.TemporaryDirectory() as tmp:
            downloader = self._downloader_for(tmp, opener)
            paper = Paper(paper_id="p3", title="T", doi="10.1/abc")
            link = SourceLink(
                url="https://api.example/article",
                source_type="oa_xml",
                resolver="crossref_tdm",
            )
            self.assertIsNone(downloader.download_first_available(paper, [link]))

    def test_source_downloader_accepts_valid_pdf(self) -> None:
        def opener(request, timeout):
            return _FakeResponse(
                request.full_url,
                200,
                {"content-type": "application/pdf"},
                b"%PDF-1.5\n...body...",
            )

        with tempfile.TemporaryDirectory() as tmp:
            downloader = self._downloader_for(tmp, opener)
            paper = Paper(paper_id="p4", title="T", doi="10.1/abc")
            link = SourceLink(
                url="https://example.org/p.pdf",
                source_type="oa_pdf",
                resolver="unpaywall",
            )
            source = downloader.download_first_available(paper, [link])
            self.assertIsNotNone(source)
            self.assertTrue(source.local_path.read_bytes().startswith(b"%PDF-"))


class _CurlResp:
    """Minimal stand-in for a curl_cffi response."""

    def __init__(
        self, status_code: int, content: bytes, url: str = "https://sci-hub.se/x"
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.url = url
        self.headers = {"content-type": "text/html"}


class _FakeCurlSession:
    """Scripted curl_cffi-like session recording (method, url) per call."""

    def __init__(self, responses: list, calls: list) -> None:
        self._responses = list(responses)
        self._calls = calls

    def _next(self) -> "_CurlResp":
        return self._responses.pop(0)

    def get(self, url, timeout=None, proxies=None):
        self._calls.append(("GET", url))
        return self._next()

    def post(self, url, data=None, timeout=None, proxies=None):
        self._calls.append(("POST", url))
        return self._next()

    def close(self) -> None:
        pass


class _FakeChatModel:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def invoke(self, messages):
        class _Msg:
            content = self.payload

        return _Msg()


class _FakeResponse:
    def __init__(
        self,
        url: str,
        status: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        self.url = url
        self.status = status
        self.headers = headers
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return self.body


class _FakeParserRouter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def parse(
        self,
        paper: Paper,
        source: DownloadedSource,
        output_dir: Path,
    ) -> list[ParseRun]:
        output_dir.mkdir(parents=True, exist_ok=True)
        blocks_path = output_dir / "jats.blocks.json"
        if paper.paper_id == "bad":
            blocks_path.write_text("{", encoding="utf-8")
        else:
            # One claim-bearing sentence + neutral filler so the parsed body
            # clears the content-quality gate (parsers.min_full_text_chars) like
            # a real full-text article. The filler has no Miller-index tokens or
            # value/unit patterns, so the rule extractor still finds exactly one
            # claim from "(110)".
            body = "RuO2 surface (110) shows HER activity at 42 mV. " + (
                "This section summarizes the experimental methodology and "
                "general background discussion in considerable detail to "
                "represent a realistic full-text article body. " * 14
            )
            write_json(
                blocks_path,
                [
                    {
                        "paper_id": paper.paper_id,
                        "parse_id": "jats",
                        "block_type": "paragraph",
                        "text": body,
                    }
                ],
            )
        return [
            ParseRun(
                paper_id=paper.paper_id,
                parser_name="jats",
                output_format="blocks_json",
                output_path=blocks_path,
                status="ok",
            )
        ]


if __name__ == "__main__":
    unittest.main()
