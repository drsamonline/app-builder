---
bump: minor
---

`repos()` gains a mode, `DRSOAM_REQUIRE_FULL_SCOPE=1`, in which a token that answers
but cannot see the private repositories is a **failure** rather than a smaller estate
to publish.

The defect this closes is not in `repos()`, which has always compared the two lists
and said so in `SCOPE`. It is in what the callers did with the fallback.
`knowledge/refresh.yml` set `GH_TOKEN: ${{ secrets.FANOUT_TOKEN || github.token }}`
— defensive-looking, and the opposite: with the secret absent, the fallback
authenticated as one repository, `/user/repos` returned that one repository, `repos()`
fell back to the public list, and the plan block counted **136 repos, 103 products,
14 kits** where the estate is **147, 111, 20**. The 11 private repositories are the
whole difference. Every run was green. The block published an under-count as fact
for weeks, and forge's refresh prompt spent three cycles describing it as an owner
action ("supply a read token") when the module had been handed a token it could not
use.

The mode is off by default, so a local run and any caller that legitimately wants the
public list are unchanged — `tests/test_full_scope.py` asserts both directions,
because a guard that is always on would break the callers it is not about.

The second half is diagnostic. A **rejected** credential and an **empty** estate both
arrive at `repos()` as an empty list, and for three cycles the first was reported as
the second. `_no_list_reason()` now names the URL, the reason, and says plainly that a
401/403 is a dead or revoked token rather than an empty account.

Six assertions, mutation-checked both ways: removing the guard turns the narrow-token
test red, and removing the rejection branch turns the diagnostic test red.
