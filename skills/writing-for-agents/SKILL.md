---
name: writing-for-agents
description: MUST use for all writing and messaging for AI agents, including discussions.
---

# Writing for agents

The reader of anything you write with this skill is an agent that has only the text. It did not see the conversation, cannot ask what you meant, and will act on what the words say, literally and with full effort. Most failures come from the gap between what you know and what made it onto the page. So work from the reader's position: before writing, settle where the work ends, what situation the reader is in, and what material it needs; then write it in words the reader can use without you.

Apply this skill to discussion and review as well as drafting and revision; discussion or review alone does not authorize rewriting. Messaging means composing or discussing message content, not merely sending or retrieving messages. When text is intended to guide an agent and also be read by humans, `reader-first-writing` can apply alongside this skill.

## Two kinds of input

**A rough request** ("write a brief so an agent fixes the flaky login test"): collect the facts from the conversation and the workspace, then draft from scratch.

**An existing prompt**: keep it. Make the smallest set of edits that fixes what is actually wrong, keep its structure and wording where they work, and add no requirement its author did not state. A full rewrite hides which change mattered and quietly drops intent the author had. The defaults below still apply: if the prompt lacks a role sentence, an example, or a closing check, add them. Whenever you add something, whether one of these or a rule that closes a real gap, list it when you deliver.

If a fact only the user knows would change what the reader delivers or what it may do, ask before writing: a few questions at most, each with your recommended answer. Otherwise choose a sensible default and list it as an assumption.

## Before writing

### Where the work ends

State the goal, why it matters (who uses the result, and for what), what counts as done, and what to hand back. Describe the destination, not the route: give the outcome, the success criteria, and the constraints, and let the reader choose the path. Current models plan better than a sequence you prescribe, and a step you guessed wrong still gets executed. List steps only where the order itself is a requirement, such as a migration that must run before a deploy.

> Before: 1. Open refresh.ts. 2. Wrap refresh() in try/catch. 3. Retry three times. 4. Run the tests.
>
> After: When a session times out, the client should renew the token silently so the user stays logged in. Done when the new timeout case in tests/auth/refresh.test.ts passes and no existing test fails. Keep the public API of AuthClient unchanged, because three other packages call it.

Turn quality adjectives into bars the reader can apply. "Thorough", "concise", and "only the important ones" get applied literally and unpredictably: a reviewer told to report only important issues will find the minor ones and stay silent about them. Name the threshold, or name what to keep and what to cut. If a later step filters the results, ask for everything.

> Before: Review carefully and report only important issues.
>
> After: Report every problem you find, including ones you are unsure of, and tag each as "breaks behavior" or "style only". A later step does the filtering.

### What situation the reader is in

When the text assigns a task (a brief, system prompt, issue, plan, or handoff), open with one role sentence: who the reader is, its function in this task, and the situation it is in. "You are the code reviewer for this pull request, which you did not write; the team plans to merge it today." The role sets the reader's perspective and what it is responsible for. Descriptions of a tool or skill have no role; they say what the thing does and when to use it.

Then tell the reader what it cannot see from where it sits: whether anyone can answer questions mid-task or it runs unattended; who else works in the same files or systems; whether its changes are reviewed or reversible; whether it should assess or change things; and what it may do without asking, including whether it may delegate further. Name the specific situations that warrant stopping to report. "Ask when unsure" leaves the reader to guess, and it ends up asking about everything or nothing.

> You run unattended; no one can answer questions until you finish. Stop and report only if the fix would delete data or touch code outside src/auth/. Another agent is editing docs/ at the same time, so leave that directory alone and don't revert changes you didn't make.

### What material the reader needs

For each source, give its location and what to take from it. Point to what the reader can open itself (file paths, commands, URLs it can reach) instead of paraphrasing, so it reads the real thing. Write out in full whatever exists only in your context: decisions made in conversation, the user's own words on a requirement, results of commands you ran, approaches already ruled out and why.

> Before: See docs/ and our earlier discussion.
>
> After: Read the "Refunds" section of docs/billing.md for the rounding rule. One requirement is in no file; the user's words were: "partial refunds must never exceed the original charge, even after currency conversion."

When you include logs, user text, or another agent's output, put it in a clearly marked block and say it is material to work from, not instructions. Keep your own instructions outside such blocks, because text inside quotes or data blocks is commonly treated as content with no authority.

## Writing it

Use the reader's words, not yours. While working you coined labels ("option B", "the lazy path", "the P2 issue") and shorthand ("→ lock contention") that mean nothing to the reader. Replace each with what it stands for, define real terms of art once, and write as if explaining fresh. When describing work done earlier, say who did it, so the reader does not believe it took those actions itself.

> Before: Option B ruled out (→ lock contention); continue with lazy-init, mind the P2 trap.
>
> After: The previous session ruled out rebuilding the connection pool on every request: under load, p95 latency rose from 80 ms to 400 ms because of lock contention. The current approach creates the pool on first use. One known problem remains: ...

Give each rule its reason in a clause ("…because a script parses this field"). The reason lets the reader handle cases you didn't list and shows how far the rule reaches. Skip it only when any capable model already knows the reason or the context makes it obvious.

State each rule once, in the place it belongs. Repetition doesn't add weight; it makes the reader over-apply the rule (repeated "ask first" lines turn into stalls on safe steps), and the copies drift apart over edits. For the same reason, use plain wording: no capitals, IMPORTANT, or pressure such as "this is critical" or "don't be lazy". Keep absolute words like never and always for true invariants, such as safety limits and irreversible actions.

Don't prescribe how to think. Leave out "think step by step" and requests to write reasoning into the answer or into tags; current models reason on their own, and some decline requests to transcribe their reasoning. If you need to see why, ask for a short explanation or the supporting evidence, such as file:line references or command output.

When fixing a known failure, write the principle behind it with its reason, not a ban on the one instance you saw. A list of bans covers only what it lists; a principle covers the neighboring cases too.

> Before: Don't use Object.create(). Don't use __proto__.
>
> After: Prefer explicit composition over prototype manipulation, because reviewers here favor code that reads top to bottom.

Write in paragraphs. Use lists only for items that are truly parallel or sequential: fields, ordered steps, independent checks. Bullets strip out the "because" and "unless" that connect instructions, and readers tend to mirror the format they are given.

Include one short example of what the reader should produce, marked as an example; it conveys form, tone, and level of detail better than a paragraph of description. Omit it only when the expected output is unmistakable from the words alone, such as a single command to run.

End a task-assigning text with a check the reader runs before reporting done: the command or test that proves the result when one exists, otherwise the done criteria to go back through. Ask it to state plainly anything it could not verify.

## Deliver

Hand over the finished text, ready to paste or already written to its file, in the language of the existing prompt or the one the user asks for. Outside it, list in a few lines the assumptions you made that the user may want to change. Keep your design notes out of the text itself.

Before delivering, read the draft as the reader would: capable, but holding only this page. Wherever it would have to guess what you meant, fix the page.
