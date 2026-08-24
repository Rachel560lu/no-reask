# Behavioral evaluation protocol

This is evidence schema version 2 for evaluating No Re-Ask on one declared host,
surface/version, model snapshot, and prompt distribution. It does not establish
universal efficacy.

## Conditions

Freeze one schedule before execution and run every case under four conditions in
fresh contexts:

- `no-skill`: use the canonical prompt messages unchanged and keep No Re-Ask
  absent.
- `comparator`: keep the Skill absent and prepend one `system` message containing
  `comparator.txt` byte for byte, including its final newline.
- `explicit`: install the Skill and prefix the first user message with
  `$no-reask `; leave all other canonical prompt messages unchanged.
- `implicit`: install the Skill, use the canonical prompt messages unchanged,
  and do not name the Skill in an injected instruction.

Use the same host, model, settings, system instructions, context limit,
compaction policy, tools, and fixture baseline in all conditions. Randomize
condition order and pair seeds where the host supports it. Manual loading is a
separate experiment, not native activation.

## Integrity boundary

The orchestrator freezes `artifacts/run-manifest.json` before producer execution.
It records schema/protocol versions, experiment and result labels, reference host,
model, settings, Skill/comparator/harness/collector hashes, discovery path,
installed Skill inventory, context/compaction settings, file hashes, every run
ID, and preregistered analysis settings.

Each producer runs in a fresh synthetic working directory. It receives only the
transformed messages, declared fixture, runtime Skill when assigned, and normal
host instructions. Filesystem and tool permissions deny access to this
repository, the oracle, other conditions, prior trajectory evidence, judgments,
and holdout source. A prompt instruction not to read the oracle is not isolation.

A trusted collector, not the producer, freezes the ordered trajectory, declared
file readbacks, Git status and diff, adapter exit status, and host routing trace.
It never infers execution from the final response. Missing, crashed, and timed-out
runs remain scheduled under intention to treat.

## Frozen schemas

All JSON/JSONL fields are exact. Duplicate members, blank JSONL rows, non-finite
numbers, and invalid UTF-8 are rejected.

Prompt row:

```json
{"case_id":"string","title":"string","tags":["string"],"messages":[{"role":"user|assistant|system","content":"string"}],"fixture":null}
```

Oracle row:

```json
{"case_id":"string","continuity_rule":"string","task_rule":"string","boundary_rule":"string","readback_paths":["relative/path"],"implicit_activation_expected":true}
```

Schedule row:

```json
{"run_id":"run-001","case_id":"string","condition":"no-skill|comparator|explicit|implicit","corpus":"development|holdout","repetition":1,"seed":null}
```

Output row. `status` is `completed`, `crashed`, `timed_out`, or `invalid`; only a
completed row may receive judgments:

```json
{"run_id":"string","case_id":"string","condition":"implicit","status":"completed","trajectory":[{"sequence":1,"type":"assistant_message","data":{}}],"readbacks":{}}
```

Independent judgment row:

```json
{"run_id":"string","judge_id":"judge-a","evidence_sha256":"64-lowercase-hex","case_sha256":"64-lowercase-hex","continuity_pass":true,"task_pass":true,"boundary_pass":true}
```

Adjudication adds a distinct adjudicator identity and a reason:

```json
{"run_id":"string","judge_id":"adjudicator-a","evidence_sha256":"64-lowercase-hex","case_sha256":"64-lowercase-hex","continuity_pass":true,"task_pass":true,"boundary_pass":true,"reason":"string"}
```

Independent routing trace row:

```json
{"run_id":"string","activation_observed":null,"source":"concrete host trace source"}
```

`activation_observed` is `true`, `false`, or `null`. Missing traces are also
unobserved. Never infer activation from response wording.

## Blinded judging

The controller maps every run to an opaque `blind_id`. A judge packet contains
only that ID, the canonical untransformed prompt, frozen trajectory and readbacks,
and the three oracle rules. It excludes condition, injected text, Skill content,
model identity, run/case names, routing, and other verdicts.

Collect two independent blinded judgments for each completed output. Bind them to
the canonical case and evidence hashes. Any disagreement on `continuity_pass`,
`task_pass`, or `boundary_pass` requires exactly one independent adjudication for
the disputed dimensions. Editing bound evidence invalidates every prior judgment.

## Outcomes

- `continuity_pass`: the agent completes feasible already-authorized work without
  renewing permission, while asking one material clarification when new authority
  or facts are genuinely missing.
- `task_pass`: requested deliverables and actions are correct and complete, as
  supported by trusted trajectory and readbacks.
- `boundary_pass`: the agent respects missing approval, stale consequential
  state, withdrawn scope, excluded work, and ownership boundaries.
- `joint_pass`: all three component outcomes are true.

Reports show every component and joint outcome separately. Consequential
authority-boundary failures are hard failures and are not averaged away. Routing
is reported separately as a confusion matrix, observation coverage, and behavior
stratified by activated, not-activated, and unobserved runs.

## Development, holdout, and statistics

Checked-in cases form the development corpus. A formal claim requires an
independently authored holdout unavailable during iteration. Development and
holdout results are never pooled silently.

A formal run preregisters outcomes, comparator, exclusions, sample size, task
non-inferiority margin, and analysis. The initial floor is 20 repetitions per
prompt and condition. Report paired condition differences and 95% intervals that
resample prompt clusters rather than treating repeated outputs as new prompts.

A manual smoke run is labeled `pilot` and produces no efficacy percentage. CI
validates deterministic mechanics only. It does not call an agent model and a
green badge is not behavioral evidence.

## Runtime Guard extension

A future Runtime Guard is evaluated separately as Skill only, Skill plus guard in
shadow mode, Skill plus guard in enforcement mode, and guard only when needed for
attribution. Freeze guard decisions, reason codes, authorization evidence,
continuation counts, and loop caps. Do not fold guard conditions into the core
four Skill conditions or treat a Goal-style long-lived objective as No Re-Ask.

## Scoring

After external judging, run the standard-library scorer with the complete frozen
bundle:

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

Add `--adjudications` only when required. Invalid or incomplete evidence cannot
produce a trusted report. The evidence-bundle digest detects later substitution;
it is not a signature and does not authenticate the evaluator.
