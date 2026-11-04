# proposal-forge

**Proposal platforms charge you per proposal. The document
itself is a file.**

Proposify runs $19–49 per user per month — and meters the sends
themselves, at $0.30–0.50 of overage for every proposal past
your plan. Better Proposals charges $13–29 a month with entry
plans capped at roughly ten proposals. Read that again: *paying
per proposal punishes you for winning more work.* And what is
the metered thing? A document — the scope, the line items, the
honest total, the terms. A document is a file, not a
subscription.

`proposal-forge` is the file. One small JSON brief in, a
polished, self-contained HTML proposal out — plus a plain-text
twin — rendered deterministically on your own machine, with no
caps and no sends counted. A local sent-log records what went
out, when, and for how much. The tool **never sends anything
itself**, tracks no opens, and offers no e-signature anything:
you send the file the way you already send files, from your own
account, in your own name.

- Pure Python 3 standard library — no dependencies, no install step
- Local only — your briefs and client names never leave your machine
- Exact money: Decimal arithmetic, half-up to the cent, totals
  built **only** from your line items
- Script-friendly exit codes: `0` = ok, `2` = error (there is
  deliberately no exit-1 state — `make` and `log` either
  succeed or fail cleanly)

## The brief

One JSON file per proposal:

```json
{
  "business": {"name": "Harbour & Pine Web Studio",
               "contact": "hello@harbourpine.example · +1 250-555-0134 · Kelowna, BC"},
  "client":   {"name": "Delgado Family Dental",
               "contact": "Marina Delgado, office manager · office@delgadodental.example"},
  "project":  "New website for Delgado Family Dental",
  "date": "2026-11-04",
  "valid_until": "2026-12-04",
  "currency": "CAD",
  "intro": "Opening text — blank lines split it into paragraphs.",
  "scope": ["What is included, one string per point"],
  "items": [
    {"description": "Page build", "qty": 6, "unit_price": 275.50},
    {"description": "Training session (per hour)", "qty": 2.5, "unit_price": 95}
  ],
  "tax": {"label": "GST (5%)", "rate": 0.05},
  "timeline": ["Week 1: …", "Week 2: …"],
  "terms": ["A 50% deposit books the project; …"]
}
```

| Field | Meaning |
|---|---|
| `business.name` | **required** — who is proposing |
| `business.contact` | optional — printed in the acceptance block and footer |
| `client.name` | **required** — who the proposal is for |
| `client.contact` | optional — shown in the "prepared for" block |
| `project` | **required** — the proposal's title |
| `items` | **required**, at least one — `description`, `qty` (> 0, may be fractional — hours), `unit_price` (≥ 0; 0 is an included line) |
| `date` | proposal date, `YYYY-MM-DD` (default: today) |
| `valid_until` | the date the offer holds until (optional — see the honesty rules) |
| `currency` | 3-letter code, default `CAD`; every amount is in it |
| `intro` | a string; blank lines split paragraphs |
| `scope` | a list of strings |
| `tax` | optional and **all-or-nothing**: `label` *and* `rate` (a fraction — `0.05` means 5%) |
| `timeline`, `terms` | a string or a list of strings |

Validation collects **every** problem and reports them together
— missing fields, a bad date, a tax with a label but no rate —
and a brief with problems writes **nothing**. You fix the brief
once, not six times.

## The money rules (exact, and only from your items)

- Each line amount is `qty × unit_price`, rounded **half-up to
  the cent**, in Decimal — so `3 × 0.335` is `1.01`, never
  float dust.
- The subtotal is the sum of those rounded line amounts.
- The tax line exists **only** when the brief supplies both a
  label and a rate — the tool never invents a tax, a label or a
  rate. The tax is the subtotal × your rate, rounded half-up.
- The total is subtotal + tax. No other number ever appears:
  no discount you didn't write, no fee you didn't list.

## Templates

Two built-in looks, both rendering the **same facts and the
same numbers**:

- `clean` (default) — light, quiet, serif
- `bold` — dark header band, strong accent

