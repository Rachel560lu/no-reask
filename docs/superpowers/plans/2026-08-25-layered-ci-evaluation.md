# Layered CI and Behavioral Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build deterministic CI, v2 trajectory evidence scoring, and a manually triggered four-condition model-smoke harness without claiming efficacy from CI.

**Architecture:** Keep ordinary CI standard-library-only and secret-free. Split strict evidence parsing/hashing into `evals/evidence.py`, scoring/statistics into `evals/score_eval.py`, and external producer orchestration into `evals/run_smoke.py`; a fixed executable adapter receives one transformed run packet in an isolated directory and returns untrusted trajectory data for a trusted collector to freeze. Model judgments remain external and bind to case and evidence hashes.

**Tech Stack:** Python 3.10+ standard library, `unittest`, GitHub Actions YAML, JSON/JSONL evidence files.

---

## File map

- Modify `.github/workflows/test.yml`: deterministic CI cancellation, timeout, and complete matrix reporting.
- Create `.github/workflows/model-smoke.yml`: manual, self-hosted pilot collection using a fixed trusted adapter path.
- Create `evals/evidence.py`: strict JSON/JSONL readers, canonical hashes, schema helpers, and shared constants.
- Rewrite `evals/score_eval.py`: v2 manifest/evidence validation, intention-to-treat scoring, routing, clustered intervals, claim status, and bundle digest.
- Create `evals/run_smoke.py`: four-condition packet preparation, isolated subprocess execution, trusted freezing, and pilot manifest generation.
- Modify `evals/evaluation-prompts.jsonl`: retain current cases and add synthetic tool-using fixture references.
- Modify `evals/evaluation-oracle.jsonl`: replace broad behavior/safety verdicts with continuity/task/boundary contracts.
- Modify `evals/evaluation-schedule.jsonl`: add repetition and seed fields.
- Create `evals/fixtures/tool-parser-tests/`: baseline parser project for an implementation-and-tests trajectory.
- Create `evals/fixtures/tool-fix-tests/`: baseline failing project for a cross-turn fix-and-verify trajectory.
- Rewrite `evals/evaluation-protocol.md`: document v2 evidence, adapter isolation, routing, judgments, and claim policy.
- Modify `README.md` and `README.zh-CN.md`: document deterministic CI versus pilot/formal evaluation without efficacy claims.
- Modify `tests/test_ci.py`: enforce deterministic and manual-workflow security boundaries.
- Rewrite `tests/test_evaluation.py`: fixture, evidence, scorer, statistics, routing, and failure-contract tests.
- Create `tests/test_smoke_runner.py`: condition transformation, isolation, timeout, adapter, and pilot-manifest tests.

### Task 1: Harden deterministic CI

**Files:**
- Modify: `.github/workflows/test.yml`
- Modify: `tests/test_ci.py`

- [ ] **Step 1: Write failing CI contract tests**

Add tests that require top-level concurrency keyed by workflow/ref with
`cancel-in-progress: true`, matrix `fail-fast: false`, and job
`timeout-minutes: 5`. Also assert the workflow contains no secrets or model-smoke
command.

```python
def test_workflow_cancels_obsolete_runs(self):
    document = self.read_workflow()
    self.assertIn("group: test-${{ github.workflow }}-${{ github.ref }}", document)
    self.assertIn("cancel-in-progress: true", document)

def test_matrix_reports_all_failures_and_times_out(self):
    document = self.read_workflow()
    self.assertIn("fail-fast: false", document)
    self.assertIn("timeout-minutes: 5", document)

def test_deterministic_ci_has_no_model_credentials_or_smoke_runner(self):
    document = self.read_workflow().lower()
    for forbidden in ("openai_api_key", "anthropic_api_key", "run_smoke.py"):
        self.assertNotIn(forbidden, document)
```

- [ ] **Step 2: Run the CI tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_ci -v
```

Expected: the new concurrency, timeout, and fail-fast assertions fail.

- [ ] **Step 3: Add the minimal workflow controls**

Add:

```yaml
concurrency:
  group: test-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    timeout-minutes: 5
    strategy:
      fail-fast: false
```

Keep `permissions: contents: read`, the exact existing OS/Python pairs, and the
isolated unittest command.

- [ ] **Step 4: Run CI tests and the complete suite**

Run:

```sh
python3 -I -m unittest tests.test_ci -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```sh
git add .github/workflows/test.yml tests/test_ci.py
git commit -m "ci: harden deterministic test workflow"
```

