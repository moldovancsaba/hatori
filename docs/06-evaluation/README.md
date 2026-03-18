# Evaluation

Behavioural and regression evaluation is done by the **golden test suite**:

- **Location:** `tests/golden/run_golden.py`
- **Run:** `make test` (includes golden suite after reset and self-tests) or `python tests/golden/run_golden.py`

The suite covers offline runtime behaviour, chat and upload UI flows, API ingest/respond/outcome, and operator dashboard. No separate EVAL module; see `docs/10-api-contracts/interfaces.md` for target contracts.
