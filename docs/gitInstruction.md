# Git Workflow Instructions

## Commit Style
- **Small, focused commits** — one logical change per commit
- **Short imperative messages** — as a senior dev would write

## Commit Message Format
```
<type>: <short description>
```

### Types
| Type | When to use |
|---|---|
| `feat` | New feature or functionality |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `chore` | Build, config, tooling |

### Examples
```
feat: add LP optimizer with neutrality constraint
fix: handle no_op directive in guardrails
docs: add optimization formula to spec
refactor: extract battery dynamics into separate module
test: add edge case for zero-demand hour
chore: add Dockerfile and health endpoint
```

## Rules
1. **Never commit broken code** — run tests before committing
2. **One logical unit per commit** — if you fix a bug and refactor, make two commits
3. **No secrets, keys, or .env files** — ever
4. **Write commit messages in present tense** — "add feature" not "added feature"
5. **Keep lines under 72 characters** in commit messages
6. **Stage before committing** — never `git commit -a` (review what you're committing)
7. **Write descriptive PR descriptions** — what changed, why, how to test
