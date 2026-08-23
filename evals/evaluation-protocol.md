# Behavioral evaluation protocol

This protocol measures responses to the frozen prompts in `evaluation-prompts.jsonl` under four conditions. Response generation is external: the scorer does not generate responses or call a model or API.

## Canonical prompts and condition transformations

Treat each `messages` array in `evaluation-prompts.jsonl` as the canonical prompt. Construct each condition exactly as follows:

- `no-skill`: use the canonical prompt messages unchanged. The No Re-Ask skill is absent.
- `comparator`: keep the skill absent and prepend exactly one `system` message whose content is the exact contents of `comparator.txt`, byte for byte, including its final newline. Leave every canonical message unchanged after it.
- `explicit`: install the skill, copy the canonical messages, and prefix the first `user` message content with `$no-reask `. Make no other message or content change.
- `implicit`: install the skill and use the canonical prompt messages unchanged. Do not name or explicitly invoke the skill in any injected instruction.

Generate every scheduled response externally in a fresh context. A producer may see only the transformed messages for its condition and the declared generation environment; it must never see `evaluation-oracle.jsonl`. Save the response string exactly as generated and do not regenerate or normalize frozen output.

Before generation, write the shared environment declaration to `artifacts/run-manifest.json`. It is one JSON object with exactly this schema:

```json
{"experiment_id":"string","host":"string","host_version":"string","model":"string","model_version":"string","settings":{}}
```

The `settings` object records every generation setting used. Use the same declared host, host version, model, model version, and settings for every run; one shared manifest covers all four conditions. The scorer does not validate environment parity, so the evaluation controller must enforce and audit this requirement.

## Evidence schemas

Each evidence file is UTF-8 JSON Lines with one object per non-blank line. Fields are exact: no omitted or additional fields are allowed, and duplicate object member names are invalid at any nesting level.

Prompt rows in `evaluation-prompts.jsonl`:

```json
{"case_id":"string","title":"string","tags":["string"],"messages":[{"role":"user|assistant|system","content":"string"}]}
```

Oracle rows in `evaluation-oracle.jsonl`:

```json
{"case_id":"string","behavior_rule":"string","safety_rule":"string","implicit_activation_expected":true}
```

Schedule rows in `evaluation-schedule.jsonl` use opaque run IDs and contain exactly one row for every case and condition:

```json
{"run_id":"run-001","case_id":"string","condition":"no-skill|comparator|explicit|implicit"}
```

Externally produced output rows:

```json
{"run_id":"string","case_id":"string","condition":"no-skill|comparator|explicit|implicit","response":"string"}
```

Independent judge rows:

```json
{"run_id":"string","judge_id":"string","output_sha256":"lowercase UTF-8 response SHA-256","behavior_pass":true,"safety_pass":true}
```

Adjudication rows, used only for disputed runs:

```json
{"run_id":"string","output_sha256":"lowercase UTF-8 response SHA-256","behavior_pass":true,"safety_pass":true,"reason":"string"}
```

## Blinded judging and adjudication

The evaluation controller privately maps each scheduled output to an opaque `blind_id`. It gives a judge a blind packet containing only the opaque `blind_id`, canonical untransformed prompt, frozen response, and the matching behavior and safety oracle rules. A packet can use this shape:

```json
{"blind_id":"opaque string","canonical_prompt":{"messages":[{"role":"user","content":"string"}]},"response":"string","oracle_rules":{"behavior_rule":"string","safety_rule":"string"}}
```

The blind packet must not contain the condition, injected instruction, run ID, or case name. Collect at least two independent, blinded judge records for every output. Judges must not see the private mapping, condition label, or each other's judgments. Bind every judgment to the exact frozen response with the lowercase SHA-256 digest of its UTF-8 bytes. Only after receiving an independent verdict does the controller map its `blind_id` back to `run_id` and write the judgment row.

Any disagreement on behavior or safety makes that run disputed. After all first-pass judgments have been collected, give one independent adjudicator the same blind packet plus only the behavior and safety disagreements for that output. Do not reveal condition, case or run naming, or judge identities. Obtain exactly one adjudication for each disputed run, bound to the same response hash; do not create adjudications for undisputed runs. The adjudicator resolves each disputed dimension, while judge consensus on the other dimension remains unchanged.

Judge and adjudicator independence is procedural: use distinct people or processes with no access to one another's work except for the adjudicator's disclosed disagreement after first-pass collection. The scorer validates distinct judge IDs and adjudication use, but it cannot establish procedural independence or blinding.

## Scoring

Run the standard-library scorer after response generation and judging are complete:

```sh
python3 -I evals/score_eval.py --schedule evals/evaluation-schedule.jsonl --outputs artifacts/evaluation-outputs.jsonl --judgments artifacts/evaluation-judgments.jsonl --adjudications artifacts/evaluation-adjudications.jsonl --report artifacts/evaluation-report.json
```

Omit `--adjudications` when the judges agree on both dimensions for every run. The scorer validates the complete four-condition schedule, evidence schemas, identities, response hashes, and dispute handling before reporting pass counts per condition.

Continuous integration validates the frozen fixtures and scorer only. Passing continuous integration is not evidence of behavioral efficacy; response generation, environment parity, judgments, and adjudication remain external to it.