Either way the output is **one self-contained HTML file**:
inline CSS only, **no JavaScript, no images, no web fonts, no
external requests of any kind**. The renderer adds no links or
URLs of its own; the only way a URL could appear is your own
brief text printing one — as escaped text, never as a link.
Every brief string is HTML-escaped, so a client named
`<script>alert(1)</script>` appears as text, never as markup.
Rendering is deterministic: the same brief (with its `date`
pinned, as the sample is) renders **byte-identical** files,
which the test suite pins.

The plain-text twin (`proposal.txt`) carries the same content
for email bodies, print, and diffing.

## The sent-log

```bash
python3 src/proposal_forge.py log --file sent-log.json add \
    --client "Delgado Family Dental" \
    --project "New website for Delgado Family Dental" \
    --total 5115.60 --sent 2026-11-04 \
    --proposal "delgado-website/proposal.html"

python3 src/proposal_forge.py log --file sent-log.json list
```

One JSON file (created by the first `add`), entries validated
on every read; a corrupt log is a clean error and is **never**
overwritten or silently wiped (saves are atomic: temp file +
replace). Recording the same client + project + sent date
twice is **refused** — it would count one proposal twice —
unless you pass `--force` for a genuine second send. `list`
totals are **grouped by currency**: a CAD total and a USD total
are never blended into a number that means nothing.

### Pairing with quote-follow-up