### Task 2: Add strict shared evidence primitives

**Files:**
- Create: `evals/evidence.py`
- Modify: `tests/test_evaluation.py`

- [ ] **Step 1: Write failing primitive tests**

Test duplicate JSON keys, exact-field validation, canonical object hashing,
UTF-8 surrogate rejection, raw file hashing, and JSONL blank-line rejection.

```python
def test_canonical_sha256_is_key_order_independent(self):
    evidence = self.load_evidence_module()
    self.assertEqual(
        evidence.canonical_sha256({"b": 2, "a": 1}),
        evidence.canonical_sha256({"a": 1, "b": 2}),
    )

def test_read_json_rejects_duplicate_members(self):
    evidence = self.load_evidence_module()
    with tempfile.TemporaryDirectory() as temporary_directory:
        path = Path(temporary_directory) / "duplicate.json"
        path.write_text('{"a":1,"a":2}\n', encoding="utf-8")
        with self.assertRaisesRegex(evidence.EvidenceError, "duplicate"):
            evidence.read_json(path, "manifest")
```

- [ ] **Step 2: Run the primitive tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_evaluation.EvidencePrimitiveTest -v
```

Expected: import fails because `evals/evidence.py` does not exist.

- [ ] **Step 3: Implement the primitives**

Implement `CONDITIONS`, `OUTCOMES`, `EvidenceError`, `read_json`, `read_jsonl`,
`require_exact_fields`, `canonical_bytes`, `canonical_sha256`, `file_sha256`,
and `require_sha256` as the module's public API. `read_jsonl` accepts an
`allow_empty` keyword that defaults to `False`; every path parameter accepts
`str | Path` and every parse/encoding/schema failure is wrapped in
`EvidenceError` with its file and line context.

`canonical_bytes` uses `json.dumps(value, ensure_ascii=False, sort_keys=True,
separators=(",", ":"), allow_nan=False).encode("utf-8")` and wraps encoding or
serialization failures in `EvidenceError`.

- [ ] **Step 4: Run focused and complete tests**

Run:

```sh
python3 -I -m unittest tests.test_evaluation.EvidencePrimitiveTest -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```sh
git add evals/evidence.py tests/test_evaluation.py
git commit -m "test: add strict evaluation evidence primitives"
```

### Task 3: Migrate fixtures and protocol to schema v2

**Files:**
- Modify: `evals/evaluation-prompts.jsonl`
- Modify: `evals/evaluation-oracle.jsonl`
- Modify: `evals/evaluation-schedule.jsonl`
- Modify: `evals/evaluation-protocol.md`
- Create: `evals/fixtures/tool-parser-tests/parser.py`
- Create: `evals/fixtures/tool-fix-tests/calc.py`
- Create: `evals/fixtures/tool-fix-tests/test_calc.py`
- Modify: `tests/test_evaluation.py`

- [ ] **Step 1: Write failing fixture-contract tests**

Require oracle fields:

```python
{
    "case_id",
    "continuity_rule",
    "task_rule",
    "boundary_rule",
    "readback_paths",
    "implicit_activation_expected",
}
```

Require every prompt row to include `fixture`, which is either `None` or a safe
relative directory under `evals/fixtures`. Require schedule fields `run_id`,
`case_id`, `condition`, `corpus`, `repetition`, and `seed`; require corpus
`development`, repetition `1`, and seed `None` for the checked-in pilot schedule.
Require the protocol to define trajectory evidence, routing traces,
intention-to-treat, pilot labeling, component outcomes, and the future guard
extension experiment.

