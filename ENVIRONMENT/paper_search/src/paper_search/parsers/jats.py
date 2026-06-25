from __future__ import annotations

from pathlib import Path

from paper_search.models import ParseRun
from paper_search.parsers.xml_blocks import blocks_to_dicts, parse_xml_blocks
from paper_search.utils import write_json


class JatsParser:
    name = "jats"

    def parse(self, paper_id: str, source_path: Path, output_dir: Path) -> ParseRun:
        output_dir.mkdir(parents=True, exist_ok=True)
        blocks = parse_xml_blocks(source_path, paper_id, self.name)
        output_path = output_dir / "jats.blocks.json"
        write_json(output_path, blocks_to_dicts(blocks))
        return ParseRun(
            paper_id=paper_id,
            parser_name=self.name,
            output_format="blocks_json",
            output_path=output_path,
            status="ok",
            parse_quality={
                "block_count": len(blocks),
                "section_count": len({block.section for block in blocks if block.section}),
                "figure_caption_count": sum(
                    1 for block in blocks if block.block_type == "figure_caption"
                ),
                "table_count": sum(1 for block in blocks if block.block_type == "table"),
            },
        )
