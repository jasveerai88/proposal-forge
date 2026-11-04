---
name: proposal-forge
description: Turn a small JSON brief into a polished, self-contained HTML proposal (plus a plain-text twin) and keep a local log of sent proposals. Use when a freelancer or small agency wants the core job of Proposify ($19–49/user/mo plus $0.30–0.50 per-send overages) or Better Proposals ($13–29/mo, ~10-proposal entry caps) — the proposal document itself, with exact totals — as a file they own, with no caps and no sends counted. The tool generates and logs only; it never sends, tracks opens, or offers e-signature. Exit codes are 0 (ok) and 2 (clean error) only — there is no exit-1 state.
---

# proposal-forge — agent skill

## Purpose

A proposal is a document: the scope, the line items, the
honest total, the terms, the date it holds until. Platforms
rent that document back to freelancers per seat and per send.
This tool renders it locally from one JSON brief —
deterministically, in two built-in templates — and keeps a
sent-log so what went out (client, project, total, date) can
hand off to follow-up tracking. Pure Python standard library;
local only; the brief, the output folder and the log file are
the only things it reads or writes.

**The honesty core of this tool:** every number in the
document comes from the brief's line items and nothing else.
There is no field, flag or supported edit that adds a tax the
brief didn't declare, extends a valid-until date, inserts a
testimonial, or pads a total. If the brief is wrong, fix the
brief — never patch the rendered output.

## When to use / not use

Use when:
- A freelancer or small studio needs a client proposal
  document (HTML + plain text) from structured facts.
- An agent drafts briefs from job notes and renders proposals
  for the owner to send personally.
- A sent proposal must be recorded so it can be followed up
  (pairs with the sibling tool quote-follow-up; neither
  depends on the other).

Do NOT use when:
- The user wants the tool to *send* the proposal, track
  opens, or collect an e-signature. Refuse those parts
  plainly: they are hosted-platform features, permanently out
  of scope; the acceptance block is for reply or print
  signature.
- The user asks you to "just add GST" (or any tax), a
  discount, a testimonial or a deadline that is not in the
  brief. Those are facts only the user can supply — ask for
  them and put them in the brief.

## Commands

```bash
# Render a proposal (validates the brief first; a brief with
# problems writes NOTHING and reports them all at once)
python3 src/proposal_forge.py make --brief brief.json \
    --out FOLDER [--template clean|bold] [--json]

# Record a proposal the owner actually sent (creates the log)
python3 src/proposal_forge.py log --file sent-log.json add \
    --client "Delgado Family Dental" \
    --project "New website for Delgado Family Dental" \
    --total 5115.60 [--sent 2026-11-04] [--currency CAD] \
    [--proposal "delgado-website/proposal.html"] [--force]

# Everything sent, with totals grouped by currency
python3 src/proposal_forge.py log --file sent-log.json list \
    [--json]
```

## The brief (JSON)

Root object. Unknown fields are ignored.

| Field | Rules |
|---|---|
| `business` | object; `name` **required** (non-empty); `contact` optional string, printed in the acceptance block and footer |
| `client` | object; `name` **required**; `contact` optional |
| `project` | **required**, non-empty string — the title |
| `items` | **required**, ≥ 1 entry: `description` (non-empty), `qty` (number > 0; fractional allowed — hours), `unit_price` (number ≥ 0; 0 = included line) |
| `date` | `YYYY-MM-DD`, optional; default today |
| `valid_until` | `YYYY-MM-DD`, optional; if both it and `date` are given, it must not be before `date` |
| `currency` | 3-letter code, default `CAD`, normalised to upper case |
| `intro` | string (blank lines split paragraphs) |
| `scope` | list of strings |
| `timeline`, `terms` | string or list of strings |
| `tax` | optional, **all-or-nothing**: `label` (non-empty) AND `rate` (fraction, 0 < rate ≤ 1; `0.05` = 5%). One without the other is an error |

Validation collects **every** problem into one error that
names each field (per-item problems are named by position,
e.g. `items[0].unit_price`). Nothing is rendered or written
when a brief has problems.

## Money (exact rules)

- Amounts are `Decimal` end to end (inputs converted via
  their shortest string form, so `0.05` is exact).
- Line amount = `qty × unit_price` rounded **half-up** to
  cents. Subtotal = sum of the **rounded** line amounts.
- Tax (only when the brief declares one) = subtotal × rate,
  rounded half-up. Total = subtotal + tax.