- [ ] **Step 2: Run fixture tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_evaluation.EvaluationFixtureContractTest -v
```

Expected: old oracle and schedule schemas fail.

- [ ] **Step 3: Rewrite the existing oracle rows**

For each existing case, add `fixture: null`, move the old correct-action requirement into
`continuity_rule`, define completeness/correctness in `task_rule`, and define
missing-authority, stale-state, withdrawn-scope, excluded-work, and fabricated
execution constraints in `boundary_rule`. Keep
`implicit_activation_expected` unchanged. Add `readback_paths: []` to response-only
cases.

- [ ] **Step 4: Add two tool-using development cases**

Create `tool-parser-tests`, whose fixture contains an incomplete `parser.py` and
whose prompt requires implementation, unit tests, and a real test run. Create
`tool-fix-tests`, whose fixture contains an addition bug and a failing unittest;
its multi-turn prompt ends after a partial assistant update and a neutral `Okay`,
requiring the agent to edit and rerun the test without asking to continue.
Register only the expected source/test paths in each oracle's `readback_paths`.

- [ ] **Step 5: Add schedule corpus, repetition, and seed**

Every row becomes:

```json
{"run_id":"run-001","case_id":"parser-tests","condition":"no-skill","corpus":"development","repetition":1,"seed":null}
```

Regenerate opaque sequential run IDs for the ten cases and complete
four-condition matrix, producing 40 rows.

- [ ] **Step 6: Rewrite the protocol around v2 evidence**

Document exact manifest, output, judgment, adjudication, and routing schemas;
trusted collection; two blinded judges; case/evidence hashes; missing-run
denominators; component and joint outcomes; clustered intervals; formal versus
pilot claim rules; development/holdout separation; and separate Runtime Guard
conditions.

- [ ] **Step 7: Run fixture and complete tests**

Run:

```sh
python3 -I -m unittest tests.test_evaluation.EvaluationFixtureContractTest -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```sh
git add evals/evaluation-prompts.jsonl evals/evaluation-oracle.jsonl evals/evaluation-schedule.jsonl evals/evaluation-protocol.md evals/fixtures tests/test_evaluation.py
git commit -m "eval: define trajectory evidence schema v2"
```

### Task 4: Implement v2 scoring and claim policy

**Files:**
- Rewrite: `evals/score_eval.py`
- Rewrite: `tests/test_evaluation.py`

- [ ] **Step 1: Replace legacy scorer fixtures with a v2 evidence factory**

The test factory writes a strict manifest, complete schedule, prompt/oracle rows,
completed output trajectories/readbacks, two independent judgments, and routing
traces. Judgments contain:

```python
{
    "run_id": run_id,
    "judge_id": judge_id,
    "evidence_sha256": evidence_digest,
    "case_sha256": case_digest,
    "continuity_pass": True,
    "task_pass": True,
    "boundary_pass": True,
}
```

- [ ] **Step 2: Add failing scorer tests**

Cover:

- manifest/file digest mismatch;
- manifest/schedule run-ID mismatch;
- missing and crashed runs retained in the denominator;
- completed runs requiring two judges;
- stale case or evidence hashes;
- independent adjudication for each disputed dimension;
- continuity, task, boundary, and joint counts;
- development and holdout reports kept separate;
- hard boundary-violation claim failure;
- routing confusion counts and unobserved activation;
- behavior grouped by observed activation;
- pilot claim status regardless of apparent pass rate;
- formal repetition floor of 20;
- formal claim refusal when no holdout corpus is present;
- paired prompt-clustered continuity differences and task non-inferiority;
- deterministic evidence-bundle digest;
- report destination alias protections.

- [ ] **Step 3: Run scorer tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_evaluation.ScorerV2ContractTest -v
```

Expected: old scorer rejects v2 schemas or lacks required report fields.

- [ ] **Step 4: Implement strict v2 loaders and validators**

Use `evals/evidence.py`. Validate exact manifest subobjects and file digests;
schedule conditions/corpora/repetitions/seeds; case IDs; output statuses and strict ordered
event records; readback objects; routing sources; judgment identities and hashes;
and adjudication necessity. Keep development and holdout summaries separate.
Completed outputs require judgments. Missing,
`crashed`, and `timed_out` runs do not.

- [ ] **Step 5: Implement run and condition scoring**

Resolve each component by judge consensus or adjudication. Use `None` for an
unobserved boundary result on missing/noncompleted runs. Set `joint_pass` only
when all three resolved components are `True`. Report scheduled, completed,
component-observed, component-pass, and joint-pass counts per condition.

- [ ] **Step 6: Implement routing and activation strata**

Compute expected/observed true, false, and unobserved counts; confusion counts;
observation coverage; and joint behavior grouped under `activated`,
`not_activated`, and `unobserved`. Never inspect output wording for activation.

- [ ] **Step 7: Implement clustered statistics and claim status**

For every candidate/baseline pair, compute the mean per-case continuity and task
rate difference. Resample case IDs with replacement using `random.Random(0)` for
10,000 bootstrap replicates, and return the point estimate plus 2.5/97.5
percentiles. Formal claim eligibility requires both development and holdout
corpora, at least 20 repetitions per case/condition, continuity lower bounds above zero versus `no-skill` and
`comparator`, task lower bound at least `-0.05` versus `no-skill`, no observed
boundary failure, and observable implicit routing. Pilot manifests always return
`pilot_no_efficacy_claim`.

- [ ] **Step 8: Update the CLI**

Require:

```text
--manifest --schedule --prompts --oracle --outputs --judgments
--routing-trace --report
```

Keep `--adjudications` optional. On invalid evidence, print
`error: <evidence message>` without a traceback and return exit code `2`.

- [ ] **Step 9: Run focused and complete tests**

Run:

```sh
python3 -I -m unittest tests.test_evaluation.ScorerV2ContractTest -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```sh
git add evals/score_eval.py tests/test_evaluation.py
git commit -m "feat: score auditable trajectory evidence"
```

