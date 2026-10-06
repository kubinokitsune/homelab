# Operations

Running, deploying, backing up and securing the lab.

---

## Service model

Each agent is its own `systemd` unit inside the agent container.

One agent crashing never affects the others, and restarting one is the entire
redeploy story for that agent. The ten deployed agents are enabled at boot (Apex
and Eos aren't deployed yet), and autostart is hardened so the fleet comes back
on its own after a power cut.

---

## Deploying

A deployment script (kept in the private infrastructure repo 🔒)
is run **from the laptop, on the home network**. It:

1. copies changed files to the server and into the agent container
2. installs any new Python dependencies
3. byte-compiles everything with `py_compile` — **catching syntax errors before
   restarting**, rather than discovering them via a dead service
4. restarts the affected agents and checks that each one came back up
5. handles host-level setup (e.g. installing and bringing up Tailscale)

The compile-then-restart ordering is the important part: a typo is caught while
the old version is still running.

---

## Backup

**Every component is its own private GitHub repo** under
[`kubinokitsune`](https://github.com/kubinokitsune) — twelve agents, the skills
library, and an infrastructure repo. A refresh is a commit and push per repo.

- The agent and infrastructure repos are **private**; the skills library is public.
- Secrets live only in git-ignored local config. Tokens are never committed.
- This hub repo links them all; it doesn't vendor them.

---

## Monitoring

| Watcher | Interval | Does |
|---|---|---|
| **Hermes** | ~120 s | Service health, disk, temps, container state; restarts dead services; IsolationForest anomaly detection; self-healing disk cleanup |
| **Warden** | ~300 s | Auth log monitoring; auto-bans brute-forcers; bans persist and are re-applied on reboot |
| **Mason** | per print | Camera + ML print watching; alerts on any premature print end |
| **Iris** | daily | Morning digest compiled from every agent's report |

Alerts go to the phone via Pushover, so a failure at 5:30 a.m. is a
notification, not an eight-hour-later discovery.

### Alert severity

| Severity | Goes to | Meaning |
|---|---|---|
| `INFO` | The agent's Discord channel | Routine |
| `WARNING` | Discord `#warnings` | Worth a look |
| `CRITICAL` | Discord `#critical` + push (priority 1) | Needs attention today; bypasses Do Not Disturb |
| `EMERGENCY` | Discord `#critical` + push (priority 2) | **Repeats every 2 min for 30 min until acknowledged** |

The line between the last two is deliberately narrow: **EMERGENCY is only for
things that get worse while unwatched and that only a person can stop.** An alert
that wakes you for something that could have waited until morning teaches you to
ignore the ones that could not.

Exactly two conditions use it today:

- **Mason** — a print that is *still running* and failing. Not one that already
  stopped: waking up cannot save a print that is already dead.
- **Warden** — an unexpected *successful* login. Not a blocked brute-force
  attempt; the difference is whether someone is already inside.

---

## Security

**Warden's hard whitelist.** `ban()` refuses to ban loopback, the local network,
the Tailscale range, or anything on a configured trusted list. An
automated banning system that can lock its owner out of their own server is
worse than no banning system.

**`!audit`** reports posture: SSH configuration, firewall state, Tailscale
status.

**Remote access is Tailscale, not a port forward.** The router belongs to a
family member and can't be administered, so no inbound port can be opened —
Tailscale dials out and gives a stable private address reachable from any
signed-in device, with nothing exposed to the public internet. Tailscale SSH
also handles SSH auth.

The host runs as a **subnet router**, so the containers are reachable remotely
at their normal local addresses — the printer's web UI works from the couch or
from school. Two requirements that both fail *silently* if missed:

1. **IP forwarding must be on** for the host. Without it the host advertises the
   route but cannot forward into it.
2. **The route must be approved once** in the Tailscale admin console.
   Tailscale ignores an unapproved route.

The deployment script handles (1) and prints a reminder for (2).

**The Homelab Hub is tailnet-only**, published by `tailscale serve` on the host
(Serve, not Funnel) — see [hub.md](hub.md). Because the hub can run real
commands, it also refuses anything that doesn't arrive through the host: with
subnet-route SNAT every tailnet request arrives from the host's own address, so a plain
LAN device gets a 403. Dangerous commands additionally need an explicit confirm,
enforced by each agent's bridge rather than by the UI.

**Pi-hole** (in its own container) filters ads at the DNS layer for every
device that uses it as a resolver — including, via Tailscale's global-nameserver
setting, every device on the tailnet anywhere in the world. That works *because*
subnet-route SNAT makes remote queries appear to come from the host itself, which
already satisfies Pi-hole's `listeningMode = "LOCAL"`; no loosening required.

**One service is public: the public-app container**, the chem calculator, via Tailscale Funnel.
Everything protecting it is in the container rather than in front of it — see
[architecture.md](architecture.md#the-public-app-container-the-only-public-thing). The
app caps request size and field length (every API route hands strings to parsers
whose cost grows with input length) and **rate-limits per visitor** — per-minute and
per-hour caps, keyed on the real client from `X-Forwarded-For`, returning 429
over the limit. The limiter can't ban at the firewall — Funnel traffic never reaches
the host's INPUT chain — so it throttles in the app instead, and the 429s show up
in the traffic report as a flood signal.

**Warden reports the traffic**, not just security: `!traffic [hours]` and a block
in the daily report (so it reaches Iris' digest) — visitor count, status mix,
busiest paths, **which country each visitor came from** (free MaxMind GeoLite2,
optional — no database just means no country labels), and anything off: scanner
probes, 5xx, guard rejections, 429 floods, one IP hammering. The app never calls
inward; Warden reads gunicorn's access log through the host.

Updating it is a pull-and-restart inside its container.

> Two Pi-hole gotchas, both silent: the `pihole` binary isn't on the `PATH` when
> commands are run non-interactively from the host — commands
> appear to succeed while doing nothing. And FTL will happily run without having
> loaded gravity; `pihole reloaddns` fixes a setup that looks correct but blocks
> nothing.

---

## Known issues & backlog

| Item | Status |
|---|---|
| **Printer USB disconnects** | Hardware fault in the CH341 bridge (~30 logged). Needs a **powered USB hub**. Software can only alert. [detail](printer.md#️-the-usb-problem) |
| **Server upgrade** | A bigger small-form-factor desktop with 8 threads and PCIe — doubles usable threads, unlocks a GPU |
| **Hermes dynamic core allocation** | **Deliberately held** until the upgraded server. On 4 cores it's high-risk/low-reward: any `cpuset` change must atomically retune Ollama's `num_thread` ([why](architecture.md#4-cpu-allocation--the-most-important-tuning-in-the-lab)), and getting it wrong mid-print crashes the print |
| **Guest hosting** | Serve a project publicly via Cloudflare Tunnel or Tailscale Funnel — gated on Warden being live |

---

## Documentation upkeep

Three documentation surfaces:

1. **This repo** — the deep explanations.
2. **The GitHub wiki** — generated from `README.md` + `docs/` by
   `scripts/build-wiki.py`, which rewrites the links for wiki page names. Edit the
   docs, never the wiki directly, then rebuild.
3. **The Discord agent wiki** — an in-channel reference of every agent and
   command, posted and edited in place by a script in the
   private infrastructure repo 🔒. It updates
   the existing messages rather than reposting, and handles HTTP 429 rate limits
   with retry-after.

**When an agent gains or loses a command, update all three.**
