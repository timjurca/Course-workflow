# Routing: which skill answers which request

**Owner: skill `course-setup` (A).** A row is added here first and only then to a skill's own spec or
`SKILL.md`. The per-skill restatements are convenience; this table is the definition.

**Completeness rule.** Every request shape any skill can plausibly receive has a row here, including
the ones whose answer is *no skill does this*. A shape with no row is a defect in this file, not a
judgement call at runtime: when you meet one, answer the student, then say the table needs a row.

---

## State decides, not phrasing

Three of the boundaries below are settled by **what exists on disk**, not by how the student worded the
request. Casual phrasing is the normal case, and a routing rule that depends on verb choice breaks
exactly when it matters most.

Where a state rule applies, the asymmetry is always the same: one direction is cheap and reversible,
the other is expensive or destructive. The safe default points away from the destructive one.

- *"Summarise lesson 3"* sent wrongly to B runs a four-pass pipeline designed to run once per lesson,
  overwrites every correction D applied, and forces a replay. Sent wrongly to E it costs a paragraph.
- *"Study lesson 3"* sent wrongly to C produces questions from stale notes. Sent wrongly to B it
  rewrites notes that were already fine.

An explicit request to **regenerate**, **redo** or **write** the notes always reaches B, because it
names the artefact instead of asking a question.

---

## The table

| Request shape | Owner | Decided by |
|---|---|---|
| **A file is attached to the request** | **A files first**, always. Every other skill says "filing via course-setup first" and stops. | — |
| Set up a new subject or course, start a semester | A (`init`, `new semester`) | — |
| "Where does this go?", hands over slides, a transcript, a handout, an article, a book | A (`file`) | — |
| Hands over a past exam, official solutions, an assignment brief, a completed mock answer sheet | A (`file`), even when the same message asks for grading or questions. A files, then names the skill to run next. | — |
| Check, fix, validate or adopt a course folder; rename a course code; undo a filing; index a book; prepare revision folders; trim the filing log | A | — |
| Names a lesson **and** points at loose or unfiled material | A (`file`) | — |
| "Write / redo / regenerate the notes for L03", "consolidate this lesson", "process this lesson" | B | — |
| **"Summarise lesson 3", "what was lesson 3 about?"** | Notes current → **E**. Notes missing or stale → **B**. | **State** |
| "Study lesson N" | Notes current → **C** (`revise`). Missing or stale → **B**. | **State** |
| Questions, quiz, test me, practice, revise lesson N | C (`revise`) | — |
| Mock exam, practice exam, exam simulation | C (`mock`) | — |
| "Grade this", "check my answers", "am I ready?" | **C**, always | — |
| "What is still open?", readiness, coverage of a course | C (`status`) | — |
| "This is wrong", "fix the formula in L03", "the definition of X is incorrect" | D (`correct`) | — |
| "Go through the findings", "what is still open in the notes?" | D (`review`) | — |
| "Bring my corrections back", or any request right after B rewrote a lesson | D (`replay`) | — |
| "I edited the notes by hand" | D (`scan`) | — |
| "Undo the last correction" | D (`undo`) | — |
| **"I think this is wrong, but I am not sure"** | **D first.** D checks it against the sources. If the notes are right, D says so with the quote and the source ID and writes nothing. Explanation beyond that evidence is E's. | — |
| "Condense L03", "the short version of L03", "a revision sheet / cheat sheet / one-pager for L03", "I do not want to re-read the whole notes" | **F** (`condense`) | — |
| "Which lessons have a short version?", "are my revision sheets up to date?" | F (`status`) | — |
| "I do not understand X", "explain X", "why is this true?", "break this down", "make it simpler" | E (`explain`) | — |
| "Show me why that follows", "derive it" | E (`explain`), as a derivation | — |
| **"Why was my answer to Mock 01 Q3 wrong?"** | Feedback for that attempt exists → **E** (`why`). No feedback yet → E names **C** and stops. | **State** |
| "What do I need to know before X?" | E (`prereq`) | — |
| "Save that explanation" | E (`save`) | — |
| "That analogy does not work" | E records it in its rejected list. Opt-in only; never inferred. | — |
| "Test me", "quiz me", "give me practice questions" | **C.** E stops and names C. | — |
| **"Solve task 3", "do my assignment", "outline it for me", "just give me a hint"** | **No skill.** Every skill refuses, however it is phrased. | — |
| **"Write me a CV / an email to my lecturer / a document / a presentation / code"** | **No skill.** E explains and produces nothing else; the others do not produce prose at all. | — |
| Anything about a course in `archived_courses` | A, by explicit path only, or after reactivating it | — |

---

## The one inbound handoff to E

C's grading verdict and `status` may name E for a concept with graded failures: *"you lost marks on
instrument relevance twice — ask course-explain why."* That is the only place another skill points the
student at E.

E never points anyone at itself, and never invokes another skill. **No skill invokes another skill.**
Every skill names the one to run next and stops.

---

## When a request is genuinely ambiguous

State the action you are about to take before taking it, in one line. A one-word correction from the
student reroutes it. This is cheaper than a clarifying question and it leaves a visible trail.

For the `file` action A is stricter: a single weak match is asked about rather than acted on, because
a misrouted file is silent damage and a redundant question is not.

---

## Ambiguous phrasings seen in practice

Triggering is not tested by any script. This list is the record: real phrasings that turned out to be
ambiguous, and which skill should win. Add a line whenever a route goes wrong in real use, and check
the outcome again after any change to a skill `description`.

| Phrasing | Should reach | Why it is ambiguous |
|---|---|---|
| "summarise lesson 3" | B or E, by state | Both descriptions used to claim it. Documented in the state rule above. |
| "go through lesson 3 with me" | E | Reads like C ("study") but asks for explanation |
| "what did I get wrong?" | C if no feedback exists yet, E if it does | "wrong" also appears in D's rows |
| "the notes for L03 are a mess" | D (`scan` then `review`), not B | Sounds like a rewrite request |
| "can you clean up my course folder" | A (`validate`) | "clean up" also reads as deleting |
| "add this to lesson 3" with a file attached | A | The verb is B's, the object is A's |
| "summarise lesson 3 for revision" | F if the notes are current, else B | Reads as E's verb with C's purpose; the artefact asked for is F's |
| "make me notes I can revise from" | F | "notes" is B's word, but the notes already exist |
| "shorten lesson 3" | F | No other skill shortens anything |
