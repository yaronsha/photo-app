---
name: package-audit
description: Real-time supply-chain security gate for package installs. Audits packages before installation (typosquat, CVE, license, popularity), requires explicit user approval. Triggered automatically by PreToolUse hook on install commands.
author: id0sch@users.noreply.github.com
maintainer: id0sch@users.noreply.github.com
last-updated: 2026-03-31
---

# Package Audit — Real-Time Install Gate

Intercepts package install commands and requires security audit + explicit user approval before proceeding.

**Related:** `dep-review` covers PR-time dependency review. This skill covers real-time install-time gating.

## Scope

1. **Direct install commands:** `npm install`, `npx`, `yarn add`, `pnpm add`, `bun add`, `pip install`, `pip3 install`, `pipx install`, `uv add`, `brew install`, `cargo install/add`, `go install`, `curl | sh/bash`
2. **Dependency file edits:** Adding/upgrading deps in `requirements.txt`, `package.json`, `pyproject.toml`, `Pipfile`, `Cargo.toml`, `go.mod`, lockfiles
3. **New skills/automation:** Skills or scripts that reference external CLI tools or packages
4. **Dockerfile / CI changes:** `RUN pip install`, `RUN npm install`, etc.

## Rule 1: Never Install Without Approval

Do not run install commands, modify dependency files, or create skills that introduce new external packages without **explicit user approval first**.

## Rule 2: Security Checks (Before Presenting to User)

For each new package, run ALL checks from the **dep-review** skill (`.claude/skills/dep-review/SKILL.md` sections 2.1–2.7):

- **2.1 Typosquatting** — edit distance, substitution patterns
- **2.2 Known CVEs** — osv.dev API, GitHub advisories
- **2.3 License** — block GPL/AGPL/SSPL, warn unknown
- **2.4 Version pinning** — flag unpinned/floating versions
- **2.5 Popularity & maintainer signals** — downloads, stars, last publish, maintainer count
- **2.6 Necessity check** — grep codebase for actual usage
- **2.7 Suspicious signals** — install scripts, mismatched description, freshly published

Additionally check:

### Install scripts (JS packages)
```bash
npm view <package> scripts --json
```
If `preinstall`, `install`, or `postinstall` scripts exist → warn: "This package runs code on install via `<script_name>`. Review the script before approving."

### Scope / namespace
- Scoped packages (`@company/package`) = verified namespace, lower hijack risk
- Unscoped + low downloads = flag

## Rule 3: Present Findings

**Format as a distinct security checkpoint.** One block per package:

```
+---------------------------------------------+
|  PACKAGE SECURITY AUDIT                     |
+------------------+--------------------------+
| Package          | <name>@<version>         |
| Author           | <author>                 |
| License          | <license>                |
| Weekly downloads | <count>                  |
| Repository       | <url>                    |
| Last published   | <date>                   |
| Scoped?          | Yes (@scope/) / No       |
| Install scripts? | Yes (preinstall) / None  |
| Vulnerabilities  | X critical, Y high, Z mod|
| Known/trusted?   | Yes / No / Unknown       |
| Warnings         | <any flags, or "None">   |
+------------------+--------------------------+
| Approve this package? (yes/no)              |
+---------------------------------------------+
```

### Warning thresholds
- Critical/high CVE → **BLOCKED** — suggest alternative
- Has install scripts → "Runs code on install — review scripts before approving"
- Possible typosquat → "Name similar to `<popular_package>` — verify intended package"
- Weekly downloads < 1,000 → "Low popularity — higher supply-chain risk"
- Last published > 1 year → "Unmaintained"
- No repository URL → "No source repo linked — cannot verify code"
- Unscoped + low downloads → "Higher hijack risk"

## Rule 4: Get Explicit Approval

- **ALWAYS ask for explicit approval.** No exceptions.
- Do NOT infer consent from the user naming the package — the audit exists to catch typosquats.
- **Pin the version explicitly** (`numpy==2.2.4`, `lodash@4.17.21`).
- **Prefer lockfile-based installs** (`npm ci` over `npm install`).
- **Explain why** each package is needed.
- Wait for clear "yes" / "approved" / "go ahead" before running the command.

## Rule 5: Risky Patterns — Propose and Stop

For `curl | sh`, post-install scripts, unvetted registries, or packages with known CVEs: **propose the change, explain the risk, and stop.** Never auto-run.

## Rule 6: Exemptions (Skip Audit Block)

These don't need the full audit block:
- Packages already in committed `package.json`, lockfiles, `requirements.txt`, `pyproject.toml`, `Pipfile`, or `setup.py` (check with `git ls-files`)
- Well-known tools: `typescript`, `eslint`, `prettier`, `tsx`, `tsc`, `vite`, `esbuild`, `webpack`
- Lockfile-only reinstalls: `npm ci`, `pnpm install` (no args), `pip install -r requirements.txt`, `uv sync`

**Packages the user names in their prompt are NOT pre-approved.** Always run the audit checks.

## Rule 7: Dependency File Changes

When adding or upgrading packages in any dependency file:
1. Show a diff of exactly what lines change
2. Explain why each new package is needed
3. Flag if a package is new vs. a version bump
4. Do not save the file until user approves

## Rule 8: Skills and Automation

When creating skills or automation that reference external tools:
- List every external dependency the skill requires
- Do not embed install instructions that auto-run
- Prefer tools already available in the repo
- Pin versions (`npx package@1.2.3` not `npx package`)

## Rule 9: Dockerfile and CI

Same audit rules apply to `RUN pip install`, `RUN npm install` in Dockerfiles/CI:
- Each new package needs the audit block
- Prefer multi-stage builds with pinned base images
- Flag `--no-cache-dir` missing for pip in Docker
- Flag `npm install` without `--ignore-scripts` in CI
