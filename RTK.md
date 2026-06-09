# RTK - Rust Token Killer (Codex CLI)

**Usage**: Token-optimized CLI proxy for shell commands.

## Rule

Always prefer `rtk` commands for inspection-heavy workflows.

Use RTK-native commands directly when the goal is to read, search, or inspect files:

```bash
rtk ls .                      # Compact directory listing
rtk tree .                    # Compact tree view
rtk read scraper/file.py      # Optimized file reading
rtk read -                    # Read from stdin
rtk find -name "*.py" .       # File search with compact tree output
rtk grep "pattern" .          # Grouped search results
rtk diff file1 file2          # Ultra-condensed diff output
rtk json package.json         # Compact JSON view
rtk smart scraper/file.py     # 2-line heuristic summary
rtk deps                      # Dependency summary
rtk env                       # Filtered environment snapshot
rtk git diff                  # Optimized git diff output
rtk git status                # Compact git status
rtk git log -n 10             # Condensed git log output
```

Use `rtk` as the wrapper for normal shell commands too:

```bash
rtk cargo test
rtk npm run build
rtk pytest -q
rtk pnpm list
```

If a command must run through the underlying shell directly, use `rtk proxy` explicitly:

```bash
rtk proxy powershell.exe -Command "Get-Content -Path 'scraper\\scrapers\\substack.py'"
```

## Meta Commands

```bash
rtk gain           # Token savings analytics
rtk gain --history # Recent command savings history
rtk proxy <cmd>     # Run raw command without filtering
```

## Notes

- Prefer `rtk read`, `rtk ls`, `rtk find`, and `rtk grep` for code/file inspection.
- Prefer `rtk git diff` and `rtk git status` for git context.
- Native PowerShell cmdlets like `Get-Content` do not resolve through `rtk` unless wrapped with `rtk proxy`.

## Verification

```bash
rtk --version
rtk gain
Get-Command rtk
```
