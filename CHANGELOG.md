# Changelog

## v0.1.0 — 2026-11-04

First release.

- **`make` — a brief becomes a proposal.** One JSON brief
  (business, client, project, intro, scope, priced line
  items, timeline, terms, valid-until, currency) renders to
  a self-contained `proposal.html` plus a plain-text
  `proposal.txt` in the `--out` folder. The brief is
  validated first, and validation collects **every** problem
  — missing fields named individually, per-item problems
  named by position (`items[0].unit_price`), an impossible
  date, a `valid_until` earlier than the proposal date —
  into one error; a brief with problems writes **nothing**.
  A corrupt brief is a clean error and is never modified.
- **Exact money, from the line items only.** Decimal
  arithmetic throughout: each line amount is
  `qty × unit_price` rounded **half-up to the cent** (qty may
  be fractional — hours; a unit price of 0 is an included
  line); the subtotal is the sum of the rounded lines; the
  total is subtotal + tax. There is no code path that adds a
  fee, discount or adjustment the brief didn't state.
- **A tax line only when the brief declares one.** `tax` is
  all-or-nothing — a `label` *and* a `rate` (a fraction:
  `0.05` is 5%) — and one without the other is a validation
  error naming the missing half. The tool never invents a
  tax, a label or a rate.
- **Two built-in templates** — `clean` (light, serif) and
  `bold` (dark header band, strong accent) — rendering the
  same facts and the same numbers. An unknown template is a
  clean error listing the available ones. Rendering is
  **deterministic**: the same brief renders byte-identical
  files (the only clock input is the brief's `date`, which a
  brief can pin), pinned by tests for both templates.
- **Self-contained and safe HTML, by construction.** Inline
  CSS only; no JavaScript, no images, no web fonts, no
  external requests of any kind. The renderer adds no links
  or URLs of its own; every brief string is HTML-escaped, so
  markup in a client name renders as text. The suite asserts
  the rendered sample contains no `http://`, `https://`,
  `<script`, `<img`, `<link`, `url(` or `@import`.
- **An acceptance block built from brief facts** — who to
  contact to accept, the valid-until date *only if the brief
  sets one*, and print signature lines. No deadline is ever
  invented or extended, and there is no e-signature claim.
- **`log` — the sent-log.** `log add` records a proposal you
  sent (client, project, total, currency, sent date, the
  proposal file's path) into one local JSON file created by
  the first add; `log list` shows everything sent with
  **totals grouped by currency** — CAD and USD are never
  blended into one meaningless number. Entries are validated
  on every read with errors that name the entry; a corrupt
  log is a clean error and is **never overwritten**; saves
  are atomic (temp file + replace); ids are never reused.
- **Duplicate sends are refused.** Same client + project
  (case-insensitive) + same sent date is already recorded —
  recording it again would count one proposal twice. The
  refusal names the existing entry and the one escape hatch:
  `--force`, for a genuine second send on the same day.
  `log add` takes the total explicitly rather than
  re-reading a brief: what was actually sent may have been
  renegotiated after drafting, and the log records what was
  sent.
- **Pairs with quote-follow-up, without depending on it.**
  The log's fields (client, project, total, sent date) are
  exactly what the sibling follow-up board asks for, so a
  sent proposal becomes a tracked quote with no re-typing.
- **`--json` on every command** — exactly one JSON object on
  stdout; errors are `{"error": ...}` objects with exit 2,
  argparse usage errors included. Exit codes are `0` (ok)
  and `2` (error) only — there is deliberately no exit-1
  state.
- Bundled examples: `examples/sample-brief.json` — a
  complete fictional Kelowna website proposal (fictional
  studio, fictional dental clinic, reserved `.example`
  contacts) whose totals are worked by hand in the README
  (subtotal 4,872.00 · GST 243.60 · total 5,115.60 CAD) —
  and `examples/sample-sent-log.json`, two recorded sends
  totalling CAD 7,005.60.
- 46 stdlib-unittest tests: hand-computed sample totals,
  Decimal rounding pins (`3 × 0.335 → 1.01`,
  `1 × 2.675 → 2.68`, tax on 199.99 → 10.00), all-problems
  validation, the all-or-nothing tax rule, byte-identical
  re-renders for both templates, HTML escaping both ways
  (escaped in HTML, raw in text), the no-external-references
  scan, duplicate refusal + `--force`, per-currency totals
  in text and JSON, and corrupt-file safety (byte-identical
  after failed runs).
- Pure Python standard library; local only; generates and
  logs — never sends; MIT licence.