proposal-forge creates the document; its sibling
[quote-follow-up](https://github.com/jasveerai88/quote-follow-up)
tracks what happens next (follow-ups due at 3/7/14 days, won,
lost). The hand-off is one line of bookkeeping: when you send a
proposal, `log add` it here, then add the same client +
project + total to quote-follow-up's board as a quote sent on
the same date. proposal-forge does not depend on
quote-follow-up — either tool works alone — but the log's
fields (client, project, total, sent date) are exactly the
fields the follow-up board asks for, so nothing is re-typed or
re-invented.

## Usage

```bash
# 1. Write a brief (start from the bundled sample), then render
python3 src/proposal_forge.py make \
    --brief examples/sample-brief.json --out /tmp/pf2
python3 src/proposal_forge.py make \
    --brief examples/sample-brief.json --out /tmp/pf3 \
    --template bold --json

# 2. Send proposal.html yourself (email, your file share, print)

# 3. Record that you sent it
python3 src/proposal_forge.py log --file sent-log.json add \
    --client "Delgado Family Dental" \
    --project "New website for Delgado Family Dental" \
    --total 5115.60 --sent 2026-11-04 \
    --proposal "delgado-website/proposal.html"

# 4. See everything that has gone out
python3 src/proposal_forge.py log \
    --file examples/sample-sent-log.json list
```

## Use with AI agents

Every command takes `--json`: exactly one JSON object on
stdout, with the same exit codes as the text view (errors come
back as `{"error": ...}`, argparse usage errors included):

```bash
python3 src/proposal_forge.py make \
    --brief examples/sample-brief.json --out /tmp/pf3 \
    --template bold --json
```

Agents: read [SKILL.md](SKILL.md) first — commands, the brief
and log schemas, the JSON output shapes, exit codes, and the
honesty rules (totals only from the brief's line items; never
invent a tax, a deadline, a testimonial or a discount; never
record a send that didn't happen).

## Real runs (verbatim)

```text
$ python3 src/proposal_forge.py make --brief examples/sample-brief.json --out /tmp/pf2
Wrote /tmp/pf2/proposal.html and /tmp/pf2/proposal.txt
  New website for Delgado Family Dental — for Delgado Family Dental from Harbour & Pine Web Studio
  Template: clean · Date: 2026-11-04 · Valid until: 2026-12-04
  Total: $5,115.60 (6 line item(s), all amounts in CAD)
  proposal-forge generated the document only — send it yourself; nothing was sent or tracked.
(exit code: 0)
```

The sample brief's money, worked by hand: 600.00 + 1,450.00 +
(6 × 275.50 = 1,653.00) + (6 × 85.25 = 511.50) + 420.00 +
(2.5 × 95.00 = 237.50) = **subtotal 4,872.00**; GST at the
brief's 5% = **243.60**; **total 5,115.60 CAD**. The rendered
`proposal.txt` for that brief, in full:

```text
Harbour & Pine Web Studio
PROPOSAL — New website for Delgado Family Dental

Prepared for: Delgado Family Dental
Client contact: Marina Delgado, office manager · office@delgadodental.example · +1 250-555-0176
Prepared by: Harbour & Pine Web Studio
Contact: hello@harbourpine.example · +1 250-555-0134 · Kelowna, BC
Date: 2026-11-04
Valid until: 2026-12-04
All amounts in: CAD

Delgado Family Dental's current site dates from 2018: it is hard to read on a phone, the booking phone number is buried, and the services pages no longer match what the clinic offers. This proposal covers a ground-up rebuild — a fast, phone-first site that makes booking the obvious next step on every page.
Everything below is scoped from our walkthrough of the current site on 2026-10-28 and the clinic's list of services. Nothing here is padded: each line item is work we will actually do, priced as quoted.

SCOPE
-----
- A new phone-first design for the clinic: homepage plus templates for services, team and contact pages
- Build-out of six pages: home, four service pages (cleanings, implants, orthodontics, emergency care) and a contact page with the booking number throughout
- Online booking setup: connect the clinic's booking form, test it end to end on phone and desktop
- Copy polish on all six pages, working from the clinic's existing text
- A one-hour training session for front-desk staff on updating hours, holiday closures and team bios

THE WORK, PRICED
----------------
Discovery and sitemap                     1 x      $600.00       $600.00
Design — homepage and page templates      1 x    $1,450.00     $1,450.00
Page build — services, team, contact      6 x      $275.50     $1,653.00
Copy polish (per page)                    6 x       $85.25       $511.50
Online booking setup and testing          1 x      $420.00       $420.00
Training session (per hour)             2.5 x       $95.00       $237.50
Subtotal                                                       $4,872.00
GST (5%)                                                         $243.60
Total (CAD)                                                    $5,115.60

TIMELINE
--------
- Week 1: discovery, sitemap and design direction confirmed with the clinic
- Weeks 2–3: page build and copy polish, with a review link sent at the end of week 2
- Week 4: booking setup, testing on phone and desktop, staff training, launch

TERMS
-----
- A 50% deposit books the project; the balance is due on launch day
- Two rounds of design revisions are included; further rounds are billed at the training-session hourly rate
- The clinic supplies text, photos and the service list; the studio supplies the build, setup and training described above
- Prices are in CAD and hold until the valid-until date on this proposal

ACCEPTANCE
----------
To accept this proposal, contact Harbour & Pine Web Studio at hello@harbourpine.example · +1 250-555-0134 · Kelowna, BC. This proposal is valid until 2026-12-04.

Accepted for Delgado Family Dental: ______________________________   Date: ______________

Harbour & Pine Web Studio · hello@harbourpine.example · +1 250-555-0134 · Kelowna, BC
```

The `proposal.html` twin carries the identical content and
numbers under the chosen template's styling — open it in any
browser, attach it, or print it to PDF.

The sent-log flow, verbatim — including the duplicate refusal:

```text
$ python3 src/proposal_forge.py log --file /tmp/demo-log.json add --client "Delgado Family Dental" --project "New website for Delgado Family Dental" --total 5115.60 --sent 2026-11-04 --proposal "delgado-website/proposal.html"
Recorded proposal #1: Delgado Family Dental — New website for Delgado Family Dental — $5,115.60 — sent 2026-11-04
Sent-log: demo-log.json (1 proposal(s))
(exit code: 0)

$ python3 src/proposal_forge.py log --file /tmp/demo-log.json add --client "Delgado Family Dental" --project "New website for Delgado Family Dental" --total 5115.60 --sent 2026-11-04
ERROR: already recorded: Delgado Family Dental — New website for Delgado Family Dental — sent 2026-11-04 is log entry #1. Recording it twice would count the proposal twice; pass --force if this really was a second send on the same day.
(exit code: 2)

$ python3 src/proposal_forge.py log --file examples/sample-sent-log.json list
proposal-forge v0.1.0 — log list · file sample-sent-log.json

#1 · 2026-10-21 · Okanagan Trail Outfitters — Booking page refresh — $1,890.00 · file: booking-refresh/proposal.html
#2 · 2026-11-04 · Delgado Family Dental — New website for Delgado Family Dental — $5,115.60 · file: delgado-website/proposal.html

Totals by currency: CAD $7,005.60 (2)
Totals are kept per currency — they are never blended into one number.
(exit code: 0)
```

And a brief with problems — every one named, nothing written:

```text
$ python3 src/proposal_forge.py make --brief /tmp/bad-brief.json --out /tmp/never
ERROR: the brief has 3 problem(s) — nothing was written:
  - client is required — an object with a 'name' (and optionally a 'contact')
  - project is required and must be a non-empty string
  - items[0].unit_price is required and must be a number (got None)
(exit code: 2)
```

## Tests

```bash
python3 -m unittest discover -s tests -v
# Ran 46 tests — OK
```

The suite covers both directions: the sample brief's totals
are matched against hand-worked arithmetic (above); the
rounding pins are Decimal-exact (`3 × 0.335 → 1.01`,
`1 × 2.675 → 2.68`, tax on 199.99 → 10.00); validation names
**all** problems in one error, including per-item positions
and the all-or-nothing tax rule; both templates render
**byte-identical** output across runs; a brief containing
`<script>` in the client name renders it as escaped text in
HTML and raw text in the .txt; the rendered HTML is asserted
to contain no `http://`, `https://`, `<script`, `<img`,
`<link`, `url(` or `@import`; the log refuses duplicates
(case-insensitively), keeps per-currency totals separate in
text and JSON, and a corrupt brief or log errors cleanly with
the file left byte-identical.

## Who this is for

Freelancers and small studios — web designers, brand
designers, consultants, trades quoting bigger jobs — who write
a handful of proposals a month and refuse to rent the document
back from a platform at $19–49 a seat plus a toll per send. If
hosted e-signature and open-tracking are the whole point for
you, this tool honestly isn't that: it makes the document and
keeps the log, and you send. Many solo operators prefer
exactly that — the proposal arrives from their own address,
as a file they own.

## Internal use

This tool does a real job for its author: **Focus Brilliant**,
the author's website-building service for local trades and
clinic clients, writes its proposals with it — the bundled
sample is the shape of a real Focus Brilliant website proposal
(a Kelowna dental clinic; names and contacts are fictional).
The sent-log then hands each sent proposal to quote-follow-up,
so no proposal quietly goes cold for want of a follow-up.

## Known limits

- Briefs are JSON in v0.1.0. (A Markdown brief format is a
  plausible future addition; the JSON schema is the contract
  today.)
- One currency per proposal, and log totals stay per currency.
  A multi-currency practice gets separate honest totals, not a
  converted blend — conversion would need a rate, and the tool
  invents none.
- `make` always writes `proposal.html` / `proposal.txt` into
  the `--out` folder (re-rendering overwrites them — rendering
  is deterministic, so a re-render of the same brief changes
  nothing). Keep one folder per proposal, as the sample log's
  `proposal` paths do.
- `log add` takes the total you give it. It deliberately does
  not re-derive the total from a brief: what you actually sent
  may have been renegotiated after the brief was written, and
  the log records what was sent, not what was drafted.
- No sending, no open-tracking, no e-signature — by design,
  permanently. The acceptance block is for reply or wet-ink
  signature on a printed copy.

## Privacy

What it touches: only the brief and log files you point it at,
and the `--out` folder. What it sends: nothing — there is no
network code in this tool.

## Support

If this replaces one month of a per-send proposal bill,
consider sponsoring: **https://github.com/sponsors/jasveerai88**

## Licence

MIT — see [LICENSE](LICENSE).
