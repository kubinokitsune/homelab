# Operations

Running, deploying, backing up and securing the lab.

---

## Service model

Each agent is a `systemd` unit inside LXC 100:

```bash
systemctl status  agent-mason
systemctl restart agent-mason
journalctl -u agent-mason -f
```

One agent crashing never affects the others, and restarting one is the entire
redeploy story for that agent. All twelve are enabled at boot, and autostart is
hardened so the fleet comes back on its own after a power cut.

---

## Deploying

`deploy-update.sh` (in [homelab-infra](https://github.com/kubinokitsune/homelab-infra))
is run **from the laptop, on the home network**. It:

1. `scp`s changed files to the host, then `pct push`es them into LXC 100
2. installs any new Python dependencies into `/root/agents-venv`
3. byte-compiles everything with `py_compile` — **catching syntax errors before
   restarting**, rather than discovering them via a dead service
4. restarts the affected agents and prints each one's `is-active` state
5. handles host-level setup (e.g. installing and bringing up Tailscale)

```bash
bash ~/OneDrive/Desktop/AI_Agents/deploy-update.sh
```

The compile-then-restart ordering is the important part: a typo is caught while
the old version is still running.

---

## Backup

**Every component is its own private GitHub repo** under
[`kubinokitsune`](https://github.com/kubinokitsune) — twelve agents, the skills
library, and the infra repo. A refresh is a commit and push per repo.

- All repos are **private**.
- Secrets live only in a **gitignored `.env`**. Tokens are never committed.
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

---

## Security

**Warden's hard whitelist.** `ban()` refuses to ban loopback, the LAN, the
Tailscale range `100.64.0.0/10`, or anything listed in `WARDEN_TRUSTED_IPS`. An
automated banning system that can lock its owner out of their own server is
worse than no banning system.

**`!audit`** reports posture: SSH configuration, firewall state, Tailscale
status.

**Remote access is Tailscale, not a port forward.** The router belongs to a
family member and can't be administered, so no inbound port can be opened —
Tailscale dials out and gives a stable `100.x` address reachable from any
signed-in device, with nothing exposed to the public internet. `tailscale up
--ssh` also handles SSH auth.

**Pi-hole** (LXC 102, `192.168.1.53`) filters ads at the DNS layer for every
device that uses it as a resolver.

> Two Pi-hole gotchas, both silent: the `pihole` binary lives in
> `/usr/local/bin`, which is **not on `PATH` under `pct exec`** — commands
> appear to succeed while doing nothing. And FTL will happily run without having
> loaded gravity; `pihole reloaddns` fixes a setup that looks correct but blocks
> nothing.

---

## Known issues & backlog

| Item | Status |
|---|---|
| **Printer USB disconnects** | Hardware fault in the CH341 bridge (~30 logged). Needs a **powered USB hub**. Software can only alert. [detail](printer.md#️-the-usb-problem) |
| **Server upgrade** | HP ProDesk 600 G3 SFF (i7-6700, 4C/8T, PCIe) — doubles usable threads, unlocks a GPU |
| **Hermes dynamic core allocation** | **Deliberately held** until the i7 box. On 4 cores it's high-risk/low-reward: any `cpuset` change must atomically retune Ollama's `num_thread` ([why](architecture.md#4-cpu-allocation--the-most-important-tuning-in-the-lab)), and getting it wrong mid-print crashes the print |
| **Guest hosting** | Serve a project publicly via Cloudflare Tunnel or Tailscale Funnel — gated on Warden being live |
| **Root password** | Known-weak, set during bring-up. **Must be rotated before anything is exposed publicly.** |

---

## Documentation upkeep

Two documentation surfaces, kept in sync by hand:

1. **This repo** — the deep explanations.
2. **The Discord agent wiki** — an in-channel reference of every agent and
   command, posted and edited in place by `post_wiki.py` in
   [homelab-infra](https://github.com/kubinokitsune/homelab-infra). It updates
   the existing messages rather than reposting, and handles HTTP 429 rate limits
   with retry-after.

**When an agent gains or loses a command, update both.**
