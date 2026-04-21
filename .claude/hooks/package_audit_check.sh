#!/usr/bin/env bash
# PreToolUse hook: detect package install commands and block until audit is performed.
# Exit 0 = allow, Exit 2 = block with message.

set -uo pipefail

# Guard: if jq is not available, allow (don't break all Bash commands)
if ! command -v jq &>/dev/null; then
  exit 0
fi

# Read tool input from stdin (JSON with "command" field)
INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null) || true

if [ -z "$CMD" ]; then
  exit 0
fi

# Strip quoted strings to avoid false positives on commands that merely
# *mention* install commands inside arguments (e.g. gh pr create --body "npm install ...").
# Replace single-quoted, double-quoted, and heredoc bodies with empty strings.
STRIPPED=$(echo "$CMD" | sed -E \
  -e "s/'[^']*'//g" \
  -e 's/"[^"]*"//g' \
  -e "s/\\$\\(cat <<'?[A-Z_]*'?[^)]*\\)//g" \
)

# Patterns that indicate a package install/add command
INSTALL_PATTERNS=(
  'npm[[:space:]]+(install|i|add)[[:space:]]'
  'npx[[:space:]]+'
  'pnpm[[:space:]]+(add|install)[[:space:]]'
  'yarn[[:space:]]+(add)[[:space:]]'
  'bun[[:space:]]+(add|install)[[:space:]]'
  'pip3?[[:space:]]+install[[:space:]]'
  'pipx[[:space:]]+install[[:space:]]'
  'uv[[:space:]]+(pip[[:space:]]+install|add)[[:space:]]'
  'brew[[:space:]]+install[[:space:]]'
  'cargo[[:space:]]+(install|add)[[:space:]]'
  'go[[:space:]]+install[[:space:]]'
  'curl[[:space:]].*\|[[:space:]]*(sh|bash|zsh)'
  'wget[[:space:]].*\|[[:space:]]*(sh|bash|zsh)'
)

# Whitelist: commands that look like installs but are safe (no new packages)
# All patterns are start-anchored (^) to prevent substring matches in compound commands.
SAFE_PATTERNS=(
  # Lockfile-only reinstalls (no package name, optional flags)
  # Flags that take path values: --cwd, --prefix, --cache-dir (matched explicitly)
  # Boolean flags: --frozen-lockfile, --no-save, etc. (matched as --flag with no value)
  '^npm[[:space:]]+ci([[:space:]]|$)'
  '^npm[[:space:]]+(install|i)([[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]*$'
  '^pnpm[[:space:]]+install([[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]*$'
  '^yarn[[:space:]]+install([[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]*$'
  '^bun[[:space:]]+install([[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]*$'
  # Allow --cwd with space-separated path (bun install --cwd /path)
  '^bun[[:space:]]+install[[:space:]]+--cwd[[:space:]]+/[^[:space:]]*([[:space:]]+--[a-z-]+(=[^[:space:]]+)?)*[[:space:]]*$'
  # Requirements file / editable installs (existing deps)
  '^pip3?[[:space:]]+install[[:space:]]+-r[[:space:]]'
  '^pip3?[[:space:]]+install[[:space:]]+(\.|\.\/|-e[[:space:]])'
  '^uv[[:space:]]+pip[[:space:]]+install[[:space:]]+-r[[:space:]]'
  '^uv[[:space:]]+sync'
  # Pre-approved brew packages (repo tooling)
  '^brew[[:space:]]+install[[:space:]]+(lefthook|jq|yq)([[:space:]]|$)'
  # Common local npx tools (already installed in repo)
  '^npx[[:space:]]+(tsc|tsx|eslint|oxlint|oxfmt|prettier|vitest|jest|playwright|lefthook|turbo|rimraf|sort-package-json)([[:space:]]|$)'
)

# Split into individual command segments and check each independently.
# This handles: multi-line scripts, compound commands (&&, ;, ||), and
# ensures safe patterns on one segment can't shield another.
BLOCKED=false
while IFS= read -r LINE; do
  [ -z "$LINE" ] && continue

  # Split compound commands on && ; || into individual segments
  # Use sed to put each segment on its own line, then iterate
  while IFS= read -r SEG; do
    # Trim leading/trailing whitespace
    SEG=$(echo "$SEG" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')
    [ -z "$SEG" ] && continue

    # Strip quotes from this segment for install-pattern matching
    SEG_STRIPPED=$(echo "$SEG" | sed -E \
      -e "s/'[^']*'//g" \
      -e 's/"[^"]*"//g' \
    )

    # Check safe patterns (anchored, against original segment)
    IS_SAFE=false
    for pattern in "${SAFE_PATTERNS[@]}"; do
      if echo "$SEG" | grep -qE "$pattern"; then
        IS_SAFE=true
        break
      fi
    done
    $IS_SAFE && continue

    # Check install patterns against stripped segment
    for pattern in "${INSTALL_PATTERNS[@]}"; do
      if echo "$SEG_STRIPPED" | grep -qE "$pattern"; then
        BLOCKED=true
        break 3
      fi
    done
  done <<< "$(echo "$LINE" | awk '{gsub(/[[:space:]]*(&&|[|][|]|;)[[:space:]]*/,"\n"); print}')"
done <<< "$STRIPPED"

if $BLOCKED; then
  echo "PACKAGE AUDIT REQUIRED: This command installs new packages. You must run the package-audit security checks before proceeding. Load and follow .claude/skills/package-audit/SKILL.md — present the security audit block to the user and get explicit approval before installing. If you're unsure what this means or how to proceed, contact Avihay or Ido for approval."
  exit 2
fi

# No match — allow
exit 0
