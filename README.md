<p align="center">
  <img src="./no-reask/assets/icon.svg" width="96" alt="No Re-Ask icon">
</p>
<h1 align="center">No Re-Ask</h1>
<p align="center"><strong>You already asked. Let the work continue.</strong></p>
<p align="center"><em>Finish authorized work without asking again.</em></p>
<p align="center"><strong>English</strong> · <a href="./README.zh-CN.md">中文</a></p>

<p align="center">
  <a href="https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml"><img src="https://github.com/Rachel560lu/no-reask/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.10+">
</p>

## The problem

This skill started with a message that should not exist:

> Continue.

You already said what to do. The agent understood, did part of it, and then handed the rest back as a new choice:

> **You:** “Review this PR. If only formatting issues remain, fix them directly and revalidate.”
>
> **Agent:** “I found two formatting issues. The fix is straightforward.”

```diff
- I can fix them. Would you like me to continue?
+ Fixed two formatting issues. Revalidation passed.
```

The agent did not lack understanding or authorization. It walked up to the elevator, saw that you had already pressed the button, and turned around to ask, “Still going up?”

No Re-Ask removes that unnecessary turn. When work is already requested, still in scope, and feasible now, the agent continues and reports the result. When a real choice, authority, or safety fact is missing, it still asks.

## How it works

The skill carries the authorization boundary of the current request forward until the requested work is completed, materially blocked, or explicitly withdrawn.

- Continue feasible work that remains inside the authorized scope.
- Report the completed outcome and concrete evidence, such as a fresh test result.
- Ask one concise material clarification when a genuinely missing choice, authority, or safety fact prevents correct action.
- Finish the requested scope before offering optional, adjacent suggestions.

Partial progress, elapsed time, long-running work, context changes, and turn boundaries are not blockers by themselves. They are reasons to preserve state and continue, not reasons to ask whether already-requested work should be done.

## Use cases

- Applying an already-requested fix after diagnosis instead of asking for the same permission again.
- Continuing after a progress update, long test run, tool call, or turn boundary.
- Finishing an explicit review or recommendation instead of returning the final decision to the user.
- Asking one focused question when a genuinely missing target, authority, or safety fact blocks the next action.

## No Re-Ask and Goal

**Goal tells the elevator which floor to reach. No Re-Ask keeps it from stopping at every floor to ask, “Still going?”**

They solve different problems:

| | Codex Goal | No Re-Ask |
|---|---|---|
| Question answered | What outcome must be reached? | Is this next step already authorized? |
| What it keeps | A durable objective and stopping condition | The authorization boundary of the current request |
| Best fit | Long-running work across turns with a validation loop | Redundant permission questions in ordinary work |
| It does not | Supply missing authorization | Create a persistent execution loop |

They can work together: Goal keeps the destination in view; No Re-Ask keeps the agent from needlessly stopping on the way. See the official [Codex Goal documentation](https://learn.chatgpt.com/use-cases/follow-goals) for its long-running, verifiable workflow.

## Installation

Run the following guarded block from the root of the cloned repository. It creates a link to the installable runtime, but refuses to overwrite an existing file, directory, live symbolic link, or dangling symbolic link at the target path.

```sh
skill_target="${HOME}/.codex/skills/no-reask"

if [ -e "$skill_target" ] || [ -L "$skill_target" ]; then
  printf '%s\n' "$skill_target already exists; rename or remove it before installing."
else
  mkdir -p ~/.codex/skills
  ln -s "$(pwd)/no-reask" "$skill_target"
fi
```

## Usage

Invoke the skill explicitly in an important request:

```text
$no-reask Review this PR. If only formatting issues remain, fix them directly and revalidate.
```

It also applies to recommendation work:

```text
$no-reask Review the available options, choose one, and give me the final recommendation with reasons.
```

Implicit discovery may occur after the skill is installed, but explicit invocation is the most reliable choice for important tasks.

## Decision boundary

| State | Action |
|---|---|
| Requested work is unfinished and feasible | Continue and complete it. |
| Requested work is complete | Report the outcome and supporting evidence. |
| A material choice, authority, or safety fact is missing | Ask one concise material clarification that covers the known blocker while preserving progress. |
| Work is optional and adjacent to the request | Finish the requested scope first; suggest the extra work afterward only if useful. |

A material clarification requests new information needed to act correctly or safely. It is not repeated permission for work already requested. Progress updates, elapsed time, and turn boundaries do not create a new authorization boundary.

## Boundaries

No Re-Ask is a behavior skill and prompt-level mitigation. It has no runtime service or external dependency, and it is not a phrase blacklist: the decision depends on scope and state, not forbidden wording.

The skill cannot guarantee activation in every interaction, and it does not erase context or control logs. It does not expand authorization, invent credentials, bypass approvals, make unsafe assumptions, or introduce scope creep. When a genuinely material fact is missing, the correct behavior is still to ask one focused clarification.

## Behavioral evaluation

The behavioral evaluation uses a frozen prompt set, oracle, and schedule across four conditions: no-skill, comparator, explicit invocation, and implicit discovery. Model responses are generated externally and judgments are made independently; the scorer is deterministic and uses only the Python standard library.

Follow the local [`evals/evaluation-protocol.md`](evals/evaluation-protocol.md), then score the prepared outputs and judgments with:

```sh
python3 -I evals/score_eval.py --schedule evals/evaluation-schedule.jsonl --outputs artifacts/evaluation-outputs.jsonl --judgments artifacts/evaluation-judgments.jsonl --report artifacts/evaluation-report.json
```

The checks validate the evaluation structure and scoring mechanics. Passing continuous integration does not measure behavioral efficacy, and this README does not claim an effect result.

## Repository structure

The installable runtime contains:

- `no-reask/SKILL.md` — behavior instructions and the decision boundary.
- `no-reask/agents/openai.yaml` — agent-facing display metadata and the default prompt.
- `no-reask/assets/icon.svg` and `icon-400.png` — the project symbol in scalable and raster formats.

Development evidence remains outside the installable runtime:

- `evals/` — the frozen evaluation materials, protocol, and deterministic scorer.
- `tests/` — automated repository contract checks.
- `.github/workflows/test.yml` — the continuous integration workflow.

## Development

Run the complete local test suite from the repository root:

```sh
python3 -I -m unittest discover -s tests -p 'test_*.py' -v
```

## Feedback

For a behavior gap, include the original request, the actual output, the expected output, and whether the skill was invoked explicitly or discovered implicitly. Remove credentials and private or internal information before sharing the report.
