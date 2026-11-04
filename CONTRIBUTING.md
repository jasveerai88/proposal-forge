# Contributing

Contributions are welcome — bug reports, fixes and small focused features.

## Ground rules

- **Standard library only.** proposal-forge's promise is
  "clone and run". Pull requests that add a third-party dependency
  will not be merged.
- **Local only, and it never sends.** No network calls, no
  telemetry, no uploads of user files, and no sending,
  open-tracking or e-signature features: the tool generates a
  document and keeps a log; the owner sends from their own
  account, in their own name. A pull request that adds a
  sending integration changes what this tool *is* and will not
  be merged.
- **The numbers come from the brief, or they don't appear.**
  Totals are built only from the brief's line items, in
  Decimal, rounded half-up per line. A tax line exists only
  when the brief declares both a label and a rate; a deadline
  exists only when the brief sets `valid_until`. A change that
  lets the tool invent, default or "helpfully" adjust a tax, a
  total or a date will not be merged.
- **Rendering stays deterministic and self-contained.** The
  same brief must render byte-identical output (the brief's
  `date` is the only clock input), and the HTML must stay a
  single file with inline CSS — no JavaScript, no external
  requests, no renderer-added links — with every brief string
  HTML-escaped. Tests pin both properties; keep them passing
  when you touch a template, and keep the two templates
  carrying identical facts and numbers.
- **The log is the user's business record.** A change that can
  lose, corrupt or silently rewrite log entries will not be
  merged. Loading must keep validating every entry; saving
  must stay atomic; a corrupt log must stay an error, never a
  wipe. Duplicate protection (same client + project + sent
  date, refused without `--force`) and per-currency totals
  are promises, not preferences — weakening either needs the
  README, the changelog, the SKILL.md schema and the tests
  updated together, and a very good reason.
- **Validation reports everything at once.** Brief problems
  are collected and named together (per-item problems by
  position) so the author fixes the brief once. Don't regress
  to fail-on-first-problem, and don't let a bad brief write
  partial output — nothing is written until the brief is
  clean.
- **Both directions tested.** A behaviour change needs a test
  where good input succeeds and bad input fails cleanly — not
  just one side. Money math needs hand-computed expectations
  in the test, not figures copied from the tool's own output.
