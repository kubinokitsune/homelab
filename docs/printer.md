# The printer stack

**Hardware:** Creality Ender 3 S1 Pro, reflashed with **Klipper**
**Host:** LXC 101 · `192.168.1.136` · pinned to its own CPU core
**Agent:** [Mason](agents.md#-mason--3d-printing) ([printer-ai-agent](https://github.com/kubinokitsune/printer-ai-agent))

---

## The stack

```
Ender 3 S1 Pro (STM32 MCU, Klipper firmware)
        │  USB — CH341 serial bridge → /dev/ttyUSB0
        ▼
LXC 101 ── Klipper      motion planning on the host, dumb-fast MCU
        ├─ Moonraker    :7125   HTTP + WebSocket API
        └─ Mainsail     :80     web UI  →  http://192.168.1.136
                │
                ▼  Moonraker API
             Mason (in LXC 100)
                │
                ├── camera  →  ustreamer :8080  →  moondream vision
                └── ML      →  RandomForest + IsolationForest
```

Klipper does the motion planning on the Linux host and streams precisely timed
steps to the printer's MCU — which is why the host's timing matters and why LXC
101 gets a core to itself.

### Flashing notes (hard-won)

- The S1 Pro needs a `STM32F4_UPDATE` folder present on the SD card for the
  bootloader to accept the firmware — without it the flash silently does
  nothing.
- A failing SD card produced the same symptom as a bad firmware build. Rule out
  the card first.
- LXC USB passthrough needs both tty permissions and a udev hotplug rule, or the
  device vanishes from the container on reconnect.

---

## ⚠️ The USB problem

The single worst piece of hardware in the lab is the **CH341 USB-serial bridge**.

A print failed at 5:30 a.m. The kernel log showed:

```
usb 2-10: USB disconnect, device number 7
```

…and the device came back as **`/dev/ttyUSB1`**. Klipper was configured for
`ttyUSB0`, so it could not reconnect, and the print was dead. Roughly **30
disconnects** have now been logged.

**This is a hardware fault and no software can fix it.** The CH341 is a
low-quality bridge with marginal power delivery. The real fix is a **powered USB
hub** (or replacing the bridge).

What software *can* do, and now does: Mason alerts on **any** premature print
end, so a 5:30 a.m. failure is a phone notification rather than a discovery
eight hours later.

---

## Mason's control surface

Everything Mainsail exposes, Mason can drive through Moonraker — plus things
Mainsail doesn't expose conveniently.

**Motion & calibration:** `!home` `!zoffset` `!babystep` `!savez`
**Jobs:** `!files` `!print` `!pause` `!resume` `!cancel` `!cooldown` `!estop` `!job`
**Live tuning:** `!speed` `!flow` `!fan` `!pa`

`moonraker.py` also pulls file metadata (object height, filament weight,
embedded thumbnails) so Mason knows what a print *should* look like, and queries
the `fan` object so fan state is observable.

> **About the hotend fan:** `[heater_fan hotend_fan]` is **thermostatic by
> design** — Klipper drives it from hotend temperature and it is deliberately
> not user-controllable. That is correct behaviour, not a missing feature:
> manually stopping it while the hotend is hot risks a heat creep jam. The part
> cooling fan (`!fan`) is the one meant to be tuned.

---

## Vision

A USB webcam on the printer, streamed by **ustreamer** on `:8080`, read by the
**moondream** vision model.

### Adaptive exposure

The camera has day / lowlight / night modes, and auto-selection originally did
not work at all — every mode reported brightness inside the same 55–190 band, so
nothing ever triggered a switch.

The fix was to stop comparing raw readings and **normalise to true ambient
light** by dividing out each mode's own gain:

```python
_MODE_FACTOR  = {"day": 1.0, "lowlight": 2.7, "night": 7.1}
_TARGET       = 110.0
_SWITCH_MARGIN = 18        # hysteresis — stops mode oscillation

ambient = reading / _MODE_FACTOR[cur]
```

Now a night-mode reading of 150 is correctly understood as *dark* (≈21 ambient),
and the mode switches. The margin prevents flapping at the boundary.

Related: the laptop can act as a work light overnight — which required a 40 s
heartbeat calling `SetThreadExecutionState`, a `mouse_event` pulse and a
brightness re-max, because a single call is not enough to stop Windows dimming
the panel.

---

## Failure detection

Two models, because they answer different questions.

| Model | Question | Needs |
|---|---|---|
| **RandomForest** | "Does this look like a known failure?" | Labelled prints (`!label`) |
| **IsolationForest** | "Is this unlike any clean print I've seen?" | Only clean prints |

The second is the more useful one early on: it catches novel failures and needs
no failure examples, only a baseline of good prints. `!train` builds the models,
`!dataset` shows what data exists, and `anomaly_readiness()` reports whether
there's enough for training to be meaningful.

Tuning that mattered:

```python
_FAILURE_BELOW = -0.12     # was -0.08 — too twitchy, false alarms
```

and raw scores are mapped to a **quality percentage** (`_score_to_pct()`:
failure ≈ 30 %, clean ≈ 70 %) because that's the number a human can act on.

### The swipe labeler

The models are only as good as their labels, and labelling a whole print
good-or-bad is crude — a print can be clean for three hours and fail in the
fourth. So frames are labelled **individually**, through a little mobile web app
(`printer-ai-agent/label_ui/`): it shows one unlabelled frame at a time as a
card, you **swipe right for good, left for bad**, and the label lands in that
print's `frame_labels.json`. The failure detector prefers a frame's own label
over the whole-print one, falling back to the print label when a frame hasn't
been swiped.

It runs in LXC 100 and is reached from the phone **over Tailscale at
`http://192.168.1.115:5005`** — deliberately *not* public, since these are
photos of the print bed. Path-traversal-guarded, and every label is a single
`POST`.

### Per-print reports in the vault

When a print ends, Mason writes a note to `Print Reports/<date>_<file>.md` —
outcome, duration, filament, and a strip of the print's frames embedded in the
note itself — so each print has a durable record in Obsidian, photos included,
linking to the labeler. Iris does the same for the nightly digest, one dated
note per night under `Homelab Digests/`.

---

## The print critic

`!assess` takes a camera frame plus live print state and asks the LLM for an
opinion and concrete parameter changes. It writes them in a structured
`ACTIONS:` block, which is parsed and — only after you `!apply` — sent to the
printer. `!tuning` shows what's pending, `!applied` what's been done.
`print_tuning.py` keeps the ledger.

Two guards, both added because the model misbehaved in exactly these ways:

1. **The parser scans the whole response**, not just the end — the model
   reliably put its `ACTIONS:` block in the wrong place.
2. **`_ACTION_BOUNDS` drops out-of-range values.** The model once proposed
   `pa=5` — a pressure-advance value roughly 100× sane, which would have wrecked
   the print. Values outside physical bounds are discarded before they can ever
   reach the printer.

This is the general pattern for letting an LLM touch hardware: **propose freely,
validate strictly, apply only on human approval.**

---

## Print session recording

`print_recorder.py` tracks sessions — start, progress samples, camera frames,
outcome — which is what the ML trains on.

An early bug created a **duplicate session on every agent restart**; during one
development day ~15 restarts produced 5 phantom "prints". Fixed with
`open_session_for()` (reuse the session already open for this file) and
`dedupe_open()` (collapse duplicates), which took that day's count from 5 to the
correct 2. It also survives a filename rollover and resumes the correct session
after a restart.

Mason's daily report is deliberately three facts: **how many prints today, what
is printing now, and whether there's enough data to train the anomaly
detector.**
