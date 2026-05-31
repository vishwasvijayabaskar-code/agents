"""Standard benchmark suite for the agent system.

Each eval task defines:
  id       — unique identifier
  task     — prompt to send to agents
  route    — force a specific agent (None = auto-route)
  checks   — list of checker specs (see checkers.py)
  min_score — minimum LLM judge score to pass (0 = skip LLM judge)
  tags     — categories for filtering

Add new tasks here to expand the benchmark.
"""

SUITE: list[dict] = [
    # ----------------------------- FAST agent ---
    {
        "id": "fast_math",
        "task": "What is 17 * 23?",
        "route": "FAST",
        "checks": [{"type": "contains_any", "values": ["391", "39 1"]}],
        "min_score": 0,
        "tags": ["fast", "math"],
    },
    {
        "id": "fast_capital",
        "task": "What is the capital of France?",
        "route": "FAST",
        "checks": [{"type": "contains_any", "values": ["Paris", "paris"]}],
        "min_score": 0,
        "tags": ["fast", "factual"],
    },
    {
        "id": "fast_no_error",
        "task": "Explain what a Python list comprehension is",
        "route": "FAST",
        "checks": [
            {"type": "no_error"},
            {"type": "min_length", "value": 50},
        ],
        "min_score": 0,
        "tags": ["fast", "explanation"],
    },

    # ----------------------------- CODER agent ---
    {
        "id": "coder_fibonacci",
        "task": "Write a Python function to compute the Nth Fibonacci number using recursion with memoization",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["def ", "fibonacci", "fib"]},
            {"type": "no_error"},
        ],
        "min_score": 6,
        "tags": ["coder", "python", "algorithms"],
    },
    {
        "id": "coder_html_button",
        "task": "Write an HTML button that says 'Click me' with CSS to make it blue and rounded",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["<button", "button"]},
            {"type": "contains_any", "values": ["border-radius", "rounded", "blue", "#"]},
        ],
        "min_score": 0,
        "tags": ["coder", "html", "css"],
    },
    {
        "id": "coder_rest_api",
        "task": "Write a minimal FastAPI endpoint that returns {\"status\": \"ok\"} at GET /health",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["@app.get", "FastAPI", "fastapi"]},
            {"type": "contains_any", "values": ["/health", "health"]},
        ],
        "min_score": 6,
        "tags": ["coder", "python", "api"],
    },
    {
        "id": "coder_no_crash",
        "task": "Write a Python class for a stack with push, pop, and peek methods",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["class ", "def push", "def pop"]},
            {"type": "no_error"},
        ],
        "min_score": 0,
        "tags": ["coder", "python", "data-structures"],
    },

    # ----------------------------- Routing ---
    {
        "id": "route_code_task",
        "task": "write a function to sort a list",
        "route": None,  # auto-route
        "checks": [
            {"type": "contains_code"},
            {"type": "no_error"},
        ],
        "min_score": 0,
        "tags": ["routing", "coder"],
    },
    {
        "id": "route_short_task",
        "task": "what is 2 + 2",
        "route": None,
        "checks": [
            {"type": "contains_any", "values": ["4", "four"]},
            {"type": "no_error"},
        ],
        "min_score": 0,
        "tags": ["routing", "fast"],
    },

    # ----------------------------- Quality ---
    {
        "id": "quality_explanation",
        "task": "Explain how a hash table works in simple terms",
        "route": "FAST",
        "checks": [
            {"type": "no_error"},
            {"type": "min_length", "value": 100},
            {"type": "contains_any", "values": ["hash", "key", "bucket", "collision"]},
        ],
        "min_score": 6,
        "tags": ["fast", "quality", "explanation"],
    },
    {
        "id": "quality_code_correctness",
        "task": "Write a Python function that reverses a string without using slicing",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["def ", "reverse"]},
            {"type": "no_error"},
        ],
        "min_score": 6,
        "tags": ["coder", "quality", "python"],
    },

    # ----------------------------- More FAST ---
    {
        "id": "fast_boolean",
        "task": "Is 0 truthy or falsy in Python?",
        "route": "FAST",
        "checks": [{"type": "contains_any", "values": ["falsy", "False", "false"]}, {"type": "no_error"}],
        "min_score": 0,
        "tags": ["fast", "python", "factual"],
    },
    {
        "id": "fast_definition",
        "task": "In one sentence, what is idempotency in the context of HTTP methods?",
        "route": "FAST",
        "checks": [
            {"type": "no_error"},
            {"type": "contains_any", "values": ["same", "repeat", "multiple", "once", "effect"]},
        ],
        "min_score": 0,
        "tags": ["fast", "explanation"],
    },

    # ----------------------------- More CODER ---
    {
        "id": "coder_sql_query",
        "task": "Write a SQL query to select the top 5 customers by total order amount from an orders table",
        "route": "CODER",
        "checks": [
            {"type": "contains_any", "values": ["SELECT", "select"]},
            {"type": "contains_any", "values": ["ORDER BY", "order by", "LIMIT", "limit", "TOP", "top"]},
            {"type": "no_error"},
        ],
        "min_score": 0,
        "tags": ["coder", "sql"],
    },
    {
        "id": "coder_regex",
        "task": "Write a Python function using re that validates an email address",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["import re", "re.", "compile", "match"]},
            {"type": "no_error"},
        ],
        "min_score": 0,
        "tags": ["coder", "python", "regex"],
    },
    {
        "id": "coder_bugfix",
        "task": "This Python function has a bug, fix it:\n\ndef average(nums):\n    return sum(nums) / len(nums) + 1",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "no_error"},
        ],
        "min_score": 6,
        "tags": ["coder", "python", "debug"],
    },
    {
        "id": "coder_dockerfile",
        "task": "Write a minimal Dockerfile for a Python 3.11 app whose entry point is app.py",
        "route": "CODER",
        "checks": [
            {"type": "contains_any", "values": ["FROM", "from python"]},
            {"type": "contains_any", "values": ["app.py", "CMD", "ENTRYPOINT"]},
        ],
        "min_score": 0,
        "tags": ["coder", "docker"],
    },

    # ----------------------------- More routing ---
    {
        "id": "route_explanation_task",
        "task": "what does the SOLID acronym stand for in software design",
        "route": None,
        "checks": [
            {"type": "no_error"},
            {"type": "contains_any", "values": ["single", "Single", "responsibility", "Liskov", "dependency"]},
        ],
        "min_score": 0,
        "tags": ["routing", "explanation"],
    },

    # ----------------------------- More quality ---
    {
        "id": "quality_tradeoffs",
        "task": "Explain the trade-offs between SQL and NoSQL databases",
        "route": "FAST",
        "checks": [
            {"type": "no_error"},
            {"type": "min_length", "value": 150},
            {"type": "contains_any", "values": ["schema", "scale", "scaling", "relational", "consistency", "flexible"]},
        ],
        "min_score": 6,
        "tags": ["fast", "quality", "databases"],
    },
    {
        "id": "quality_algorithm",
        "task": "Write a Python implementation of binary search with a docstring explaining the time complexity",
        "route": "CODER",
        "checks": [
            {"type": "contains_code"},
            {"type": "contains_any", "values": ["def ", "binary", "search", "mid"]},
            {"type": "contains_any", "values": ["log", "O(", "complexity"]},
            {"type": "no_error"},
        ],
        "min_score": 6,
        "tags": ["coder", "quality", "algorithms"],
    },
]
