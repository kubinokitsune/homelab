# Architecture

How the physical machine is carved up, what runs where, and why.

---

## 1. The hardware

| | |
|---|---|
| **Machine** | Second-hand small-form-factor office PC (~1 L) |
| **CPU** | Low-power desktop CPU — 4 cores / 4 threads |
| **RAM** | 16 GB DDR3L — **BIOS-capped at 16 GB** |
| **Storage** | 512 GB SATA SSD |
| **Power** | 65 W external brick — the whole lab idles in the low tens of watts |
| **Expansion** | None. No PCIe slot, so **no GPU is possible.** |

Two constraints follow from that spec sheet, and they shape everything else:

1. **No GPU → no big models.** All inference is CPU-bound, which is why the
   fleet runs a 3-billion-parameter model rather than anything larger, and why
   thread allocation matters so much (see §4).
2. **4 threads total, shared by everything** — ten running agents, an LLM, a vector DB,
   a real-time 3D printer controller and a DNS server. Isolation is not
   optional; it is the only reason a heavy LLM query doesn't cause a print to
   fail.

> **Planned upgrade:** a bigger small-form-factor desktop with 8 threads and PCIe
> slots. It roughly doubles usable threads and unlocks a future GPU. Several
> backlog items — notably Hermes' dynamic core redistribution — are
> deliberately held until that box exists.

---

## 2. Proxmox VE

The bare-metal OS is **Proxmox VE**.

Everything runs in **LXC containers**, not VMs. That is a deliberate choice:

| | LXC | VM |
|---|---|---|
| RAM overhead | ~0 (shared kernel) | 512 MB – 1 GB each |
| CPU overhead | ~0 | 5–15 % |
| USB passthrough | Simple bind-mount | Needs IOMMU juggling |

On a 16 GB / 4-thread box, three VMs would have eaten a quarter of the RAM
before a single agent started. Containers cost essentially nothing. The
trade-off — a shared kernel, so weaker isolation — is acceptable for a
single-owner home lab.

---

## 3. The containers

```
Proxmox host
│
├── agent container            ← the brain
│     ├── one systemd service per agent (10 deployed)
│     ├── Docker: Ollama       (LLM inference)
│     ├── Docker: Qdrant       (vector memory)
│     └── Docker: Syncthing    (Obsidian vault sync)
│
├── printer container          ← the hands
│     ├── Klipper      (motion control firmware host)
│     ├── Moonraker    (HTTP/WebSocket API)
│     ├── Mainsail     (web UI)
│     └── USB serial passed through → the 3D printer
│
├── DNS container              ← the filter
│     └── Pi-hole v6 — network-wide DNS ad-blocking
│
├── public-app container       ← the only public thing
│     ├── gunicorn (non-root) → Chemistry Calculator Flask app
│     └── Tailscale Funnel → https://chemcalc.<tailnet>.ts.net
│
└── (host) camera stream       ← USB webcam pointed at the print bed
```

### The agent container (the brain)

Everything that thinks. Each agent is its own `systemd` service, so one
crashing agent can't take the fleet down, and restarting a single service is the
whole redeploy story for one agent.

The three Docker services are the shared substrate:

- **Ollama** — local LLM inference. Models: `llama3.2:3b` (chat),
  `nomic-embed-text` (embeddings), `moondream` (vision).
- **Qdrant** — vector database; one collection per agent plus shared vault
  indexes.
- **Syncthing** — keeps the Obsidian vault on the server in sync with the
  laptop, continuously and without a cloud service in between.

### The printer container (the hands)

Physically isolated from the brain **because 3D printing is soft-real-time.**
Klipper must feed motion commands to the printer's MCU on a steady schedule; if
the host stalls even briefly, the print is ruined. Putting it in its own
container with its own pinned CPU core means no LLM query, however heavy, can
starve it.

