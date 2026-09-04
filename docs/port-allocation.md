# Host port allocation

**Read this before writing a compose file or a `forge_registry.base_url`.**

Three Forges have now solved the same problem separately and none of the three fixes was
written down, so the fourth discovers it again:

    CRE Forge     docker-compose.override.yml remaps 5432 -> 55432, 8000 -> 8011, 8080 -> 8081
    SimForge      ran on 8100, which was NOT free; moved to 8110 on 4 September
    AnimaForge    needs the same override and does not have one - its compose wants 4000,
                  3001, 3002, 5432, 8001, all but one of which are taken

This page is that record.

---

## ⚠ THIS IS A SNAPSHOT, NOT AN AUTHORITY

**It records what was allocated on 4 September 2026. It does not record what is listening
right now, and it cannot.** Nothing generates it and nothing checks it — deliberately: a
second hand-written list to compare against would compare two claims, which is the shape V6
and `docs/decisions.md` entries 4 and 7 already warn about.

**`docker ps --format '{{.Names}}\t{{.Ports}}'` is what tells you who owns a port.** This
table tells you what somebody intended. When the two disagree, `docker ps` is right.

If you find yourself citing this page as proof a port is free, stop — that is
`forge_map.ESTATE`'s problem built a second time, and entry 7 is about what that costs.

---

## The one that matters: 5432

**`5432` is the native PostgreSQL serving The Office's own development and test databases.**
It is not a container. It does not move.

**AnimaForge's committed compose binds `5432:5432`.** Starting it as-committed takes that
port out from under The Office, and The Office's databases go with it.

That is a different failure from the one trap #8 describes. Trap #8 is a *probe* reading the
wrong system — an observer being misled. This is a *service* taking something real out from
under something real, and no amount of careful reading prevents it. It happens at
`docker compose up`.

CRE Forge already hit this and its override header says so at length, including the
`!override` merge trap that a plain value falls into. **Copy that file's approach; do not
re-derive it.** And per trap #8, an override must not reach CI — the job passes
`-f docker-compose.yml` explicitly (`medlink-wholesale/docs/decisions/0001`).

---

## Allocated, 4 September 2026

### The Office and the Village

| Port | Belongs to | Notes |
|---|---|---|
| **5432** | **native PostgreSQL — The Office's dev + test databases** | not a container; the port everything else must avoid |
| 8002 | the Village (`VILLAGE_BASE_URL`, `app.py` default `VILLAGE_PORT`) | **squatted today** — see below |

### Forges, as registered

| Port | Forge | `forge_registry.base_url` |
|---|---|---|
| 4000 | CapitalForge | `http://127.0.0.1:4000/api/office` |
| 8011 | CRE Forge | `http://127.0.0.1:8011/forge` — remapped from 8000 by its override |
| **8110** | **SimForge** | `http://127.0.0.1:8110/office` — moved here 4 Sep; verified free by `docker ps -a`, `netstat` and a live probe on both address spellings before binding |
| — | VoiceForge | `https://example.invalid` — never deployed |

### Currently squatting

Not allocations. Containers from other projects that hold ports something else expects:

| Port | Held by | What expected it |
|---|---|---|
| 3001 | `visonaudioforge-frontend-1` | AnimaForge `platform-api`; misread as FunnelForge during recon |
| 3002 | `vaf-ws-k-container-runtime-frontend-1` | AnimaForge `realtime`; misread as FunnelForge |
| 8000 | `visonaudioforge-api-1` | CRE Forge's committed compose (hence its override) |
| 8100 | `voice-forge-asr` | **SimForge, until 4 Sep** — it never owned the port; see below |
| 8001 | `vaf-ws-k-container-runtime-api-1` | AnimaForge `ai-api` |
| **8002** | `vaf-ws-j-pipeline-persistence-api-1` | **the Village** — its 401 was read as the Village refusing a credential for a week |

### Other projects, for avoidance

`3055`, `3300`, `3301` (VoiceForge app/studio), `5200`, `5533`, `6479`, `8080`, `8085`,
`8090`, `9011`, `9021`, `55432` and `56379` (CRE Forge's remapped db/redis) are in use by
VoiceForge, VisionAudioForge and the VAF workstream stacks.

---

## SimForge's 8100 was not free — the correction, and the move

**Resolved 4 September 2026. SimForge is on 8110.** What follows is why, kept because the
mechanism is the lesson.

It was chosen on 4 September after checking that 8000 was taken. **8100 was not checked, and
it was not free:** `voice-forge-asr` publishes `0.0.0.0:8100->8000/tcp`.

Both are listening right now:

    0.0.0.0:8100      PID 45504    Docker proxy -> voice-forge-asr
    127.0.0.1:8100    PID 122140   SimForge's uvicorn (started with --host 127.0.0.1)

They do not conflict at bind time because the addresses differ — a specific bind and a
wildcard bind can coexist. **Which one a client reaches depends on the address it dials:**
`127.0.0.1:8100` reaches SimForge because the specific binding wins; the machine's LAN
address reaches VoiceForge's ASR.

`forge_registry.base_url` for simforge is `http://127.0.0.1:8100/office`, so it works today
**by an accident of bind specificity, not because the port is SimForge's.** Start SimForge
without `--host 127.0.0.1`, or reach it by any other address, and The Office is talking to a
speech-recognition service.

CRE Forge's override header already warned about the general case in different words:
*"Ports were chosen with the Docker daemon RUNNING. Checked while it was down, 8001 looked
free and was not."* The variant here is narrower and worse — the port was checked while the
daemon was up, and the check was simply not run for the port that was chosen.

### What the move proved on the way out

Stopping SimForge's uvicorn and re-requesting its own registered `base_url`:

    GET http://127.0.0.1:8100/office/_modules   ->  404

**Not a connection refusal — a 404 from `voice-forge-asr`.** The Office's registry row,
unchanged, pointing at a speech-recognition service that answered. Every result the bridge
had produced rested on a specific bind winning over a wildcard one, which nobody chose.

### After the move

`8110` was checked four ways before anything bound to it: `netstat -ano` in any state,
`docker ps -a` for published **or** exposed, and a live probe on `127.0.0.1` and on
`localhost`. All four said nothing was there.

Both address spellings now reach SimForge, and that is the substantive change — **on an
uncontested port the failure mode becomes a connection error rather than a wrong service.**
The bridge was re-verified end to end afterwards: `run/start` 200, brokered call 200,
`manifest_match: required`, and the ledger's `forge_side_ref` present as `forge_request_id`
in SimForge's own log with `office_trace` matching the ledger's `trace_id`.

**8100 is back to `voice-forge-asr` alone.**

---

## Picking a port

1. `docker ps --format '{{.Names}}\t{{.Ports}}'` — with the Docker daemon **running**.
2. `netstat -ano | grep LISTENING` — catches native services like PostgreSQL on 5432 that
   never appear in `docker ps`.
3. Check the port you are about to use, not just the one you are avoiding. That is the step
   that was skipped for 8100.
4. Add it to the table above in the same commit that uses it.

Step 4 is the whole point of the page, and it is the step with nothing enforcing it.
