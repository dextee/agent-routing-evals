# Agent routing evaluations

Does a second model improve a billing decision enough to justify another call? This repository ships the inputs, answer key, exact policy, model outputs and a Python grader for one small, reproducible experiment. Everything needed to replay it is in Git.

## Try it locally

With Git and Python 3.10 or newer:

```sh
git clone https://github.com/dextee/agent-routing-evals.git
cd agent-routing-evals
python evaluate.py
python -m unittest -v
```

Use `python evaluate.py --json` for per-ticket outcomes, token counts, failed attempts and timing. Replaying results is offline and uses only the Python standard library.

## What happened on 20 November 2026 (Singapore)

A single GPT-6 Luna request processed 20 synthetic, held-out billing disputes. The escalation strategy reused those answers and asked GPT-6.2 Sol to reconsider the 17 tickets with missing references or a ledger row count other than one. Both requested models used medium effort. The policy, routing rule and expected outputs were [committed before the run](https://github.com/dextee/agent-routing-evals/tree/ed745a4). The two repeated trials used the same cases.

| Repeat | Strategy | Accepted | Missed human reviews | Incorrect claims | Wall time |
|---|---|---:|---:|---:|---:|
| 1 | Fixed | 20/20 | 0 | 0 | 18.3 s |
| 1 | Escalation | 20/20 | 0 | 0 | 37.3 s |
| 2 | Fixed | 20/20 | 0 | 0 | 17.3 s |
| 2 | Escalation | 20/20 | 0 | 0 | 36.0 s |

**Use the simpler route on this fixture.** The second read changed no acceptance decision. Both models reached the ceiling on these constrained cases. The result leaves open what would happen with more difficult records, free-form summaries, realistic traffic or a different review policy. Twenty cases repeated twice are still twenty distinct cases.

Wall time includes starting the CLI and waiting for a complete batch. Escalation times include the first stage. Four live requests completed, with zero failed attempts or retries. The CLI used a ChatGPT login and reported token counts. Actual USD per accepted task is unknown. The run records name the models requested at the CLI and contain the returned answer fields. Only final agent-message items appeared in the CLI event stream. [Raw results](results/pilot-2026-11-20) · [Protocol](PROTOCOL.md)

## Inspect a decision

In case H09 the export contains the same captured debit twice. Both ledger rows share an event ID. A grounded answer cites both source rows and explains one capture. Case H10 also repeats an event ID, but its statuses conflict. That case requires investigation. Changing a correct answer to another valid claim code can leave the route unchanged while still failing the grader. [Twenty held-out inputs](data/heldout.json) · [Expected decisions](expected/heldout.json) · [Scoring tests](test_evaluate.py)

## Collect a fresh run

The bundled pilot used Codex CLI 0.170.0. To make fresh requests, use an existing login with access to the requested models and a compatible CLI. A new run consumes that account's model allowance or provider billing.

```sh
python collect.py scratch/new-run
python evaluate.py --runs scratch/new-run --json
```

The collector passes only the policy and selected cases to each model from a temporary directory. Keep a fresh output directory for every experiment. To develop a new policy, start with the six development cases, then freeze fresh held-out cases before making performance claims. Grounded claims here use a closed vocabulary. Free-form summaries need a separate factual review. [Policy](policy.txt) · [Development cases](data/dev.json) · [ChatGPT guide evaluation worksheet](https://github.com/dextee/chatgpt-agent-team-guide/blob/main/docs/cost-and-evaluation.md)