The printer connects over USB via a CH341 serial bridge, passed through to the
container. (This chip is the lab's least reliable component — see
[printer.md](printer.md#the-usb-problem).)

### The DNS container (the filter)

Network-wide DNS ad-blocking using the StevenBlack blocklist. Because it filters
at the DNS layer, it covers **every device that uses it as a resolver** — phones,
TVs, consoles — with no per-device software. Currently serving one floor of the
house, plus every device on the tailnet from anywhere in the world (see
[operations.md](operations.md#security)).

Two limits worth stating, because they look like faults and are not:

- **In-app ads survive it.** Instagram, YouTube and TikTok serve ads from the
  same domains as their content, so there is no domain to block that would not
  also break the app. DNS filtering kills third-party ad networks, not
  first-party ad serving.
- **iCloud Private Relay bypasses it entirely.** On iPhone/iPad, Safari's DNS
  goes through Apple's relays and never reaches Pi-hole. It has to be turned off
  per-device, in two places: iCloud settings *and* per-Wi-Fi "Limit IP Address
  Tracking".

### The public-app container (the only public thing)

The [Chemistry Calculator](https://github.com/kubinokitsune/chem-calculator)'s
Flask UI (its own **public** repo), published to the internet through Tailscale
Funnel.

It gets its own container for one reason: **it is the only service here that
strangers can reach.** Everything about it assumes that. The container is
unprivileged and holds nothing but this app; gunicorn runs as a non-root system
user with no shell and no home; its service is sandboxed so it can only write
to scratch space, and its memory is capped. If the app is ever exploited, the
attacker is in an empty box with no route to the agents, the vault or the
printer.

Tailscale runs *inside* this container in **userspace-networking** mode, since an
unprivileged LXC has no `/dev/net/tun`. That is enough to serve a Funnel.

> **Don't overwrite Tailscale's defaults file.** The service reads a port
> variable from it, so dropping the variable makes `tailscaled` fail to start
> with an error that does not mention the cause.

---

## 4. CPU allocation — the most important tuning in the lab

Containers are **CPU-pinned** with `cpuset`, not just weighted. The agent container gets 3
cores; the printer container gets the fourth core to itself.

And then there is the single nastiest bug this lab has produced:

> ### ⚠️ Ollama's `num_thread` **must equal** the agent container's core count (3).
>
> Set it higher — say the default 4 — and Ollama spawns more worker threads than
> the container has cores. The Linux CFS bandwidth controller then throttles the
> whole cgroup at the end of every scheduling period, and inference collapses
> from **~9.6 tok/s to ~0.6 tok/s — a ~16× slowdown**, with the fans screaming
> the entire time.
>
> Symptoms: every agent "just slow", the box sounding like a jet engine, and
> nothing in the logs. It looks like a hardware problem. It isn't.
>
> Pinned in `skills/config.py` and in the vision path. **If the container's
> core count ever changes, this value must change with it.**

This coupling is also precisely why Hermes' "redistribute cores on demand"
feature is held back: any dynamic `cpuset` change would have to atomically
retune Ollama, and getting it wrong mid-print crashes the print.

---

## 5. Remote access

(Addresses, ports and container numbers are deliberately not published.)

**Remote access is via [Tailscale](https://tailscale.com)** (WireGuard + NAT
traversal), not a port forward. The router belongs to a family member and can't
be administered, so no inbound port can be opened. Tailscale solves this by
dialling *out* from the server, giving a stable private address reachable
from any signed-in device.

The host is also a **subnet router**, so every private service above is
reachable from my own devices anywhere in the world. The only thing
exposed to the *public* internet is the public-app container, via Funnel — see
[operations.md](operations.md#security) for the full picture.

---

## 6. Design trade-offs, stated plainly

| Decision | Why | What it costs |
|---|---|---|
| LXC over VMs | RAM and CPU overhead near zero | Shared kernel, weaker isolation |
| One systemd service per agent | Independent crash + restart | One unit file per agent to maintain |
| 3B model, not 7B+ | The only size that answers in seconds on this CPU | Weaker reasoning; compensated by grounding agents in real data rather than trusting the model |
| Local embeddings | Free, private, fast | Poor discrimination (scores cluster 0.45–0.53) → semantic search alone can't separate domains, so folder allow-lists do it instead ([why](data-and-memory.md#why-folder-scoping-exists)) |
| Printer on its own pinned core | A stalled host ruins a print | One of four cores permanently spoken for |
| Tailscale over port-forwarded WireGuard | No router admin access needed | Depends on a third-party coordination service |

---

**See also:** [operations.md](operations.md) for how this is deployed, backed up
and monitored · [printer.md](printer.md) for the printer stack in depth.
