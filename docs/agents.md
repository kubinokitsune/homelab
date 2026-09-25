# The agents

Twelve Discord agents, each a distinct personality with its own channel, its own
memory collection, and its own domain. **Ten are currently deployed** — Apex and
Eos are written but have no service on the server yet, and are marked below.

All of them are built on the same
[`DiscordAgent` base](skills-library.md), so every one of them also inherits:

| Universal command | Does |
|---|---|
| `!help` | Lists that agent's real commands |
| `!note <text>` | Writes a note into the vault under `Agent Notes/<Agent>/` |
| `!learn <fact>` | Stores a fact in long-term vector memory **and** leaves a visible vault note |
| `!recall <query>` | Searches that agent's memory |
| `!tell <agent> <msg>` | Sends inter-agent mail |

You can also just talk to them — plain messages get an LLM reply grounded in
live data and vault context. Two conveniences on top:

- **Trailing note capture** — write the note first, end the message with
  `!newnote`, and it gets saved. No need to remember the command up front.
- **Command chaining** — several commands in one message are split and run in
  order.

---

## 🔧 Forge — engineering mentor
**Repo:** [engineering-ai-agent](https://github.com/kubinokitsune/engineering-ai-agent)

The most built-out agent after Mason. Forge is a project partner: it does the
maths, keeps the shopping list, tracks build progress, and remembers what broke
last time.

| Command | Does |
|---|---|
| `!calc <expr>` | Engineering calculator — evaluates real expressions, not an LLM guess |
| `!spec <part>` | Returns **real datasheet links** for a component |
| `!parts` / `!order <item>` / `!ordered <item>` | Parts & shopping list with order state |
| `!build <name>` / `!steps` / `!step <n>` / `!done` | Build checklists with step tracking |
| `!stuck <problem>` / `!resolved <fix>` / `!errors` / `!patterns` | Error log — and ML clustering over it to surface recurring failure patterns |
| `!search <q>` / `!reindex` | Search the engineering side of the vault |
| `!review` / `!report` | Project review and status |

> `!spec` used to synthesise specs with the LLM. It timed out at 90 s — twice —
> and risked inventing numbers. It now returns real datasheet links in ~1.3 s.
> That trade (a link you can verify over a paragraph you can't) is the whole
> design philosophy in one command.

---

## 🧱 Mason — 3D printing
**Repo:** [printer-ai-agent](https://github.com/kubinokitsune/printer-ai-agent) · **Deep dive:** [printer.md](printer.md)

By far the largest agent — full control of the printer, a camera, and two
machine-learning models. It talks to Klipper through the Moonraker API.

**Printer state & motion**
`!status` · `!temp` · `!home` · `!zoffset` · `!babystep` · `!savez`

**Job control**
`!files` · `!print <file>` · `!pause` · `!resume` · `!cancel` · `!cooldown` · `!estop` · `!job`

**Live tuning** (mid-print, bounds-checked)
`!settings` · `!speed <%>` · `!flow <%>` · `!fan <%>` · `!pa <value>`

**Print critic** — the camera + LLM analyse the print and propose concrete parameter changes, which you approve before they're applied
`!assess` · `!apply` · `!tuning` · `!applied`

**Camera & vision**
`!snap` · `!look` · `!cammode` · `!autocam` · `!day` · `!lowlight` · `!dim` · `!night`

**Machine learning**
`!train` · `!label` · `!dataset` · `!report`

Mason also runs without being asked: it watches prints, detects failures, and
messages you when something is wrong.

---

## 🖥️ Hermes — server caretaker
**Repo:** [maintenance-ai-agent](https://github.com/kubinokitsune/maintenance-ai-agent)

Watches the machine that everything else depends on. A ~120 s watchdog checks
services, restarts what's dead, and learns what "normal" looks like.

| Command | Does |
|---|---|
| `!health` / `!report` | Overall system health |
| `!services` / `!restart <svc>` | Service state and recovery |
| `!temps` / `!disk` / `!uptime` / `!specs` / `!containers` | Hardware and container telemetry |
| `!baseline` / `!trends` / `!anomaly` | IsolationForest anomaly detection over server metrics — flags "this is unusual" without being told the thresholds |
| `!cleanup` | Self-healing disk cleanup |
| `!learn` / `!knowledge` / `!log` | Operational knowledge base and incident log |

---

## 🛡️ Warden — security
**Repo:** [security-ai-agent](https://github.com/kubinokitsune/security-ai-agent)

Watches authentication and network posture. A ~300 s watchdog auto-bans
brute-forcers, and bans persist across reboots.

| Command | Does |
|---|---|
| `!threats` / `!report` | Current threat picture |
| `!logins` / `!sessions` | Auth attempts and live sessions |
| `!ports` | Listening ports |
| `!ban <ip>` / `!bans` / `!unban <ip>` | Ban management |
| `!audit` | Posture audit — SSH config, firewall, Tailscale |

> **Hard whitelist.** `ban()` *refuses* to ban loopback, the LAN, the Tailscale
> range `100.64.0.0/10`, or anything in `WARDEN_TRUSTED_IPS` — so the agent
> defending the server can never lock its owner out of it.

---

## 🗂️ Axiom — vault librarian
**Repo:** [librarian-ai-agent](https://github.com/kubinokitsune/librarian-ai-agent)

Curates the Obsidian vault: finds things, spots rot, and organises.

| Command | Does |
|---|---|
| `!find <q>` | **Deterministic** file lookup — real paths, never an invented title |
| `!health` / `!duplicates` / `!orphans` / `!misfiled` | Vault hygiene reports |
| `!organize` / `!refile` | Restructure notes into the right folders |
| `!tag` / `!topics` | Nearest-centroid auto-tagging and topic clustering |
| `!reindex` | Rebuild the vector index |
| `!nightly` | The full nightly librarian pass |

> **Two hard rules.** The nightly pass **never hard-deletes** — it archives, and
> merges losslessly. And school/IB coursework is never merged into personal
> project notes.

---

## 📚 Codex — sources (a local NotebookLM)
**Repo:** [codex-ai-agent](https://github.com/kubinokitsune/codex-ai-agent)

Ingest a pile of material, then ask questions answered **from those sources
only**, with citations.

| Command | Does |
|---|---|
| `!ask <q>` | Answer from the ingested sources, cited |
| `!explain <topic>` | Explain a concept using the sources |
| `!studyguide` | Generate a study guide |
| `!sources` | List what's been ingested |

Drop a file, link, or **audio file** in its channel and it ingests
automatically. Audio is transcribed locally with faster-whisper (CTranslate2,
CPU int8) — so lecture recordings and voice memos become searchable sources.

---

## 🎓 Chiron — tutor
**Repo:** [tutor-ai-agent](https://github.com/kubinokitsune/tutor-ai-agent)

Active recall with a real spaced-repetition scheduler.

| Command | Does |
|---|---|
| `!explain <topic>` / `!quiz <topic>` | Teach and test |
| `!card <front> / <back>` / `!gencards` | Create flashcards, by hand or generated |
| `!review` / `!flip` | Run a review session |
| `!again` `!hard` `!good` `!easy` | Grade a card — drives the **SM-2** algorithm, which sets the next interval |
| `!cards` / `!studied` / `!streak` | Deck stats and study streak |

---

## 📅 Kairos — scheduler
**Repo:** [scheduler-ai-agent](https://github.com/kubinokitsune/scheduler-ai-agent)

Plans the day around fixed anchors (school, training) and how recovered you are.

| Command | Does |
|---|---|
| `!today` / `!tomorrow` | The day's plan |
| `!mode` | Switch planning mode |
| `!readiness` | Pull readiness in from Eos to shape the plan |
| `!event` / `!unevent` / `!calendar` | Calendar management |

**Plain-English scheduling:** you don't need `!event`. Say *"physics test next
Tuesday"*, *"move the dentist to Friday"* or *"cancel golf"* and Kairos parses
the intent and date, then adds, moves or cancels the event.

---

## ☀️ Iris — the morning digest
**Repo:** [digest-ai-agent](https://github.com/kubinokitsune/digest-ai-agent)

The front page. Iris collects every other agent's report, the calendar, and the
news into one briefing — deliberately terse, no filler.

| Command | Does |
|---|---|
| `!digest` | Produce the briefing now |
| `!news` | Just the news section |

News comes from **real RSS feeds** — NYT World, BBC World, La Nación (CR), The
Tico Times, El País — and every item is date-checked, with anything older than
**366 days** dropped. (CNN's feed was excluded after it was found serving 2023
articles as current.)

Iris also reports **overnight progress on multi-day prints**, so a 2-day job
shows up in the morning with how far it got.

---

## 📋 Scout — recruiting
**Repo:** [recruitment-ai-agent](https://github.com/kubinokitsune/recruitment-ai-agent)

Runs the lacrosse recruiting pipeline.

| Command | Does |
|---|---|
| `!pipeline` | Pipeline state across schools |
| `!fit <school>` | Assess fit |
| `!draft` | Draft outreach to a coach |
| `!followups` | Who's owed a reply |

---

## 🏋️ Apex — gym
**Repo:** [gym-ai-agent](https://github.com/kubinokitsune/gym-ai-agent)

`!plan` — training plan · `!progress` — progress over time.

> ⚠️ **Not deployed.** No `agent-apex.service` exists on the server yet; the code
> is written but has never run.

## 🌙 Eos — recovery
**Repo:** [recovery-ai-agent](https://github.com/kubinokitsune/recovery-ai-agent)

`!readiness` — daily readiness score, which Kairos reads when planning and Iris
reports in the digest.

> ⚠️ **Not deployed.** No `agent-eos.service` exists on the server yet; the code
> is written but has never run. Note this means Kairos' `!readiness` and Iris'
> digest currently have no Eos to pull from.

---

## Not part of the fleet: 🎒 AI-School-Agent

[AI-School-Agent](https://github.com/kubinokitsune/AI-School-Agent) is a
standalone **Node.js** tool that predates the Discord fleet. It opens Google
Classroom in Chrome, reads an assignment, researches it with Playwright, reads
local files and Google Docs, and writes a structured IB assignment brief into
the Obsidian vault (with an assignment registry and English/Spanish
auto-detection).

It shares the vault but none of the Python skills library, and it is run by hand
rather than living in Discord.

---

## How they talk to each other

Agents aren't isolated. `!tell <agent> <message>` sends **inter-agent mail**,
delivered through the `on_mail` hook. This is how Iris assembles the digest
(every agent files a report), how Kairos gets readiness from Eos, and how Mason
can escalate a print failure.
