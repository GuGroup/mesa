General SKILL workflow.

TEST VERSION!

# Strategy Generation
Stratgy generation process should follow this continuous skill flow.

1. Experimental data extraction
  - Extract information by using skill in 'TASK_EXTRACT_DATA_FROM_PDF'
  - TEST: input saved on mesa_0625(present project)/RESULT/0625/init_files/experiment/ExperiemntalData.pdf

2. Paper search
  - Search paper with 'search-papers-with-mcp' skill.
  - User must speicify the 'target task' and 'material domain'.
  - User need to download recommended papers manually.
  
3. Paper extraction
  - Extract information from paper by using 'decompose-chemistry-paper-pdf' or 'extract-general-insight-pdf'.
  - Paper under 'strategy' folder should be extracted with 'decompose-chemistry-paper-pdf'.
  - Paper under non-'strategy' folder should be extracted with 'extract-general-insight-pdf'.
  - TEST: input saved on mesa_0625(present project)/RESULT/0625/init_files/papers/domain, legacy, strategy, meta

4. Strategy generation
  - Use 'generate-strategies' skill (`generate_strategies` workflow stage).
  - You need to generate multiple computational chemistry strategies based on result of 1,2, and 3 skills.
  - Use information from 1. Experimental data extraction only as benchmark constraints or measured targets to explain computationally.
  - Do not generate experimental strategy plans; generate DFT/computational proof strategies from 3. Paper extraction.
X. Strategy update after manuscript
  - Use 'update-strategies-from-manuscript' skill after one strategy such as S1 is completed and written as a manuscript or result artifact.
  - Compare the manuscript result against the original generated strategy sequence.
  - Decide whether to maintain the original next strategy, revise details, reprioritize, repair the completed strategy, or add a new computational direction.
  - Keep updated strategies computational chemistry focused and preserve references from the original strategy plan and manuscript output.
