# Project Instructions

- When adding a new company, follow the guide in `ADDING_A_COMPANY.md` step by step.
- The pipeline lives in `earnings2/`. Key entry points: `cli.py` (commands), `web.py` (Flask UI), `pipeline/runner.py` (orchestration).
- Always test parsing incrementally: start with one quarter, then expand to a full year, then older eras.
- PDF table extraction is fragile — always inspect what pdfplumber actually returns before writing parser logic.
- After adding a new company, update `ADDING_A_COMPANY.md` with any new lessons, pitfalls, or process changes learned during the work.
