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
Generation 0's misses are the context-rot signature: distinct counts and user lists drift as the input grows.

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
