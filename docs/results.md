# Results — run `main`, 2026-10-11

Workload: synthetic production logs. Train and gate tasks have 2,000 lines (about 150k tokens if read inline);
the long split has 16,000 lines, 8x longer than anything the evolution trained on. Worker: Gemini 3.8 Flash.
Engineer: Claude Opus 5.5. 8 generations, 3 candidates each.

## Headline

| harness | train (12) | gate (8, held out) | long (8, 8x longer) | tokens per task, train | tokens per task, long |
| --- | --- | --- | --- | --- | --- |
| generation 0 (plain inline) | 0.83 | 0.87 | 0.38 | 149,983 | 1,438,737 |
| final champion `ccd980aa` (generation 5) | 1.00 | 1.00 | 1.00 | 4,261 | 5,079 |

On the long split the champion gets every answer for about 283x fewer tokens ($0.046 vs $9.19 for 8 tasks).
Each long input is about 1.03M tokens, right at Gemini 3.8 Flash's 1M window. Generation 0's first reply fits,
but 3 of its 8 runs overflowed the window when a second turn re-sent the history (400 INVALID_ARGUMENT), and it
answered 3 of the other 5 correctly (both needles, one top-k). Its token figure counts those re-sent turns. The
evolved harness keeps the data in the REPL, so input size never touches its context.

## What happened

- **Generation 1:** all three proposals moved the data into the REPL and counted in Python. The best scored
  1.00 on train but fell from 0.87 to 0.62 on the held-out gate: the worker wrote imagined ```output blocks
  and answered from them. The gate rejected it as **overfit**.
- **Generation 2:** the engineer read its rejected siblings' failures, named both failure modes (gen-0
  counting drift; catalog truncation and imagined outputs), turned on `stop_at_output`, and wrote a
  `log_catalog` skill. **Accepted:** train 1.00, gate 1.00, 10,010 tokens per task.
- **Generations 3 and 5:** cost-focused patches cut tokens to 6,516 and then 4,261 at full accuracy.
  **Accepted.**
- **Generations 4, 6, 7, 8:** candidates saved under the 15% bar and were rejected as no gain.

### Champion path (main)

| gen | genome | train | gate | long | tokens/task (train) | patch |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 084db956 | 0.83 | 0.87 | 0.38 | 149,983 | (none) |
| 2 | daf2764d | 1.00 | 1.00 | 1.00 | 10,010 | set repl=true; set context_mode="repl"; set max_obs_chars=16000; set stop_at_output=true; put_skill log_catalog; add_not |
| 3 | 34bfc7fd | 1.00 | 1.00 | - | 6,516 | add_note 'Be economical: every extra turn re-sends the whole catalog. Target 3 replies: (1'; set limits.max_steps=8 |
| 5 | ccd980aa | 1.00 | 1.00 | 1.00 | 4,261 | put_skill pick_templates; remove_note #3; remove_note #1; remove_note #0; add_note 'The log is only in the REPL string ` |

### Every candidate