- Display: `$` for CAD/USD/AUD/NZD, `€` EUR, `£` GBP; any
  other code prefixes the amount (`CHF 100.00`). The document
  states its currency; all amounts are in it.

## Rendering guarantees

- One self-contained HTML file: inline CSS only. **No
  JavaScript, no images, no fonts, no external requests.** The
  renderer adds no links or URLs of its own; a URL inside
  brief text prints as escaped text, never as a link.
- Every brief string is HTML-escaped in the HTML output
  (`<script>` in a name renders as text). The .txt twin
  prints brief text as-is.
- Deterministic: same brief → byte-identical files (the only
  clock input is the brief's `date`, defaulting to today —
  pin it in the brief for reproducible renders).
- Templates: `clean` (default) and `bold`. An unknown
  template is a clean error listing both, and writes nothing.
- Output names are fixed: `proposal.html`, `proposal.txt` in
  the `--out` folder (created if missing; re-rendering
  overwrites deterministically). Keep one folder per
  proposal.

## The sent-log (JSON)

Root: `{"proposals": [entry, ...]}` (a bare list is also
accepted on read). Entry: `id` (assigned by `add`, never
reused), `client`, `project` (non-empty strings), `total`
(number ≥ 0), `currency` (3-letter, default CAD), `sent`
(`YYYY-MM-DD`), `proposal` (path string, recorded never
opened; may be empty). The log is validated on every read —
errors name the entry (`log entry 2: ...`). A corrupt log is
a clean error and is **never** overwritten; saves are atomic
(temp file + replace).

Duplicates: same `client` + `project` (case-insensitive) +
same `sent` date → refused with exit 2; `--force` records a
genuine second send. **Totals in `list` are grouped by
currency** — never blended.

## Output JSON schema (`--json`)

Common fields: `tool` (`"proposal-forge"`), `version`,
`command`, `file`/`brief` (file name).

- `make`: `template`, `out_dir`, `files` (the two paths),
  `business`, `client`, `project`, `date`, `valid_until`
  (or null), `money` — `{lines: [{description, qty,
  unit_price, amount}], subtotal, tax: {label, rate, amount}
  | null, total, currency}`. Amounts are numbers (ints when
  whole).
- `log add`: `entry` (the stored entry), `entries` (count).
- `log list`: `proposals` (entries sorted by `sent`, then
  `id`), `totals` — `{CCC: {count, amount}}` per currency.

On error, stdout is a single object: `{"error": "<message>"}`
with exit code 2 — including argparse usage errors in
`--json` mode. Never plain text, never a traceback.

## Exit codes

- `0` — success. (`make` wrote both files; `log add`
  recorded; `log list` printed.)
- `2` — ERROR: brief missing/corrupt/invalid (all problems
  named), unknown template, `--out` not a folder, log
  missing (for `list`), log corrupt (file left untouched),
  duplicate send without `--force`, invalid flag values.
  Nothing was written or changed; do not quote numbers from
  a failed run.
- There is **no exit 1** in this tool — no view has an
  "attention" state.

## Limits & honesty rules the agent must respect

- **Totals come only from the brief's line items.** Never
  patch a rendered proposal's numbers, and never state a
  total you didn't get from a successful `make` run.
- **Never invent a tax.** If a proposal needs one, the brief
  must carry `tax.label` and `tax.rate` from the user. A
  label without a rate (or the reverse) is an error by
  design — surface it, don't fill it in.
- **Never invent or extend a deadline.** `valid_until` is
  the brief's date or absent (the document then names no
  deadline). Do not "refresh" it on a re-render unless the
  user supplies a new date for the brief.
- **No invented proof.** Testimonials, client logos, past
  results, discounts and "limited-time" pressure are not
  fields of this tool. If the user wants such wording, it
  belongs in their own `intro`/`terms` text, in their own
  words — do not draft claims you can't verify.
- **Record only real sends.** Run `log add` after the owner
  actually sent the proposal, with the total that was
  actually sent (it may differ from the last render after a
  negotiation — the log records what was sent, not what was
  drafted; that is why `add` takes `--total` explicitly
  instead of re-reading a brief).
- **Duplicates protect the record.** Don't reach for
  `--force` to tidy the log — it is only for a genuine
  second send of the same proposal on the same day.
- **Per-currency totals are the honest totals.** When
  relaying `log list`, keep currencies separate; never sum
  across currencies or convert at a rate the user didn't
  give you.
- Local only, sends nothing: the tool reads/writes only the
  brief, the `--out` folder and the log file named with
  `--file`.
