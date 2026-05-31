# Eval Baseline

Reference results from the benchmark suite (`evals/suite.py`) run against the
default local model stack. Regenerate with `python3 evals/runner.py`; compare a
later run with `python3 evals/runner.py --compare`.

## Latest baseline — 2026-05-31

| Metric | Value |
|--------|-------|
| Tasks | 20 |
| Passed | **20 (100%)** |
| Failed | 0 |
| LLM-judged tasks | 7 (avg score 7.1 / 10) |
| Total wall time | ~946s (avg 47s/task) |

Models used:
- orchestrator `ollama/qwen3:32b`
- coder `ollama/qwen2.5-coder:32b`
- fast `ollama/qwen2.5:7b`
- researcher `ollama/deepseek-r1:14b`

Hardware/timing will vary; treat wall times as relative, not absolute. Cold model
loads dominate the first task of each model family.

## Per-tag pass rate

| Tag | Pass / Total |
|-----|--------------|
| coder | 11 / 11 |
| fast | 8 / 8 |
| python | 7 / 7 |
| quality | 4 / 4 |
| explanation | 4 / 4 |
| routing | 3 / 3 |
| algorithms | 2 / 2 |
| factual | 2 / 2 |
| api / css / data-structures / databases / debug / docker / html / math / regex / sql | 1 / 1 each |

## Notes

- All checks are heuristic (contains code, contains keywords, no error signal, min
  length); tasks with `min_score > 0` additionally pass an LLM-judge threshold.
- Tasks force a route where the point is to exercise a specific agent; `routing`
  tasks leave `route=None` to exercise the orchestrator's auto-routing.
- The runner persists results after every task (`partial` flag), so an interrupted
  run still yields a usable JSON in `evals/results/`.
- This file is the human-readable reference; raw timestamped JSON in
  `evals/results/` is gitignored.

## How to use as a regression gate

```bash
python3 evals/runner.py            # run, writes evals/results/<ts>.json
python3 evals/runner.py --compare  # diff the two most recent runs, flag regressions
```

A regression = a task that passed in the previous run and fails in the current one.
