# Examples

Sample inputs for the file-watcher (`./run --watch`). Copy any of these into the
`watch/` directory and the agents process them automatically.

| File | What the watcher does |
|------|-----------------------|
| `task.txt` | Plain task text — orchestrator auto-routes |
| `job.task` | YAML with explicit `task` + `route` (and optional `project`) |
| `page.url` | URL on line 1 — RESEARCHER fetches + summarizes it |
| `review_me.py` | Source file — CODER reviews it for bugs/security |

## Try it

```bash
# Terminal 1 — start the watcher
./run --watch

# Terminal 2 — drop a file in
cp examples/task.txt watch/
```

Results land in `output/watched_<timestamp>/`, and the processed file moves to
`watch/done/`.

You can also process the examples once without the daemon:

```bash
cp examples/*.txt examples/*.task watch/
./run --watch --once
```
