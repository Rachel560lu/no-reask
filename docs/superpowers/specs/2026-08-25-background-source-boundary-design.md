# No Re-Ask Background and Safety Boundary Design

Date: 2026-08-25
Status: Approved and implemented

## Purpose

Add a concise, human-origin story for No Re-Ask while making the authorization
boundary unmistakable. The project must not imply that agents should skip tool,
security, or consequential-action approvals.

## Chosen approach

Follow the same layered pattern used by No Negative Echo:

1. Keep the README memorable and short.
2. Put the original complaint, interpretation, and source trail in
   `BACKGROUND.md`.
3. Link the two documents so the joke is easy to encounter and the evidence is
   easy to audit.

`BACKGROUND.md` will contain English and Chinese sections in one file. This
keeps the requested artifact singular while supporting both existing README
audiences.

## Source story

The primary source is u/BigBootyBear's August 2026 r/webdev post, "Is agentic AI
making you procrastinate?" The directly relevant complaint is that an agent asks
for approval or asks what comes next just as the user begins another activity,
then waits idle for input. The document may use brief attributed excerpts and
the comment-section phrase "babysitting and rubber-stamping" to preserve the
human voice.

The source is evidence of the interaction pain, not proof that every approval
prompt is redundant. An Anthropic source about approval fatigue may be included
as adjacent context, clearly distinguished from No Re-Ask's narrower behavior.

## Boundary statement

No Re-Ask carries forward authorization only when the next action is already
requested, clearly within scope, feasible, and reversible.

It does not bypass or suppress:

- tool or host approval gates;
- destructive or difficult-to-reverse actions;
- actions outside the stated scope;
- new credentials, external communications, deployment, publication, or other
  consequential authority not already granted;
- a genuinely missing choice or safety fact.

When any of those conditions applies, the agent should stop and ask one focused
material question.

## README changes

Both READMEs will receive a short source-linked sentence near the existing PR
example and a direct link to `BACKGROUND.md`. The existing humor remains the
main presentation; the new text should not turn the README opening into a
research report.

Both boundary sections will explicitly state that No Re-Ask does not mean
"skip safety approval" and will distinguish conversational re-asking from host
or tool permission prompts.

## Verification

Repository checks will verify that:

- `BACKGROUND.md` exists and both READMEs link to it;
- the background contains the primary Reddit source;
- both READMEs retain explicit language against bypassing approvals;
- the existing README, packaging, and behavioral-evaluation contracts still
  pass.

## Non-goals

- No claim that No Re-Ask eliminates all interruptions.
- No recommendation to enable unrestricted or dangerous permission modes.
- No change to the Skill's runtime behavior in this documentation-only update.
- No efficacy claim based on a social-media post.