| gen | genome | focus | status | train | tokens/task | reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | d2c681c1 | accuracy | not_selected | 1.00 | 32,788 | train acc 0.83 -> 1.00 |
| 1 | 1baa83d7 | cost | rejected_no_gain | 0.68 | 25,909 | no train gain: acc 0.83 -> 0.68, tokens/task 149,983 -> 25,909 |
| 1 | c6556a93 | free | rejected_overfit | 1.00 | 30,702 | train acc 0.83 -> 1.00; train gain +0.17 did not hold out: gate acc 0.87 -> 0.62 |
| 2 | e1c01836 | accuracy | not_selected | 1.00 | 31,111 | train acc 0.83 -> 1.00 |
| 2 | 50949e4f | cost | not_selected | 1.00 | 15,468 | train acc 0.83 -> 1.00 |
| 2 | daf2764d | free | accepted | 1.00 | 10,010 | train acc 0.83 -> 1.00; gate acc 0.87 -> 1.00 |
| 3 | 742bebf3 | accuracy | rejected_no_gain | 1.00 | 9,932 | no train gain: acc 1.00 -> 1.00, tokens/task 10,010 -> 9,932 |
| 3 | 34bfc7fd | cost | accepted | 1.00 | 6,516 | train acc held at 1.00; tokens/task 10,010 -> 6,516; gate acc 1.00 -> 1.00 |
| 3 | 26cbd9f5 | free | rejected_no_gain | 1.00 | 10,812 | no train gain: acc 1.00 -> 1.00, tokens/task 10,010 -> 10,812 |
| 4 | 7cc857a0 | accuracy | rejected_no_gain | 1.00 | 5,580 | no train gain: acc 1.00 -> 1.00, tokens/task 6,516 -> 5,580 |
| 4 | 54582410 | cost | rejected_no_gain | 1.00 | 6,223 | no train gain: acc 1.00 -> 1.00, tokens/task 6,516 -> 6,223 |
| 4 | 86233b80 | free | rejected_no_gain | 1.00 | 6,291 | no train gain: acc 1.00 -> 1.00, tokens/task 6,516 -> 6,291 |
| 5 | 9d1b7f95 | accuracy | rejected_no_gain | 1.00 | 6,429 | no train gain: acc 1.00 -> 1.00, tokens/task 6,516 -> 6,429 |
| 5 | ccd980aa | cost | accepted | 1.00 | 4,261 | train acc held at 1.00; tokens/task 6,516 -> 4,261; gate acc 1.00 -> 1.00 |
| 5 | 0ec31dcc | free | not_selected | 1.00 | 5,489 | train acc held at 1.00; tokens/task 6,516 -> 5,489 |
| 6 | 8e12e345 | accuracy | rejected_no_gain | 1.00 | 4,308 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 4,308 |
| 6 | 50a77a41 | cost | rejected_no_gain | 1.00 | 4,147 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 4,147 |
| 6 | 369dcd52 | free | rejected_no_gain | 1.00 | 5,989 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 5,989 |
| 7 | 17e233a3 | accuracy | rejected_no_gain | 1.00 | 4,320 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 4,320 |
| 7 | 6b572d17 | cost | rejected_no_gain | 1.00 | 3,952 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 3,952 |
| 7 | 5a75e9a0 | free | rejected_no_gain | 1.00 | 4,314 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 4,314 |
| 8 | 738cc1bd | accuracy | rejected_no_gain | 1.00 | 4,343 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 4,343 |
| 8 | e096eee3 | cost | rejected_no_gain | 1.00 | 4,246 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 4,246 |
| 8 | 2fb96a25 | free | rejected_no_gain | 1.00 | 7,650 | no train gain: acc 1.00 -> 1.00, tokens/task 4,261 -> 7,650 |

---

# Results — run `tickets` (second workload), 2026-10-11

Workload: a synthetic support inbox. Each ticket has one hidden intent (refund, cancel, shipping, login,
double charge, praise), phrased combinatorially with negated decoys ("I'm not asking for a refund").
Train and gate inboxes have 1,500 tickets (about 50k tokens); the long split has 12,000. Same loop, same
engineer, same starting genome as run `main`. Count questions get partial credit (1 - 10 x relative error).
5 generations, 3 candidates each.

## Headline

| harness | train (12) | gate (8, held out) | long (8, 8x longer) | tokens per task, train | tokens per task, long |
| --- | --- | --- | --- | --- | --- |
| generation 0 (plain inline) | 0.95 | 0.97 | 0.30 | 117,740 | 709,538 |
| champion `68547efa` (generation 3) | 1.00 | 1.00 | 0.87 | 65,714 | 266,782 |

## A different species

