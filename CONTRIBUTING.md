# Contributing

## Dev setup

```bash
# Clone and install in editable mode with test dependencies
git clone https://github.com/trgeuy/serial-mcp-server.git
cd serial-mcp-server
pip install -e ".[test]"

# Run tests (no serial hardware needed)
python -m pytest tests/ -v
```

## How tools are registered

Each `handlers_*.py` file exports two objects:

```python
TOOLS: list[Tool] = [...]          # Tool definitions with names, descriptions, schemas
HANDLERS: dict[str, Callable] = {  # Maps tool name → async handler function
    "serial.tool_name": handle_fn,
}
```

`server.py` merges these objects inside `build_server()`:

```python
tools = handlers_serial.TOOLS + handlers_introspection.TOOLS + handlers_spec.TOOLS + handlers_trace.TOOLS + handlers_plugin.TOOLS
handlers = {**handlers_serial.HANDLERS, **handlers_introspection.HANDLERS, **handlers_spec.HANDLERS, **handlers_trace.HANDLERS}
```

`handlers_plugin.make_handlers()` adds the plugin handlers. It returns closures. Each closure captures the `PluginManager` instance and the `Server` instance.

## Handler pattern

Every handler has the same signature:

```python
async def handle_something(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
```

- `state`: the shared serial state (connections).
- `args`: the parsed tool arguments from the MCP client.
- The handler returns `_ok(key=value)` on success, or `_err(code, message)` on failure.

The dispatcher in `server.py` catches common exceptions (`KeyError`, `SerialException`, `TimeoutError`, and others) and converts them to error responses automatically.

## Adding a new tool

1. Add the `Tool(...)` definition to the `TOOLS` list in the correct `handlers_*.py` file.
2. Write the handler function. Follow the signature above.
3. Add the mapping to the `HANDLERS` dict.
4. Add tests in the matching `test_*.py` file.

Tool names follow a convention. Core tools use `serial.<action>`, for example `serial.read` or `serial.open`. Subsystem tools use `serial.<category>.<action>`, for example `serial.spec.read` or `serial.plugin.reload`.

## Plugin system internals

**Path containment.** `PluginManager.load()` resolves the path and checks that it is inside `plugins_dir` before loading. It rejects paths outside `.serial_mcp/plugins/` with a `ValueError`.

**Loading.** `load_plugin()` uses `importlib` to load a `.py` file or a package's `__init__.py`. It checks the `TOOLS` and `HANDLERS` exports, and the optional `META` export. It then registers the module in `sys.modules` under a unique key: `serial_mcp_plugin__{name}__{hash}`.

**Name collisions.** A plugin tool name can collide with an existing tool, core or plugin. When this happens, loading fails with a `ValueError`.

**Policy.** The `PluginManager` parses the `SERIAL_MCP_PLUGINS` env var into `(enabled, allowlist)`. It checks this policy before every `load()` call. `load_all()` does nothing when plugins are disabled.

**Hot reload.** `reload(name)` calls `unload(name)`, then `load(path)`. `unload` filters the `TOOLS` list in place and removes the handler keys. It also deletes the old module from `sys.modules`.

**Limitation.** MCP clients may not refresh their tool list mid-session. A newly loaded plugin may need a client restart before you can call its tools. Hot-reload of an already-loaded plugin works without a restart.

## MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) lets you call tools without an agent:

```bash
npx @modelcontextprotocol/inspector python -m serial_mcp_server
```

Open the URL with the auth token shown in the terminal. Use the **Tools** tab to call any tool directly.

## Tests

All tests run without serial hardware. They use `MagicMock` for pyserial objects, `tmp_path` fixtures for filesystem isolation, and `monkeypatch` for environment variables.

```bash
# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_plugins.py -v

# Run a specific test
python -m pytest tests/test_plugins.py::TestPluginManager::test_load_adds_tools_and_handlers -v
```
