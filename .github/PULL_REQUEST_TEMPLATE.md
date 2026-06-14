## Summary

<!-- Why is this change needed? What problem does it solve? Be specific — this becomes the permanent record of why this code exists. -->

## Changes

<!-- Bullet-point list of what changed. Focus on the "what" here since the Summary covers the "why". -->

-

## Testing

<!-- How did you verify this works? What edge cases did you consider and test? -->

## Related Issues

<!-- Required: every PR must reference an issue. Use "Closes #n" to auto-close or "Refs #n" to link without closing. -->

Closes #

## Checklist

**All boxes must be checked before a review will be started. Unchecked boxes = PR not ready.**

- [ ] Branch name follows `<type>/<short-description>` convention
- [ ] All commits follow [Conventional Commits](https://www.conventionalcommits.org/) format
- [ ] `pre-commit run --all-files` passes with zero errors
- [ ] `pytest backend/tests/` passes with zero failures
- [ ] Coverage thresholds met (`pytest --cov=backend --cov-report=term-missing`)
- [ ] `ruff check backend/` reports zero warnings
- [ ] No hardcoded secrets, credentials, or environment-specific values
- [ ] No commented-out code or debug `print()` statements
- [ ] No unrelated changes included in this PR
- [ ] Documentation updated where behaviour changed (API.md, ARCHITECTURE.md, etc.)
- [ ] PR title is a valid Conventional Commit subject line (it becomes the squash commit message)

---

> PRs that do not satisfy the checklist above will be closed with a request to fix and reopen.
> See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution guide.