- **Generations 1-2:** every proposal moved the inbox into the REPL and wrote a skill that has the
  sub-model classify tickets (`classify_records`, `find_matching`). They cut tokens up to 44% but lost
  a top-k or count question, and the gate rejected all six (gen-0's 0.95 left no room for losses).
- **Generation 3:** `tag_records` parses every ticket, removes duplicate texts, has the sub-model tag each
  unique text with the intents it really expresses (negated mentions excluded), and counts in code.
  **Accepted:** train 1.00, gate 1.00, 44% fewer tokens.
- **Generations 4-5:** savings under 15%, rejected.

On logs the loop evolved toward *computing* (parse and count in Python, no sub-calls); on tickets it
evolved toward *delegating reading* to sub-model calls. The two species scale differently: on 8x longer
inputs the logs champion's cost barely moved (4,261 to 5,079 tokens per task) while the tickets champion's
grew with the data (65,714 to 266,782) until it hit its 150-sub-call budget, which cost it one pairs
question (0.00) while every count stayed exact.

### Champion path (tickets)

| gen | genome | train | gate | long | tokens/task (train) | patch |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | ac82e342 | 0.95 | 0.97 | 0.30 | 117,740 | (none) |
| 3 | 68547efa | 1.00 | 1.00 | 0.87 | 65,714 | set repl=true; set context_mode="repl"; set limits.max_subcalls=150; set stop_at_output=true; put_skill tag_records; add |

### Every candidate

| gen | genome | focus | status | train | tokens/task | reason |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | f645dbdf | accuracy | rejected_no_gain | 0.58 | 151,026 | no train gain: acc 0.95 -> 0.58, tokens/task 117,740 -> 151,026 |
| 1 | e63ec44e | cost | rejected_no_gain | 0.54 | 79,815 | no train gain: acc 0.95 -> 0.54, tokens/task 117,740 -> 79,815 |
| 1 | 4cdd06fe | free | rejected_no_gain | 0.92 | 106,765 | no train gain: acc 0.95 -> 0.92, tokens/task 117,740 -> 106,765 |
| 2 | 539b2e1e | accuracy | rejected_no_gain | 0.80 | 66,086 | no train gain: acc 0.95 -> 0.80, tokens/task 117,740 -> 66,086 |
| 2 | 5ef1eba8 | cost | rejected_no_gain | 0.78 | 87,099 | no train gain: acc 0.95 -> 0.78, tokens/task 117,740 -> 87,099 |
| 2 | 53c3e54f | free | rejected_no_gain | 0.92 | 76,193 | no train gain: acc 0.95 -> 0.92, tokens/task 117,740 -> 76,193 |
| 3 | 68547efa | accuracy | accepted | 1.00 | 65,714 | train acc held at 1.00; tokens/task 117,740 -> 65,714; gate acc 0.97 -> 1.00 |
| 3 | fc848954 | cost | rejected_no_gain | 0.86 | 109,167 | no train gain: acc 0.95 -> 0.86, tokens/task 117,740 -> 109,167 |
| 3 | 1b195da0 | free | rejected_no_gain | 1.00 | 103,282 | no train gain: acc 0.95 -> 1.00, tokens/task 117,740 -> 103,282 |
| 4 | c77c7ef0 | accuracy | rejected_no_gain | 1.00 | 66,507 | no train gain: acc 1.00 -> 1.00, tokens/task 65,714 -> 66,507 |
| 4 | dfda46b0 | cost | rejected_no_gain | 1.00 | 62,578 | no train gain: acc 1.00 -> 1.00, tokens/task 65,714 -> 62,578 |
| 4 | f6b6b2c3 | free | rejected_no_gain | 1.00 | 66,255 | no train gain: acc 1.00 -> 1.00, tokens/task 65,714 -> 66,255 |
| 5 | b1b0c9d6 | accuracy | rejected_no_gain | 1.00 | 68,573 | no train gain: acc 1.00 -> 1.00, tokens/task 65,714 -> 68,573 |
| 5 | 5fa5b436 | cost | rejected_no_gain | 1.00 | 62,526 | no train gain: acc 1.00 -> 1.00, tokens/task 65,714 -> 62,526 |
| 5 | 4a9e38a1 | free | rejected_no_gain | 1.00 | 63,773 | no train gain: acc 1.00 -> 1.00, tokens/task 65,714 -> 63,773 |
