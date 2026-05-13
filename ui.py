from rich.console import Console
from rich.theme import Theme
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
import re

theme = Theme({
    "orchestrator": "bold cyan",
    "coder":        "bold green",
    "researcher":   "bold yellow",
    "fast":         "bold blue",
    "codex":        "bold magenta",
    "claude":       "bold red",
    "executor":     "bold white",
    "info":         "dim white",
    "result":       "white",
    "separator":    "dim blue",
})

console = Console(theme=theme, highlight=False)

AGENT_STYLES = {
    "ORCHESTRATOR": "orchestrator",
    "CODER":        "coder",
    "RESEARCHER":   "researcher",
    "FAST":         "fast",
    "CODEX":        "codex",
    "CLAUDE":       "claude",
    "EXECUTOR":     "executor",
}

def print_task_header(task: str):
    console.print()
    console.print(Panel(f"[bold]{task}[/bold]", style="separator", expand=False))

def print_agent_header(agent: str, model: str = ""):
    style = AGENT_STYLES.get(agent.upper(), "info")
    label = f"[{style}][{agent}][/{style}]"
    if model:
        short = model.split("/")[-1]
        label += f" [info]({short})[/info]"
    console.print(label)

def print_separator():
    console.rule(style="separator")

def print_agents_used(agents: list[str]):
    parts = [f"[{AGENT_STYLES.get(a.upper(), 'info')}]{a}[/{AGENT_STYLES.get(a.upper(), 'info')}]" for a in agents]
    console.print(f"\nAgents: {' → '.join(parts)}")

def print_files(output_dir: str):
    console.print(f"[info]Files: {output_dir}[/info]")

def render_markdown_code_blocks(text: str):
    """Print text, rendering code blocks with syntax highlighting."""
    parts = re.split(r'(```\w*\n[\s\S]*?```)', text)
    for part in parts:
        m = re.match(r'```(\w*)\n([\s\S]*?)```', part)
        if m:
            lang = m.group(1) or "text"
            code = m.group(2)
            try:
                syn = Syntax(code, lang, theme="monokai", line_numbers=False)
                console.print(syn)
            except Exception:
                console.print(part)
        else:
            if part.strip():
                console.print(part, style="result")

def show_stats_table(totals: dict, date: str):
    table = Table(title=f"Token Usage — {date}", style="separator")
    table.add_column("Agent (Model)", style="bold")
    table.add_column("Prompt", justify="right")
    table.add_column("Completion", justify="right")
    table.add_column("Total", justify="right", style="bold")
    grand_p = grand_c = 0
    for agent, counts in sorted(totals.items()):
        p, c = counts["prompt"], counts["completion"]
        grand_p += p
        grand_c += c
        table.add_row(agent, f"{p:,}", f"{c:,}", f"{p+c:,}")
    table.add_section()
    table.add_row("[bold]TOTAL[/bold]", f"{grand_p:,}", f"{grand_c:,}", f"{grand_p+grand_c:,}")
    console.print(table)
