"""Eval harness runner.

Runs the benchmark suite, scores results, saves JSONL, reports summary.

Usage:
    python3 evals/runner.py                  # run full suite
    python3 evals/runner.py --tags coder     # run only tasks with tag 'coder'
    python3 evals/runner.py --id fast_math   # run single task
    python3 evals/runner.py --compare        # compare last two runs
    python3 evals/runner.py --dry-run        # validate checks without running agents
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def _run_task(task_def: dict, dry_run: bool = False) -> dict:
    """Execute one eval task, return result dict."""
    from evals.checkers import all_passed, run_checks

    task_id = task_def["id"]
    task_text = task_def["task"]
    route = task_def.get("route")
    checks = task_def.get("checks", [])
    min_score = task_def.get("min_score", 0)

    output = ""
    error = None
    elapsed = 0.0

    if not dry_run:
        import time

        from main import run as _run

        t0 = time.time()
        try:
            result = _run(task=task_text, force_route=route)
            output = result.get("result") or ""
        except Exception as e:
            error = str(e)
            output = f"[Error: {e}]"
        elapsed = round(time.time() - t0, 2)

    # Run heuristic checks
    check_results = run_checks(output, checks)
    checks_passed = all_passed(check_results)

    # Optional LLM judge
    llm_score = None
    if min_score > 0 and not dry_run and output:
        try:
            from nodes.orchestrator import _score_output

            llm_score = _score_output(task_text, output)
        except Exception:
            llm_score = None

    score_passed = llm_score is None or llm_score >= min_score
    overall_passed = checks_passed and score_passed and (error is None)

    return {
        "id": task_id,
        "task": task_text,
        "route": route,
        "passed": overall_passed,
        "checks": check_results,
        "llm_score": llm_score,
        "min_score": min_score,
        "output_preview": output[:200] if output else "",
        "error": error,
        "elapsed_secs": elapsed,
        "tags": task_def.get("tags", []),
    }


def run_suite(
    tags: list[str] | None = None,
    task_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Run the benchmark suite. Returns summary dict."""
    from rich.console import Console

    from evals.suite import SUITE

    console = Console()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Filter tasks
    tasks = SUITE
    if task_id:
        tasks = [t for t in tasks if t["id"] == task_id]
    elif tags:
        tasks = [t for t in tasks if any(tag in t.get("tags", []) for tag in tags)]

    if not tasks:
        console.print("[bold red]No matching tasks found.[/bold red]")
        return {}

    console.print(f"\n[bold]Running {len(tasks)} eval task(s){'  [dry-run]' if dry_run else ''}[/bold]\n")

    results: list[dict] = []
    passed = 0
    failed = 0
    out_file = RESULTS_DIR / f"{timestamp}.json"

    def _persist(partial: bool):
        """Write current results to disk (incremental — survives mid-run crash)."""
        if dry_run:
            return
        total = passed + failed
        out_file.write_text(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "total": total,
                    "passed": passed,
                    "failed": failed,
                    "pass_rate": round(passed / total * 100) if total else 0,
                    "partial": partial,
                    "results": results,
                },
                indent=2,
            )
        )

    for task_def in tasks:
        console.print(f"  [cyan]{task_def['id']}[/cyan]  {task_def['task'][:60]}...")
        # Isolate per-task crashes so one bad task can't kill the whole run
        try:
            result = _run_task(task_def, dry_run=dry_run)
        except Exception as e:
            result = {
                "id": task_def["id"],
                "task": task_def["task"],
                "route": task_def.get("route"),
                "passed": False,
                "checks": [{"type": "runner", "passed": False, "reason": f"runner crash: {e}"}],
                "llm_score": None,
                "min_score": task_def.get("min_score", 0),
                "output_preview": "",
                "error": str(e),
                "elapsed_secs": 0.0,
                "tags": task_def.get("tags", []),
            }
        results.append(result)
        if result["passed"]:
            passed += 1
            console.print(
                f"    [green]✓ PASS[/green]  {result['elapsed_secs']}s"
                + (f"  score={result['llm_score']}" if result["llm_score"] else "")
            )
        else:
            failed += 1
            reasons = [r["reason"] for r in result["checks"] if not r["passed"]]
            console.print(
                f"    [red]✗ FAIL[/red]  {'; '.join(reasons)}"
                + (f"  score={result['llm_score']}/{result['min_score']}" if result["llm_score"] else "")
            )
            if result["error"]:
                console.print(f"    [red]   Error: {result['error'][:80]}[/red]")
        # Persist after every task — partial results survive an external kill
        _persist(partial=True)

    total = passed + failed
    pass_rate = round(passed / total * 100) if total > 0 else 0

    summary = {
        "timestamp": timestamp,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "results": results,
    }

    # Final save (partial=False marks a complete run)
    if not dry_run:
        _persist(partial=False)
        console.print(f"\n[info]Results saved: {out_file}[/info]")

    # Print summary table
    console.print(f"\n{'=' * 50}")
    console.print(f"Results: {passed}/{total} passed ({pass_rate}%)")
    if failed > 0:
        console.print("[bold red]FAILED:[/bold red]")
        for r in results:
            if not r["passed"]:
                reasons = [x["reason"] for x in r["checks"] if not x["passed"]]
                console.print(f"  • {r['id']}: {'; '.join(reasons)}")
    console.print(f"{'=' * 50}\n")

    return summary