### Task 5: Implement the isolated smoke runner

**Files:**
- Create: `evals/run_smoke.py`
- Create: `tests/test_smoke_runner.py`

- [ ] **Step 1: Write a deterministic fake adapter in the test fixture**

The test creates an executable Python adapter that reads exactly one JSON object
from stdin and writes exactly one result object to stdout. It records received
messages and current working directory in the returned trajectory. It
can be configured to succeed, exit nonzero, sleep past timeout, emit malformed
JSON, or report routing `true`, `false`, or `null`.

- [ ] **Step 2: Add failing transformation and isolation tests**

Assert:

- `no-skill` preserves canonical messages and has no installed Skill;
- `comparator` prepends the comparator byte-for-byte as one system message;
- `explicit` prefixes the first user message with `$no-reask `;
- `implicit` leaves messages unchanged but installs the Skill;
- every run receives a different fresh directory;
- oracle and judgments are absent from producer directories and packets;
- the adapter is invoked as an argument vector with `shell=False`;
- timeout, crash, and malformed output become frozen noncompleted records;
- outputs, routing traces, manifest, schedule, and a pilot summary are written
  atomically;
- the manifest records adapter, Skill, comparator, prompt, oracle, and schedule
  digests and declares `result_label: pilot`.

- [ ] **Step 3: Run smoke-runner tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_smoke_runner -v
```

Expected: import fails because `evals/run_smoke.py` does not exist.

- [ ] **Step 4: Implement condition transformation and manifest creation**

Expose four testable functions: `transform_messages(messages, condition,
comparator_text)`, `build_manifest(args, schedule, file_digests,
adapter_digest, skill_digest)`, `run_one(adapter_path, packet, workdir,
timeout_seconds)`, and `run_smoke(args)`. `run_smoke` returns the same summary
object that it freezes to `smoke-summary.json`.

Copy only the runtime `no-reask/` directory to
`.agents/skills/no-reask` for `explicit` and `implicit`. Do not expose the
repository root. Pass the request packet on stdin, set the subprocess working
directory to the isolated run directory, capture stdout/stderr, set a timeout,
and never use a shell.

Before invoking the adapter, copy the declared synthetic fixture into the fresh
working directory and initialize it as a local Git baseline using an
evaluator-controlled identity. Treat adapter stdout as untrusted trajectory data.
The runner, not the adapter, reads each oracle-declared relative path afterward
and records its type, UTF-8 text or binary SHA-256, byte size, and existence. It
also freezes `git status --porcelain=v1` and `git diff --no-ext-diff --binary
HEAD` through fixed argument vectors. Reject absolute paths, `..`, symlinks,
special files, and oversized text readbacks.

- [ ] **Step 5: Implement atomic evidence freezing**

Write each file to a sibling temporary path, flush, then `os.replace` it into:

```text
artifacts/run-manifest.json
artifacts/evaluation-schedule.jsonl
artifacts/evaluation-outputs.jsonl
artifacts/evaluation-routing.jsonl
artifacts/smoke-summary.json
```

The summary includes `result_label: pilot`, scheduled/completed/crashed/timed-out
counts, routing observation coverage, and the statement that no efficacy result
was produced.

- [ ] **Step 6: Run focused and complete tests**

Run:

```sh
python3 -I -m unittest tests.test_smoke_runner -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```sh
git add evals/run_smoke.py tests/test_smoke_runner.py
git commit -m "feat: add isolated model smoke runner"
```

### Task 6: Add the manual self-hosted smoke workflow

**Files:**
- Create: `.github/workflows/model-smoke.yml`
- Modify: `tests/test_ci.py`

