# Host Dependencies

Files in `host/` need to be installed on the host machine for certain skills to work.
Symlink to the **source repo**, not the plugin cache — cache gets overwritten on `plugin update`.

## Dependencies

| Source | Target | Used by |
|--------|--------|---------|
| `host/fish/dev-server.fish` | `~/.config/fish/functions/dev-server.fish` | `dev-server` skill |

## Install

```bash
# From the cortex repo root:
ln -sf "$PWD/plugin/host/fish/dev-server.fish" ~/.config/fish/functions/dev-server.fish
```

## Verify

```bash
type -q dev-server && echo "installed" || echo "missing"
```
