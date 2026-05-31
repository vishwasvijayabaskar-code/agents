"""Plugin loader — scans plugins/ directory and registers custom agents."""
import importlib.util
from pathlib import Path
from typing import Callable

# Registry: plugin_name -> {"node_fn": callable, "route_name": str, "description": str}
_REGISTRY: dict[str, dict] = {}

PLUGINS_DIR = Path(__file__).parent.parent / "plugins"


class PluginDefinition:
    """Returned by plugin register() to declare a custom agent."""

    def __init__(
        self,
        name: str,
        node_fn: Callable,
        description: str = "",
    ):
        if not name.isidentifier():
            raise ValueError(f"Plugin name must be a valid Python identifier, got: {name!r}")
        self.name = name.upper()
        self.node_fn = node_fn
        self.description = description


def load_plugins() -> dict[str, dict]:
    """
    Scan plugins/ directory. For each .py file, call its register() function
    which must return a PluginDefinition. Returns dict of loaded plugins.
    """
    if not PLUGINS_DIR.exists():
        return {}

    loaded = {}
    for path in sorted(PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue  # skip __init__.py etc.
        try:
            spec = importlib.util.spec_from_file_location(f"plugins.{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "register"):
                print(f"[plugins] {path.name}: no register() function, skipping")
                continue
            defn: PluginDefinition = mod.register()
            if not isinstance(defn, PluginDefinition):
                print(f"[plugins] {path.name}: register() must return PluginDefinition, skipping")
                continue
            _REGISTRY[defn.name] = {
                "node_fn": defn.node_fn,
                "route_name": defn.name,
                "description": defn.description,
                "source": str(path),
            }
            loaded[defn.name] = _REGISTRY[defn.name]
            print(f"[plugins] loaded: {defn.name} ({path.name})")
        except Exception as e:
            print(f"[plugins] {path.name}: failed to load — {e}")

    return loaded


def get_plugin_nodes() -> dict[str, Callable]:
    """Return {route_name: node_fn} for all registered plugins."""
    return {name: info["node_fn"] for name, info in _REGISTRY.items()}


def get_plugin_routes() -> list[str]:
    """Return list of all registered plugin route names."""
    return list(_REGISTRY.keys())


def get_plugin_descriptions() -> str:
    """Return formatted string of plugin descriptions for the orchestrator system prompt."""
    if not _REGISTRY:
        return ""
    lines = []
    for name, info in _REGISTRY.items():
        desc = info["description"] or "(no description)"
        lines.append(f"{name}: {desc}")
    return "\nPlugin agents:\n" + "\n".join(lines)
