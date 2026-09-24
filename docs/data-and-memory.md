# Data & memory

Where the agents' knowledge actually lives, and the rules that keep them honest
about it.

---

## The three memory layers

| Layer | Store | Holds | Survives |
|---|---|---|---|
| **Conversation** | in-process | The current exchange | No |
| **Long-term memory** | Qdrant | Facts, notes, past context, per agent | Yes |
| **The vault** | Obsidian markdown files | Everything human-readable | Yes — and I can read it myself |

The third layer is the point. Agent memory that only exists inside a vector
database is memory I can't inspect, correct, or take with me. Everything of
consequence ends up as a markdown file in a real Obsidian vault.

---

## The Obsidian vault

Lives at `/root/vault` in LXC 100, kept in sync with the laptop by **Syncthing**
(continuous, peer-to-peer, no cloud service in the middle).

Agents both **read** it (as retrieval context) and **write** to it:

```
vault/
├── Agent Notes/
│   ├── Mason/          ← !note and !learn from Mason land here
│   ├── Forge/
│   └── …
├── Engineering Studies/
├── School/
├── 02_Topics/
└── …
```

Each agent's notes folder is `Agent Notes/<Name>/`, written by
`_write_vault_note()`. Crucially, `!learn` writes a **visible vault note** as
well as storing the vector — so "the agent learned something" is verifiable by
opening a file, not by trusting a claim.

---

## Qdrant — vector memory

Runs in Docker in LXC 100 (`:6333`, dashboard at
`http://192.168.1.115:6333/dashboard`). Collections are per-agent
(`<agent>_memory`) plus shared indexes over the vault and ingested sources.

Retrieval is standard RAG: embed the query, pull the nearest chunks, prepend
them to the prompt.

---

## Ollama — local inference

| Model | Role |
|---|---|
| `llama3.2:3b` | Conversation and reasoning |
| `nomic-embed-text` | Embeddings for all retrieval |
| `moondream` | Vision — Mason looks at the print bed |

All CPU-only. See [the `num_thread` warning](architecture.md#4-cpu-allocation--the-most-important-tuning-in-the-lab) — it is the difference between 9.6 and 0.6 tokens/sec.

---

## Why folder scoping exists

This is the most interesting technical lesson in the project.

Mason — the 3D-printing agent — once answered a printing question by citing *La
noche de 12 años*, a film from a Spanish class. The note was genuinely in the
vault; the retriever genuinely ranked it highly.

The investigation found the real problem: **the local embedding model barely
discriminates.** Across a wide range of semantically unrelated queries and
documents, similarity scores clustered in a narrow band around **0.45–0.53**.
There was no threshold that separated "relevant printing note" from "unrelated
Spanish-class note", because numerically they looked the same. A better
threshold was never going to work.

So retrieval is constrained **structurally** instead of semantically:

```python
rag_include_folders = ["Engineering Studies/", "Agent Notes/"]   # allow-list
rag_exclude_folders = ["School/"]                                # deny-list
```

with `_note_allowed()` filtering results, and an over-fetch
(`fetch = max(self.context_k * 4, 16)`) so that enough candidates survive
filtering to still fill the context.

**Allow-lists beat deny-lists.** The first fix was a deny-list on `School/` —
and it failed, because the offending note lived in `02_Topics/`. Enumerating
everything an agent *shouldn't* see is unbounded; enumerating what it *should*
see is small and correct. Mason now uses an allow-list.

> The general lesson: when your embeddings are too weak to separate domains,
> don't tune the threshold — impose the structure you already know.

---

## The honesty rules

The rules that turned the fleet from "convincing" into "trustworthy". They were
written after a blunt and entirely fair piece of feedback: the agents looked
impressive and were, much of the time, confidently making things up.

Three concrete failures triggered this:

1. **Mason didn't know the printer's actual temperatures** — it answered from
   plausibility, not from the machine.
2. **Notes never reached Obsidian** — agents said "saved!" and nothing was
   written.
3. **Axiom returned invented note titles** — searching the vault for them found
   nothing, because they had never existed.

The fix was layered, because no single one of these is a prompt problem:

| Layer | Fix |
|---|---|
| **Prompt** | Honesty rules in `ask()`: never invent notes, files or live readings; never claim an action you didn't take; say "I don't know" |
| **Prompt** | The real command list, generated from the registry, injected on every call |
| **Retrieval** | Folder scoping, so context is at least on-topic |
| **Architecture** | `on_context` — inject live, authoritative state before the model speaks |
| **Architecture** | Deterministic handlers where an answer can be *looked up* rather than generated (`!find`, `!calc`, `!spec`) |

The ordering matters: the prompt layers reduce fabrication, but only the
architectural ones *eliminate* it. A model told "don't invent temperatures" will
still invent temperatures if it has none; a model handed the real temperatures
has nothing to invent.

---

## Machine learning in the lab

None of this is deep learning — it's small classical models trained on data the
lab generates about itself.

| Model | Where | What it does |
|---|---|---|
| **RandomForest** | `failure_detector.py` | Supervised print-failure classification from labelled prints |
| **IsolationForest** | `failure_detector.py` | Unsupervised anomaly detection — learns what a *clean* print looks like and flags deviation |
| **IsolationForest** | `anomaly_detector.py` | Same idea for server metrics — Hermes flags unusual behaviour without hard thresholds |
| **Nearest-centroid** | `vault_tagger.py` | Auto-tags vault notes by embedding-space proximity to established topics |
| **SM-2** | `flashcards.py` | Spaced-repetition scheduling for Chiron |
| **Clustering** | `error_log.py` | Groups Forge's logged errors to surface recurring failure patterns |

Print scoring is reported as a **quality percentage** rather than a raw
IsolationForest score, because `-0.12` means nothing to a human standing in
front of a printer at 2 a.m. and "38 %" does.
