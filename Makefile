.PHONY: install test cov lint fix run web eval demo completions clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies
	pip install -r requirements.txt

test:  ## Run the test suite (no Ollama required)
	python3 -m pytest tests/ -q

cov:  ## Run tests with coverage report
	python3 -m pytest tests/ -q --cov --cov-report=term-missing

lint:  ## Check lint, format, and types
	ruff check .
	ruff format --check .
	mypy helpers/ nodes/ state.py main.py graph.py mcp_server.py web/ watch.py evals/

fix:  ## Autofix lint issues
	ruff check --fix .

run:  ## Start the REPL (use ARGS="..." for a one-shot task)
	./run $(ARGS)

web:  ## Launch the web UI at :8000
	python3 web.py

eval:  ## Run the eval/benchmark suite (needs Ollama)
	python3 evals/runner.py $(ARGS)

demo:  ## Regenerate demo.gif (needs vhs + warm Ollama)
	vhs demo.tape

completions:  ## Print shell-completion setup (needs: pip install argcomplete)
	@echo '# bash: add to ~/.bashrc'
	@echo 'eval "$$(register-python-argcomplete main.py)"'
	@echo '# zsh: add to ~/.zshrc'
	@echo 'autoload -U bashcompinit && bashcompinit'
	@echo 'eval "$$(register-python-argcomplete main.py)"'

clean:  ## Remove Python caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache
