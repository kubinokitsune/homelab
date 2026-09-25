# The skills library

**Repo:** `homelab-agent-skills` 🔒

This is the heart of the project. Every agent is the same base class plus an
identity and a handful of domain commands — which means a capability added here
lands in all twelve agents at once.

```
ai_agent_skills_liberies/skills/
├── discord_agent.py     ← the base class everything is built on
├── llm.py  config.py  result.py  logging.py  errors.py  notifications.py
├── obsidian_vault.py  vault_index.py  vault_librarian.py  vault_tagger.py
├── vector_store.py  source_ingest.py  web_search.py  news.py  file_ops.py
├── agent_mail.py  agent_reports.py  scheduling.py  calendar.py
├── moonraker.py  camera.py  vision.py  print_recorder.py  print_tuning.py
├── failure_detector.py  anomaly_detector.py  server_monitor.py  security_monitor.py
├── build_tracker.py  parts_list.py  error_log.py  calc.py
├── flashcards.py  audio_transcribe.py
└── __init__.py
```

---

## `DiscordAgent` — the base class

Give it a name and a personality; it gives you a running agent.

```python
from skills.discord_agent import DiscordAgent

mason = DiscordAgent(
    name="Mason",
    persona="A 3D-printing specialist. Direct, practical, no filler.",
    rag_include_folders=["Engineering Studies/", "Agent Notes/"],
)

@mason.command("temp")
async def temp(ctx, args):
    return f"Nozzle {printer.nozzle}°C / Bed {printer.bed}°C"

mason.run()
```

Out of the box that agent already has Discord plumbing, LLM chat, vector memory,
vault read/write, inter-agent mail, `!help`, `!note`, `!learn`, `!recall`,
`!tell`, command chaining and the grounding rules below.

---

## The six hooks

| Hook | Fires when | Used for |
|---|---|---|
| `@agent.command("name")` | `!name …` is typed | Normal commands |
| `@agent.on_startup` | The agent boots | Restoring state, starting watchdogs |
| `@agent.on_plain_message` | A message with no command | Natural-language handling (e.g. Kairos' scheduling) |
| `@agent.on_attachment` | A file is posted | Codex ingesting documents and audio |
| `@agent.on_mail` | Another agent sends mail | Cross-agent workflows, digest reports |
| **`@agent.on_context`** | **Before every LLM reply** | **Injecting live truth into the prompt** |

### `on_context` is the important one

This is the hook that fixed the project's worst failure mode. Before the model
answers *anything*, `on_context` runs and injects current reality into the
prompt — so the agent isn't reasoning from stale training data or vibes.

```python
@mason.on_context
async def live_printer_context():
    s = await moonraker.status()
    return (f"LIVE PRINTER STATE (authoritative, right now):\n"
            f"  state: {s.state}   file: {s.filename}\n"
            f"  nozzle: {s.nozzle}°C   bed: {s.bed}°C   progress: {s.progress}%")
```

Ask Mason "how's the print going?" and it answers from *that*, not from
imagination. Hermes injects live server metrics the same way.

---

## The grounding rules

Every LLM call goes through `ask()`, which prepends non-negotiable constraints.
These exist because of a specific, memorable failure: agents confidently citing
vault notes that did not exist, quoting printer temperatures they had never
read, and inventing commands they didn't have.

**1. Honesty rules.** The agent may not invent notes, files, or live readings,
and may not claim to have done something it hasn't. Absent data, the correct
answer is "I don't know" or "I can't read that right now."

**2. Real command list injection.** The agent is told, every single call,
exactly which commands exist:

```python
cmds = ["help", "note", "learn", "recall", "tell"] + sorted(self._commands)
system += ("\n\n## Your ONLY real commands\n"
    "Exactly these exist: " + "  ".join(f"`!{c}`" for c in cmds) + "\n"
    "NEVER invent a command or make up its name/syntax...")
```

The list is generated from the actual command registry, so it cannot drift out
of date. Mason once told its owner to run a command that had never existed;
after this, it can't.

**3. Retrieval scoping.** RAG results are filtered by folder before they reach
the prompt — see [data-and-memory.md](data-and-memory.md#why-folder-scoping-exists).

**4. Deterministic over generative.** Where a real answer can be computed or
looked up, it is — `!find` reads the filesystem, `!calc` evaluates the
expression, `!spec` returns datasheet links. The LLM is for phrasing and
reasoning, not for facts it would have to make up.

---

## Quality-of-life parsing

**Trailing note capture.** Writing a note shouldn't require remembering the
command first. Write the thought, end with `!newnote`, done:

```
PETG warps badly under 60°C bed. Bump to 80 and it sticks. !newnote
```

Matched by `r"^(.*\S)\s*!(?:newnote|savenote)\s*$"` and saved to the vault.

**Command chaining.** Multiple commands in one message are split on
`r"!([A-Za-z][\w-]*)([^!]*)"` and executed in order, so `!status !temp !job`
works as one message.

---

## Skills by area

| Area | Modules |
|---|---|
| **Core** | `discord_agent` · `llm` · `config` · `result` · `logging` · `errors` · `notifications` |
| **Vault & knowledge** | `obsidian_vault` · `vault_index` · `vault_librarian` · `vault_tagger` · `vector_store` · `source_ingest` · `file_ops` |
| **External info** | `web_search` · `news` · `audio_transcribe` |
| **Coordination** | `agent_mail` · `agent_reports` · `scheduling` · `calendar` |
| **Printer** | `moonraker` · `camera` · `vision` · `print_recorder` · `print_tuning` |
| **Machine learning** | `failure_detector` · `anomaly_detector` · `vault_tagger` · `flashcards` (SM-2) |
| **Monitoring** | `server_monitor` · `security_monitor` |
| **Project tooling** | `build_tracker` · `parts_list` · `error_log` · `calc` |

---

## Building a new agent

1. Create a repo and a `bot/<name>.py`.
2. Instantiate `DiscordAgent` with a name, persona, and any folder scoping.
3. Register domain commands with `@agent.command(...)`.
4. Add `@agent.on_context` if the agent controls anything real — if it can
   observe live state, it must, or it will guess.
5. Add a `systemd` unit `agent-<name>.service` in LXC 100.
6. Add the agent to the Discord wiki via `post_wiki.py`.

Steps 1–4 are typically under 200 lines. Everything else is already done.
