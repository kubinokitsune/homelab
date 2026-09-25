# Architecture

How the physical machine is carved up, what runs where, and why.

---

## 1. The hardware

| | |
|---|---|
| **Machine** | Dell OptiPlex 9020M (Micro form factor, ~1L) |
| **CPU** | Intel Core i5-4590T — 4 cores / 4 threads, Haswell, 35W TDP |
| **RAM** | 16 GB DDR3L SODIMM (2×8 GB) — **BIOS-capped at 16 GB** |
| **Storage** | 512 GB Micron C400 SATA SSD |
| **Power** | 65 W external brick — the whole lab idles in the low tens of watts |
| **Expansion** | None. No PCIe slot, so **no GPU is possible.** |

Two constraints follow from that spec sheet, and they shape everything else:

1. **No GPU → no big models.** All inference is CPU-bound, which is why the
   fleet runs a 3-billion-parameter model rather than anything larger, and why
   thread allocation matters so much (see §4).
2. **4 threads total, shared by everything** — 13 agents, an LLM, a vector DB,
   a real-time 3D printer controller and a DNS server. Isolation is not
   optional; it is the only reason a heavy LLM query doesn't cause a print to
   fail.

> **Planned upgrade:** an HP ProDesk 600 G3 SFF (i7-6700, 4C/8T, has PCIe
> slots). It roughly doubles usable threads and unlocks a future GPU. Several
> backlog items — notably Hermes' dynamic core redistribution — are
> deliberately held until that box exists.

---

## 2. Proxmox VE

The bare-metal OS is **Proxmox VE**, at `192.168.1.135`
(web UI: `https://192.168.1.135:8006`).

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
Proxmox host  192.168.1.135
│
├── LXC 100  "homelab"  ·  192.168.1.115   ← the brain
│     ├── 13 agent systemd services (agent-mason, agent-hermes, …)
│     ├── Docker: Ollama        :11434   (LLM inference)
│     ├── Docker: Qdrant        :6333    (vector memory)
│     └── Docker: Syncthing     :8384    (Obsidian vault sync)
│
├── LXC 101  "klipper"  ·  192.168.1.136   ← the hands
│     ├── Klipper      (motion control firmware host)
│     ├── Moonraker    :7125  (HTTP/WebSocket API)
│     ├── Mainsail     :80    (web UI)
│     └── /dev/ttyUSB0 passed through → Ender 3 S1 Pro
│
├── LXC 102  "pihole"   ·  192.168.1.53    ← the filter
│     └── Pi-hole v6 — network-wide DNS ad-blocking
│
├── LXC 103  "chemcalc" ·  192.168.1.54    ← the only public thing
│     ├── gunicorn (non-root) → Chemistry Calculator Flask app
│     └── Tailscale Funnel → https://chemcalc.<tailnet>.ts.net
│
└── (host) ustreamer  :8080  ← USB webcam pointed at the print bed
```

### LXC 100 — `homelab` (the brain)

Everything that thinks. Each agent is its own `systemd` service
(`agent-<name>.service`), so one crashing agent can't take the fleet down, and
`systemctl restart agent-mason` is the whole redeploy story for one agent.

The three Docker services are the shared substrate:

- **Ollama** — local LLM inference. Models: `llama3.2:3b` (chat),
  `nomic-embed-text` (embeddings), `moondream` (vision).
- **Qdrant** — vector database; one collection per agent plus shared vault
  indexes.
- **Syncthing** — keeps the Obsidian vault at `/root/vault` in sync with the
  laptop, continuously and without a cloud service in between.

### LXC 101 — `klipper` (the hands)

Physically isolated from the brain **because 3D printing is soft-real-time.**
Klipper must feed motion commands to the printer's MCU on a steady schedule; if
the host stalls even briefly, the print is ruined. Putting it in its own
container with its own pinned CPU core means no LLM query, however heavy, can
starve it.

The printer connects over USB via a CH341 serial bridge, passed through to the
container. (This chip is the lab's least reliable component — see
[printer.md](printer.md#the-usb-problem).)

### LXC 102 — `pihole` (the filter)

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

### LXC 103 — `chemcalc` (the only public thing)

The [Chemistry Calculator](https://github.com/kubinokitsune/chem-calculator)'s
Flask UI, published to the internet through Tailscale Funnel.

It gets its own container for one reason: **it is the only service here that
strangers can reach.** Everything about it assumes that. The container is
unprivileged and holds nothing but this app; gunicorn runs as a non-root system
user with no shell and no home; `ProtectSystem=strict` means it cannot write
outside `/tmp`; memory is capped at 768 MB. If the app is ever exploited, the
attacker is in an empty box with no route to the agents, the vault or the
printer.

Tailscale runs *inside* this container in **userspace-networking** mode, since an
unprivileged LXC has no `/dev/net/tun`. That is enough to serve a Funnel.

> **Do not overwrite `/etc/default/tailscaled`.** Its unit file references
> `${PORT}` from that file, so dropping the variable makes `tailscaled` fail to
> start with an error that does not mention the cause.

---

## 4. CPU allocation — the most important tuning in the lab

Containers are **CPU-pinned** with `cpuset`, not just weighted. LXC 100 gets 3
cores; LXC 101 gets core 3 to itself.

And then there is the single nastiest bug this lab has produced:

> ### ⚠️ Ollama's `num_thread` **must equal** LXC 100's core count (3).
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

## 5. Network map

| Address | What |
|---|---|
| `192.168.1.135` | Proxmox host — UI on `:8006`, camera stream on `:8080` |
| `192.168.1.115` | LXC 100 — Qdrant `:6333`, Syncthing `:8384`, Ollama `:11434` |
| `192.168.1.136` | LXC 101 — Mainsail `:80`, Moonraker `:7125` |
| `192.168.1.53`  | LXC 102 — Pi-hole `/admin` |
| `192.168.1.54`  | LXC 103 — chem calculator (gunicorn on `:5000`, public via Funnel) |

**Remote access is via [Tailscale](https://tailscale.com)** (WireGuard + NAT
traversal), not a port forward. The router belongs to a family member and can't
be administered, so no inbound port can be opened. Tailscale solves this by
dialling *out* from the server, giving a stable `100.x.x.x` address reachable
from any signed-in device.

The host is also a **subnet router** for `192.168.1.0/24`, so every service above
answers at its usual LAN address from anywhere in the world. The only thing
exposed to the *public* internet is LXC 103, via Funnel — see
[operations.md](operations.md#security) for the full picture.

---

## 6. Design trade-offs, stated plainly

| Decision | Why | What it costs |
|---|---|---|
| LXC over VMs | RAM and CPU overhead near zero | Shared kernel, weaker isolation |
| One systemd service per agent | Independent crash + restart | 13 unit files to maintain |
| 3B model, not 7B+ | The only size that answers in seconds on this CPU | Weaker reasoning; compensated by grounding agents in real data rather than trusting the model |
| Local embeddings | Free, private, fast | Poor discrimination (scores cluster 0.45–0.53) → semantic search alone can't separate domains, so folder allow-lists do it instead ([why](data-and-memory.md#why-folder-scoping-exists)) |
| Printer on its own pinned core | A stalled host ruins a print | One of four cores permanently spoken for |
| Tailscale over port-forwarded WireGuard | No router admin access needed | Depends on a third-party coordination service |

---

**See also:** [operations.md](operations.md) for how this is deployed, backed up
and monitored · [printer.md](printer.md) for the LXC 101 stack in depth.