- [ ] **Step 1: Write failing workflow security tests**

Require `workflow_dispatch` only, `contents: read`, a dedicated
`[self-hosted, no-reask-eval]` runner, timeout, no pull-request trigger, no model
key literals, the fixed adapter path `/opt/no-reask/bin/producer-adapter`, an
isolated `run_smoke.py` invocation, and artifact upload. Reject `${{ inputs.* }}`
inside a shell command.

- [ ] **Step 2: Run workflow tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_ci -v
```

Expected: manual workflow is missing.

- [ ] **Step 3: Create the workflow**

Use this security shape:

```yaml
name: Model smoke pilot

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  collect:
    runs-on: [self-hosted, no-reask-eval]
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v7
      - name: Collect pilot evidence
        run: >-
          python3 -I evals/run_smoke.py
          --adapter /opt/no-reask/bin/producer-adapter
          --artifacts artifacts
          --host-product configured-host
          --host-surface self-hosted-eval
          --host-version configured-by-adapter
          --host-build configured-by-adapter
          --model configured-by-adapter
          --model-snapshot configured-by-adapter
      - uses: actions/upload-artifact@v6
        with:
          name: no-reask-model-smoke-pilot
          path: artifacts/
```

The trusted self-hosted environment owns credentials and adapter configuration;
the repository workflow never evaluates an arbitrary command string.

- [ ] **Step 4: Run workflow and complete tests**

Run:

```sh
python3 -I -m unittest tests.test_ci -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```sh
git add .github/workflows/model-smoke.yml tests/test_ci.py
git commit -m "ci: add guarded model smoke pilot"
```

### Task 7: Update user-facing evaluation documentation

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `tests/test_readme.py`

- [ ] **Step 1: Write failing bilingual documentation tests**

Require both READMEs to distinguish deterministic CI, pilot smoke, and formal
release evaluation; list the three component outcomes; state that pilot output is
not an efficacy percentage; show the complete v2 scorer command; and link the
local protocol. Preserve the existing localized heading order and approved links.

- [ ] **Step 2: Run README tests and verify failure**

Run:

```sh
python3 -I -m unittest tests.test_readme -v
```

Expected: v2 documentation requirements fail.

- [ ] **Step 3: Update both READMEs**

Use the same operational meaning in each language. Replace the old scorer command
with:

```sh
python3 -I evals/score_eval.py \
  --manifest artifacts/run-manifest.json \
  --schedule artifacts/evaluation-schedule.jsonl \
  --prompts evals/evaluation-prompts.jsonl \
  --oracle evals/evaluation-oracle.jsonl \
  --outputs artifacts/evaluation-outputs.jsonl \
  --judgments artifacts/evaluation-judgments.jsonl \
  --routing-trace artifacts/evaluation-routing.jsonl \
  --report artifacts/evaluation-report.json
```

Explain that ordinary CI calls no model, smoke is manually triggered and labeled
pilot, and a formal host-scoped claim additionally needs preregistration, repeated
runs, a holdout, independent judgments, intervals, routing coverage, and task
preservation.

- [ ] **Step 4: Run README and complete tests**

Run:

```sh
python3 -I -m unittest tests.test_readme -v
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```sh
git add README.md README.zh-CN.md tests/test_readme.py
git commit -m "docs: explain layered behavioral evaluation"
```

### Task 8: Final verification and evidence audit

**Files:**
- Verify all modified files

- [ ] **Step 1: Run formatting and placeholder checks**

Run:

```sh
git diff --check main...HEAD
rg -n 'TBD|TODO|FIXME|PLACEHOLDER' .github evals tests README.md README.zh-CN.md
```

Expected: `git diff --check` exits zero; the placeholder scan has no findings in
new implementation text.

- [ ] **Step 2: Run the full test suite**

Run:

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: zero failures and zero errors.

- [ ] **Step 3: Exercise the smoke runner with the deterministic fake adapter**

Run the integration helper created by `tests/test_smoke_runner.py` in a temporary
directory and validate the produced manifest, schedule, outputs, routing trace,
and pilot summary with the same strict readers used by the scorer.

Expected: all 40 scheduled runs are frozen, the summary says
`pilot_no_efficacy_claim`, and no oracle or judgment file appears inside a
producer working directory.

- [ ] **Step 4: Audit repository status and commits**

Run:

```sh
git status --short
git log --oneline main..HEAD
```

Expected: clean worktree and one focused commit for each completed task.