def compare_runs():
    """Compare the two most recent eval runs and highlight regressions."""
    from rich.console import Console

    console = Console()

    runs = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
    if len(runs) < 2:
        console.print("[yellow]Need at least 2 runs to compare.[/yellow]")
        return

    current = json.loads(runs[0].read_text())
    previous = json.loads(runs[1].read_text())

    cur_by_id = {r["id"]: r for r in current["results"]}
    prev_by_id = {r["id"]: r for r in previous["results"]}

    regressions = []
    improvements = []
    new_tasks = []

    for task_id, cur in cur_by_id.items():
        if task_id not in prev_by_id:
            new_tasks.append(task_id)
            continue
        prev = prev_by_id[task_id]
        if prev["passed"] and not cur["passed"]:
            regressions.append(task_id)
        elif not prev["passed"] and cur["passed"]:
            improvements.append(task_id)

    console.print("\n[bold]Comparing runs:[/bold]")
    console.print(
        f"  Previous: {previous['timestamp']}  {previous['passed']}/{previous['total']} ({previous['pass_rate']}%)"
    )
    console.print(
        f"  Current:  {current['timestamp']}   {current['passed']}/{current['total']} ({current['pass_rate']}%)"
    )

    if regressions:
        console.print(f"\n[bold red]REGRESSIONS ({len(regressions)}):[/bold red]")
        for t in regressions:
            cur = cur_by_id[t]
            reasons = [r["reason"] for r in cur["checks"] if not r["passed"]]
            console.print(f"  • [red]{t}[/red]: {'; '.join(reasons)}")

    if improvements:
        console.print(f"\n[bold green]IMPROVEMENTS ({len(improvements)}):[/bold green]")
        for t in improvements:
            console.print(f"  • [green]{t}[/green]")

    if new_tasks:
        console.print(f"\n[cyan]NEW TASKS ({len(new_tasks)}):[/cyan] {', '.join(new_tasks)}")

    if not regressions and not improvements:
        console.print("\n[green]No changes between runs.[/green]")

    return {"regressions": regressions, "improvements": improvements}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run agent eval suite")
    parser.add_argument("--tags", nargs="+", help="Run only tasks with these tags")
    parser.add_argument("--id", dest="task_id", help="Run a single task by ID")
    parser.add_argument("--compare", action="store_true", help="Compare last two runs")
    parser.add_argument("--dry-run", action="store_true", help="Validate checks without running agents")
    parser.add_argument("--list", action="store_true", help="List all tasks in the suite")
    args = parser.parse_args()

    if args.compare:
        compare_runs()
    elif args.list:
        from evals.suite import SUITE

        for t in SUITE:
            print(f"  {t['id']:35}  {','.join(t.get('tags', []))}  {t['task'][:60]}")
    else:
        run_suite(tags=args.tags, task_id=args.task_id, dry_run=args.dry_run)
