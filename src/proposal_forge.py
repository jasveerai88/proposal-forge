#!/usr/bin/env python3
"""proposal-forge — turn a small client/project brief into a
polished, self-contained proposal document, and keep a local log
of what you sent.

Pure Python standard library. Local only: no network, no uploads,
no accounts. Your briefs and proposals never leave your machine.

Proposal platforms sell the *sending* of a proposal as a
subscription: Proposify runs $19–49 per user per month AND meters
the sends themselves ($0.30–0.50 of overage per proposal past the
plan), and Better Proposals charges $13–29 a month with entry
plans capped at roughly ten proposals. But the document is the
job — the scope, the line items, the honest total, the terms —
and a document is a file, not a subscription. proposal-forge is
the file: one JSON brief in, a self-contained HTML proposal (and
a plain-text twin) out, deterministically, with no caps and no
sends counted.

It never sends anything itself, tracks no opens, and offers no
e-signature anything. You send the file the way you already send
files. Its sibling quote-follow-up tracks the follow-up AFTER a
quote exists; proposal-forge is the half before that — it
creates the document.

The brief is a single JSON file:

  business    {"name": ..., "contact": ...} — who is proposing
              (name required; contact optional, printed in the
              acceptance block and the footer)
  client      {"name": ..., "contact": ...} — who it is for
              (name required; contact optional)
  project     the proposal's title (required)
  date        proposal date, YYYY-MM-DD (default: today)
  valid_until the date the offer holds until, YYYY-MM-DD (or
              absent — the document then names no deadline; the
              tool never invents or extends one)
  currency    3-letter code, default "CAD" — every amount in
              the document is in this currency
  intro       opening text (a string; blank lines split it into
              paragraphs)
  scope       the scope section: a list of strings (or absent)
  items       the priced work (required, at least one):
              [{"description": ..., "qty": ..., "unit_price": ...}]
              qty may be fractional (hours); unit_price may be 0
              (an included line)
  tax         {"label": "GST (5%)", "rate": 0.05} — OPTIONAL and
              all-or-nothing: the tax line appears only when the
              brief supplies BOTH a label and a rate (a fraction:
              0.05 means 5%). The tool never invents a tax.
  timeline    a string or a list of strings (or absent)
  terms       a string or a list of strings (or absent)

Money is exact to the cent, computed with Decimal: each line
amount is qty x unit_price rounded half-up to cents; the
subtotal is the sum of those rounded line amounts; the tax is
the subtotal x the brief's rate, rounded half-up to cents; the
total is subtotal + tax. No other number ever appears — totals
come only from the brief's line items.

Commands:
  make      --brief FILE --out DIR [--template clean|bold]
            [--json] — validate the brief, then render
            proposal.html + proposal.txt into DIR. Validation
            collects EVERY problem and reports them together;
            a bad brief writes NOTHING.
  log       --file FILE add --client C --project P --total T
            [--sent D] [--currency CCC] [--proposal PATH]
            [--force] — record a proposal you sent. A duplicate
            (same client + project + sent date) is refused
            unless --force.
  log       --file FILE list — every recorded proposal, with
            totals GROUPED BY CURRENCY (CAD and USD are never
            added together into a meaningless blend).

Templates are built in: "clean" (light, quiet) and "bold"
(dark header band, strong accent). Both produce ONE
self-contained HTML file: inline CSS only, no JavaScript, no
images, no fonts, no external requests of any kind — the
renderer adds no links or URLs of its own; brief text is
HTML-escaped and printed as text, never as markup. Rendering is
deterministic: the same brief renders byte-identical output
(the only clock input is the proposal `date`, which the brief
can pin).

Exit codes: 0 = ok · 2 = ERROR — clean message, never a
traceback; with --json the error is {"error": ...}. There is
deliberately no exit-1 state: `make` and `log` either succeed
or fail cleanly. A corrupt brief or log is an error and is
NEVER overwritten or silently wiped; log saves are atomic
(temp file + replace).
"""
import argparse
import html
import json
import math
import os
import re
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from string import Template

__version__ = "0.1.0"
TOOL = "proposal-forge"

TEMPLATES = ("clean", "bold")
DEFAULT_TEMPLATE = "clean"
DEFAULT_CURRENCY = "CAD"
_CENT = Decimal("0.01")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY_RE = re.compile(r"^[A-Za-z]{3}$")
_SYMBOLS = {"CAD": "$", "USD": "$", "EUR": "€", "GBP": "£",
            "AUD": "$", "NZD": "$"}


class ToolError(Exception):
    """A clean, user-facing failure (printed as ERROR, exit 2)."""


# --------------------------------------------------------------------------
# money — Decimal end to end, half-up to the cent
# --------------------------------------------------------------------------

def _dec(value):
    """A JSON number -> Decimal via its shortest string form, so
    0.05 means exactly 0.05 and never 0.05000000000000000277."""
    return Decimal(str(value))


def _cents(value):
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _is_number(value):
    return not isinstance(value, bool) \
        and isinstance(value, (int, float)) \
        and math.isfinite(value)


def fmt_money(amount, currency):
    """Decimal -> display string: '$5,115.60' for symbol
    currencies, 'CHF 5,115.60' for any other code."""
    symbol = _SYMBOLS.get(currency)
    if symbol:
        return f"{symbol}{amount:,.2f}"
    return f"{currency} {amount:,.2f}"


def fmt_qty(qty):
    """Decimal qty -> '6' for whole numbers, '2.5' for fractional
    (trailing zeros trimmed)."""
    if qty == qty.to_integral_value():
        return str(int(qty))
    return format(qty.normalize(), "f")


def _num(value):
    """Decimal -> int when whole, else float (for JSON output)."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

def parse_date(value, label):
    """Strict YYYY-MM-DD -> date, or a clean ToolError naming
    `label`."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ToolError(f"{label} must be a date as YYYY-MM-DD "
                        f"(got {value!r})")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{label} is not a real calendar date: "
                        f"{value!r}")


# --------------------------------------------------------------------------
# the brief — load + validate (every problem reported together)
# --------------------------------------------------------------------------

def _reject_json_constant(name):
    raise ValueError(f"invalid constant {name}")


def load_json_file(path, kind):
    """Read + parse a JSON file -> its data, or a clean ToolError.
    The file is only READ here; a corrupt file is reported, never
    repaired in place."""
    if not path.is_file():
        raise ToolError(f"{kind} not found: {path}")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"could not read {kind} {path.name} "
                        f"({exc.__class__.__name__}) — the file "
                        f"was left untouched")
    try:
        return json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise ToolError(f"{kind} {path.name} is not valid JSON: "
                        f"{exc} — the file was left untouched")


def _party(raw, label, problems):
    """A {"name", "contact"} block: name required (non-empty),
    contact optional. Returns {"name": ..., "contact": ...}."""
    if not isinstance(raw, dict):
        problems.append(f"{label} is required — an object with a "
                        f"'name' (and optionally a 'contact')")
        return {"name": "", "contact": ""}
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append(f"{label}.name is required and must be a "
                        f"non-empty string")
        name = ""
    contact = raw.get("contact", "")
    if not isinstance(contact, str):
        problems.append(f"{label}.contact must be a string "
                        f"(got {contact!r})")
        contact = ""
    return {"name": name.strip(), "contact": contact.strip()}


def _string_list(raw, label, problems):
    """intro/timeline/terms accept a string or a list of strings;
    scope takes a list. Normalise to a list of strings."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        out = []
        for i, item in enumerate(raw):
            if not isinstance(item, str) or not item.strip():
                problems.append(f"{label}[{i}] must be a "
                                f"non-empty string")
            else:
                out.append(item)
        return out
    problems.append(f"{label} must be a string or a list of "
                    f"strings (got {raw!r})")
    return []


def _brief_date(raw, field, problems):
    if raw is None:
        return None
    try:
        return parse_date(raw, f"'{field}'").isoformat()
    except ToolError as exc:
        problems.append(str(exc))
        return None


def validate_brief(data):
    """Validate a parsed brief -> a clean brief dict. Every
    problem found is collected and raised together in ONE
    ToolError, so the author fixes the brief once, not six
    times. Raises before anything is rendered or written."""
    if not isinstance(data, dict):
        raise ToolError("the brief must be a JSON object of "
                        "fields (business, client, project, "
                        "items, ...)")
    problems = []
    business = _party(data.get("business"), "business", problems)
    client = _party(data.get("client"), "client", problems)
    project = data.get("project")
    if not isinstance(project, str) or not project.strip():
        problems.append("project is required and must be a "
                        "non-empty string")
        project = ""
    items_raw = data.get("items")
    items = []
    if not isinstance(items_raw, list) or not items_raw:
        problems.append("items is required — a list with at "
                        "least one priced line item")
    else:
        for i, raw in enumerate(items_raw):
            where = f"items[{i}]"
            if not isinstance(raw, dict):
                problems.append(f"{where} must be an object with "
                                f"description, qty and unit_price")
                continue
            desc = raw.get("description")
            if not isinstance(desc, str) or not desc.strip():
                problems.append(f"{where}.description is required "
                                f"and must be a non-empty string")
                desc = ""
            qty = raw.get("qty")
            if not _is_number(qty):
                problems.append(f"{where}.qty is required and "
                                f"must be a number (got {qty!r})")
                qty = 0
            elif _dec(qty) <= 0:
                problems.append(f"{where}.qty must be greater "
                                f"than 0 (got {qty!r})")
            price = raw.get("unit_price")
            if not _is_number(price):
                problems.append(f"{where}.unit_price is required "
                                f"and must be a number "
                                f"(got {price!r})")
                price = 0
            elif _dec(price) < 0:
                problems.append(f"{where}.unit_price must be 0 or "
                                f"more (got {price!r})")
            items.append({"description": desc.strip() if desc
                          else "",
                          "qty": qty, "unit_price": price})
    tax = None
    tax_raw = data.get("tax")
    if tax_raw is not None:
        if not isinstance(tax_raw, dict):
            problems.append("tax must be an object with a 'label' "
                            "and a 'rate'")
        else:
            label = tax_raw.get("label")
            rate = tax_raw.get("rate")
            if not isinstance(label, str) or not label.strip():
                problems.append("tax.label is required when a tax "
                                "is given — the tool never invents "
                                "a tax label")
                label = ""
            if not _is_number(rate):
                problems.append("tax.rate is required when a tax "
                                "is given — a fraction such as "
                                "0.05 for 5% (the tool never "
                                "invents a rate)")
                rate = 0
            elif not (0 < _dec(rate) <= 1):
                problems.append(f"tax.rate must be a fraction "
                                f"greater than 0 and at most 1 "
                                f"(got {rate!r})")
            tax = {"label": label.strip() if label else "",
                   "rate": rate}
    currency = data.get("currency", DEFAULT_CURRENCY)
    if not isinstance(currency, str) \
            or not _CURRENCY_RE.match(currency):
        problems.append(f"currency must be a 3-letter code such "
                        f"as 'CAD' (got {currency!r})")
        currency = DEFAULT_CURRENCY
    intro = _string_list(data.get("intro"), "intro", problems)
    scope = _string_list(data.get("scope"), "scope", problems)
    timeline = _string_list(data.get("timeline"), "timeline",
                            problems)
    terms = _string_list(data.get("terms"), "terms", problems)
    brief_date = _brief_date(data.get("date"), "date", problems)
    valid_until = _brief_date(data.get("valid_until"),
                              "valid_until", problems)
    if data.get("date") is not None and brief_date is not None \
            and valid_until is not None \
            and valid_until < brief_date:
        problems.append(f"valid_until ({valid_until}) is before "
                        f"the proposal date ({brief_date}) — the "
                        f"offer would already be over on the day "
                        f"it is made")
    if problems:
        listing = "\n".join(f"  - {p}" for p in problems)
        raise ToolError(f"the brief has {len(problems)} "
                        f"problem(s) — nothing was written:\n"
                        f"{listing}")
    return {
        "business": business,
        "client": client,
        "project": project.strip(),
        "date": brief_date or date.today().isoformat(),
        "valid_until": valid_until,
        "currency": currency.upper(),
        "intro": intro,
        "scope": scope,
        "items": items,
        "tax": tax,
        "timeline": timeline,
        "terms": terms,
    }


# --------------------------------------------------------------------------
# the money — lines, subtotal, the brief's tax, total
# --------------------------------------------------------------------------

def compute_money(brief):
    """The proposal's arithmetic, from the brief and nothing
    else. Per line: amount = qty x unit_price rounded half-up to
    cents. Subtotal = the sum of the rounded line amounts. Tax
    (only when the brief supplies one) = subtotal x rate rounded
    half-up to cents. Total = subtotal + tax."""
    lines = []
    subtotal = Decimal("0")
    for item in brief["items"]:
        qty = _dec(item["qty"])
        price = _cents(_dec(item["unit_price"]))
        amount = _cents(qty * _dec(item["unit_price"]))
        subtotal += amount
        lines.append({"description": item["description"],
                      "qty": qty, "unit_price": price,
                      "amount": amount})
    tax = None
    if brief["tax"] is not None:
        rate = _dec(brief["tax"]["rate"])
        tax_amount = _cents(subtotal * rate)
        tax = {"label": brief["tax"]["label"], "rate": rate,
               "amount": tax_amount}
    total = subtotal + (tax["amount"] if tax else Decimal("0"))
    return {"lines": lines, "subtotal": subtotal, "tax": tax,
            "total": total, "currency": brief["currency"]}


# --------------------------------------------------------------------------
# rendering — HTML (escaped, self-contained, deterministic) + text
# --------------------------------------------------------------------------

def _esc(text):
    return html.escape(text, quote=True)


_CLEAN_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; color: #222;
  margin: 0; background: #f7f5f0; }
.page { max-width: 760px; margin: 0 auto; background: #fff;
  padding: 48px 56px; }
.kicker { font-size: 12px; letter-spacing: 3px; text-transform:
  uppercase; color: #8a7f5c; margin: 0 0 8px; }
h1 { font-size: 30px; line-height: 1.2; margin: 0 0 6px; }
h2 { font-size: 15px; letter-spacing: 2px; text-transform:
  uppercase; color: #8a7f5c; margin: 34px 0 10px;
  border-bottom: 1px solid #e3ddcd; padding-bottom: 6px; }
p { line-height: 1.6; margin: 0 0 12px; }
.meta { color: #555; font-size: 14px; line-height: 1.7;
  margin: 18px 0 4px; }
.meta strong { color: #222; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 4px; }
th { text-align: left; font-size: 12px; letter-spacing: 1px;
  text-transform: uppercase; color: #8a7f5c;
  border-bottom: 2px solid #222; padding: 6px 8px; }
td { padding: 8px; border-bottom: 1px solid #e9e4d6;
  vertical-align: top; }
td.n, th.n { text-align: right; white-space: nowrap; }
tr.total td { font-weight: bold; font-size: 17px;
  border-bottom: none; border-top: 2px solid #222; }
tr.sub td { color: #444; }
ul { line-height: 1.6; margin: 0 0 12px; padding-left: 20px; }
.sign { margin-top: 18px; line-height: 2.6; color: #444; }
.foot { margin-top: 44px; padding-top: 14px;
  border-top: 1px solid #e3ddcd; color: #777; font-size: 13px; }
"""

_BOLD_CSS = """
body { font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
  color: #1c2430; margin: 0; background: #e8ecf1; }
.page { max-width: 760px; margin: 0 auto; background: #fff;
  padding: 0 56px 48px; }
.band { background: #14263c; color: #fff; margin: 0 -56px;
  padding: 38px 56px 30px; }
.kicker { font-size: 12px; letter-spacing: 3px; text-transform:
  uppercase; color: #f0b429; margin: 0 0 8px; }
h1 { font-size: 32px; line-height: 1.15; margin: 0 0 6px; }
.band .meta { color: #c8d3e0; }
h2 { font-size: 15px; letter-spacing: 2px; text-transform:
  uppercase; color: #14263c; margin: 34px 0 10px;
  border-bottom: 3px solid #f0b429; padding-bottom: 6px; }
p { line-height: 1.6; margin: 0 0 12px; }
.meta { color: #465366; font-size: 14px; line-height: 1.7;
  margin: 18px 0 4px; }
.meta strong { color: inherit; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 4px; }
th { text-align: left; font-size: 12px; letter-spacing: 1px;
  text-transform: uppercase; color: #fff; background: #14263c;
  padding: 8px; }
td { padding: 8px; border-bottom: 1px solid #dbe1e8;
  vertical-align: top; }
td.n, th.n { text-align: right; white-space: nowrap; }
tr.total td { font-weight: bold; font-size: 17px;
  border-bottom: none; border-top: 3px solid #f0b429; }
tr.sub td { color: #444; }
ul { line-height: 1.6; margin: 0 0 12px; padding-left: 20px; }
.sign { margin-top: 18px; line-height: 2.6; color: #444; }
.foot { margin-top: 44px; padding-top: 14px;
  border-top: 1px solid #dbe1e8; color: #777; font-size: 13px; }
"""

_HTML_SKELETON = Template("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>$title</title>
<style>$css</style>
</head>
<body>
<div class="page">
$header
$body
</div>
</body>
</html>
""")


def _meta_lines(brief):
    """(label, value) pairs for the Prepared for/by block."""
    rows = [("Prepared for", brief["client"]["name"])]
    if brief["client"]["contact"]:
        rows.append(("Client contact", brief["client"]["contact"]))
    rows.append(("Prepared by", brief["business"]["name"]))
    if brief["business"]["contact"]:
        rows.append(("Contact", brief["business"]["contact"]))
    rows.append(("Date", brief["date"]))
    if brief["valid_until"]:
        rows.append(("Valid until", brief["valid_until"]))
    rows.append(("All amounts in", brief["currency"]))
    return rows


def _acceptance_text(brief):
    """The acceptance wording, built only from brief facts: who
    to contact, and — only if the brief sets one — the date the
    offer holds until. No deadline is ever invented."""
    contact = brief["business"]["contact"]
    if contact:
        text = (f"To accept this proposal, contact "
                f"{brief['business']['name']} at {contact}.")
    else:
        text = (f"To accept this proposal, contact "
                f"{brief['business']['name']}.")
    if brief["valid_until"]:
        text += (f" This proposal is valid until "
                 f"{brief['valid_until']}.")
    return text


def _totals_rows(money):
    rows = [("Subtotal", money["subtotal"])]
    if money["tax"] is not None:
        rows.append((money["tax"]["label"], money["tax"]["amount"]))
    rows.append((f"Total ({money['currency']})", money["total"]))
    return rows


def render_html(brief, money, template_name):
    """The proposal as ONE self-contained HTML file: inline CSS,
    no JavaScript, and no external reference of any kind — the
    renderer adds no links, images or fonts; the only way a URL
    could appear is a brief field printing one as (escaped)
    text. Every brief string is HTML-escaped."""
    cur = money["currency"]
    meta = "\n".join(
        f"<div><strong>{_esc(label)}:</strong> {_esc(value)}</div>"
        for label, value in _meta_lines(brief))
    header_inner = (
        f"<p class=\"kicker\">Proposal</p>\n"
        f"<h1>{_esc(brief['project'])}</h1>\n"
        f"<div class=\"meta\">\n{meta}\n</div>")
    if template_name == "bold":
        header = f"<div class=\"band\">\n{header_inner}\n</div>"
        css = _BOLD_CSS
    else:
        header = header_inner
        css = _CLEAN_CSS
    parts = []
    for para in brief["intro"]:
        for chunk in para.split("\n\n"):
            if chunk.strip():
                parts.append(f"<p>{_esc(chunk.strip())}</p>")
    if brief["scope"]:
        lis = "\n".join(f"<li>{_esc(s)}</li>"
                        for s in brief["scope"])
        parts.append(f"<h2>Scope</h2>\n<ul>\n{lis}\n</ul>")
    rows = []
    for line in money["lines"]:
        rows.append(
            f"<tr><td>{_esc(line['description'])}</td>"
            f"<td class=\"n\">{fmt_qty(line['qty'])}</td>"
            f"<td class=\"n\">{fmt_money(line['unit_price'], cur)}"
            f"</td>"
            f"<td class=\"n\">{fmt_money(line['amount'], cur)}</td>"
            f"</tr>")
    totals = _totals_rows(money)
    for label, amount in totals[:-1]:
        rows.append(
            f"<tr class=\"sub\"><td colspan=\"3\">{_esc(label)}"
            f"</td><td class=\"n\">{fmt_money(amount, cur)}</td>"
            f"</tr>")
    label, amount = totals[-1]
    rows.append(
        f"<tr class=\"total\"><td colspan=\"3\">{_esc(label)}</td>"
        f"<td class=\"n\">{fmt_money(amount, cur)}</td></tr>")
    parts.append(
        "<h2>The work, priced</h2>\n<table>\n"
        "<tr><th>Description</th><th class=\"n\">Qty</th>"
        "<th class=\"n\">Unit price</th>"
        "<th class=\"n\">Amount</th></tr>\n"
        + "\n".join(rows) + "\n</table>")
    for heading, key in (("Timeline", "timeline"),
                         ("Terms", "terms")):
        if brief[key]:
            lis = "\n".join(f"<li>{_esc(s)}</li>"
                            for s in brief[key])
            parts.append(f"<h2>{heading}</h2>\n<ul>\n{lis}\n</ul>")
    parts.append(
        f"<h2>Acceptance</h2>\n"
        f"<p>{_esc(_acceptance_text(brief))}</p>\n"
        f"<p class=\"sign\">Accepted for "
        f"{_esc(brief['client']['name'])}: "
        f"______________________________&nbsp;&nbsp;"
        f"Date: ______________</p>")
    foot = _esc(brief["business"]["name"])
    if brief["business"]["contact"]:
        foot += f" · {_esc(brief['business']['contact'])}"
    parts.append(f"<div class=\"foot\">{foot}</div>")
    return _HTML_SKELETON.substitute(
        title=_esc(f"Proposal — {brief['project']}"),
        css=css, header=header, body="\n".join(parts))


def _section_text(heading, lines, bullet="- "):
    if not lines:
        return []
    out = ["", heading, "-" * len(heading)]
    for line in lines:
        for chunk in line.split("\n\n"):
            if chunk.strip():
                out.append(f"{bullet}{chunk.strip()}"
                           if bullet else chunk.strip())
    return out


def render_text(brief, money):
    """The plain-text twin of the proposal: the same facts, the
    same numbers, no markup. Brief text is printed as-is."""
    cur = money["currency"]
    out = [brief["business"]["name"],
           f"PROPOSAL — {brief['project']}", ""]
    for label, value in _meta_lines(brief):
        out.append(f"{label}: {value}")
    for para in brief["intro"]:
        out.append("")
        for chunk in para.split("\n\n"):
            if chunk.strip():
                out.append(chunk.strip())
    out += _section_text("SCOPE", brief["scope"])
    out += ["", "THE WORK, PRICED", "----------------"]
    width = max(len(l["description"]) for l in money["lines"])
    for line in money["lines"]:
        out.append(
            f"{line['description']:<{width}}  "
            f"{fmt_qty(line['qty']):>5} x "
            f"{fmt_money(line['unit_price'], cur):>12}  "
            f"{fmt_money(line['amount'], cur):>12}")
    for label, amount in _totals_rows(money)[:-1]:
        out.append(f"{label:<{width}}  {'':>5}   "
                   f"{'':>12}  {fmt_money(amount, cur):>12}")
    label, amount = _totals_rows(money)[-1]
    out.append(f"{label:<{width}}  {'':>5}   {'':>12}  "
               f"{fmt_money(amount, cur):>12}")
    out += _section_text("TIMELINE", brief["timeline"])
    out += _section_text("TERMS", brief["terms"])
    out += ["", "ACCEPTANCE", "----------",
            _acceptance_text(brief), "",
            f"Accepted for {brief['client']['name']}: "
            f"______________________________   Date: ______________",
            ""]
    foot = brief["business"]["name"]
    if brief["business"]["contact"]:
        foot += f" · {brief['business']['contact']}"
    out.append(foot)
    return "\n".join(out) + "\n"


def money_as_json(money):
    return {
        "lines": [{"description": l["description"],
                   "qty": _num(l["qty"]),
                   "unit_price": _num(l["unit_price"]),
                   "amount": _num(l["amount"])}
                  for l in money["lines"]],
        "subtotal": _num(money["subtotal"]),
        "tax": ({"label": money["tax"]["label"],
                 "rate": _num(money["tax"]["rate"]),
                 "amount": _num(money["tax"]["amount"])}
                if money["tax"] is not None else None),
        "total": _num(money["total"]),
        "currency": money["currency"],
    }


# --------------------------------------------------------------------------
# the sent-log — load + validate + save (a corrupt log is never wiped)
# --------------------------------------------------------------------------

def _fail_log_entry(no, msg):
    raise ToolError(f"log entry {no}: {msg}")


def normalize_log_entry(raw, no):
    """Validate one raw log entry -> a clean entry dict."""
    if not isinstance(raw, dict):
        _fail_log_entry(no, f"expected an object of fields, got "
                            f"{raw!r}")
    entry_id = raw.get("id")
    if isinstance(entry_id, bool) or not isinstance(entry_id, int) \
            or entry_id < 1:
        _fail_log_entry(no, f"'id' must be a positive whole "
                            f"number (got {entry_id!r})")
    client = raw.get("client")
    if not isinstance(client, str) or not client.strip():
        _fail_log_entry(no, "'client' is required and must be a "
                            "non-empty string")
    project = raw.get("project")
    if not isinstance(project, str) or not project.strip():
        _fail_log_entry(no, "'project' is required and must be a "
                            "non-empty string")
    if "total" not in raw:
        _fail_log_entry(no, "missing required field 'total'")
    total = raw["total"]
    if not _is_number(total):
        _fail_log_entry(no, f"'total' must be a finite number "
                            f"(got {total!r})")
    if _dec(total) < 0:
        _fail_log_entry(no, f"'total' must be 0 or more "
                            f"(got {total!r})")
    currency = raw.get("currency", DEFAULT_CURRENCY)
    if not isinstance(currency, str) \
            or not _CURRENCY_RE.match(currency):
        _fail_log_entry(no, f"'currency' must be a 3-letter code "
                            f"(got {currency!r})")
    try:
        sent = parse_date(raw.get("sent"), "'sent'").isoformat()
    except ToolError as exc:
        _fail_log_entry(no, str(exc))
    proposal = raw.get("proposal", "")
    if not isinstance(proposal, str):
        _fail_log_entry(no, f"'proposal' must be a string (got "
                            f"{proposal!r})")
    return {"id": entry_id, "client": client.strip(),
            "project": project.strip(),
            "total": float(_cents(_dec(total))),
            "currency": currency.upper(), "sent": sent,
            "proposal": proposal}


def load_log(path, must_exist=True):
    """Read + validate the sent-log -> list of clean entries.
    Raises ToolError on anything wrong; the file is only ever
    READ here."""
    if not path.is_file():
        if must_exist:
            raise ToolError(f"sent-log not found: {path} — record "
                            f"a proposal first (`log add` "
                            f"creates the file)")
        return []
    data = load_json_file(path, "sent-log")
    if isinstance(data, dict):
        if "proposals" not in data:
            raise ToolError(f"sent-log {path.name}: a JSON object "
                            f"must hold the entries under a "
                            f"\"proposals\" key — the file was "
                            f"left untouched")
        data = data["proposals"]
    if not isinstance(data, list):
        raise ToolError(f"sent-log {path.name}: expected a JSON "
                        f"list of proposals (or an object with "
                        f"\"proposals\") — the file was left "
                        f"untouched")
    entries = [normalize_log_entry(raw, i + 1)
               for i, raw in enumerate(data)]
    seen = set()
    for e in entries:
        if e["id"] in seen:
            raise ToolError(f"sent-log {path.name}: duplicate id "
                            f"{e['id']} — ids must be unique; "
                            f"the file was left untouched")
        seen.add(e["id"])
    return entries


def save_log(path, entries):
    """Write the log atomically (temp file in the same folder,
    then replace) so a crash mid-write can never leave half a
    log."""
    payload = {"proposals": entries}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        raise ToolError(f"could not write sent-log {path} "
                        f"({exc.__class__.__name__}: {exc})")


def log_totals(entries):
    """Totals GROUPED BY CURRENCY — a CAD total and a USD total
    are never added together into a number that means nothing."""
    totals = {}
    for e in entries:
        bucket = totals.setdefault(
            e["currency"], {"count": 0, "amount": Decimal("0")})
        bucket["count"] += 1
        bucket["amount"] += _dec(e["total"])
    return totals


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

class _JsonAwareParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage errors as JSON in
    --json mode ({"error": ...} on stdout, same exit code 2) —
    an agent driving this tool with --json never gets plain
    text or a traceback. The flag lives on the class so
    subparsers share it."""

    json_mode = False

    def error(self, message):
        if self.json_mode:
            print(json.dumps({"error": message}))
            self.exit(2)
        super().error(message)


def _json_arg(p):
    p.add_argument("--json", action="store_true",
                   help="print one JSON object instead of text")


def cmd_make(a):
    brief_path = Path(a.brief)
    template_name = a.template
    if template_name not in TEMPLATES:
        raise ToolError(f"unknown template {template_name!r} — "
                        f"available templates: "
                        f"{', '.join(TEMPLATES)}")
    data = load_json_file(brief_path, "brief")
    brief = validate_brief(data)      # raises before any write
    money = compute_money(brief)
    html_text = render_html(brief, money, template_name)
    text_text = render_text(brief, money)
    out_dir = Path(a.out)
    if out_dir.exists() and not out_dir.is_dir():
        raise ToolError(f"--out {a.out} exists and is not a "
                        f"folder — nothing was written")
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / "proposal.html"
        txt_path = out_dir / "proposal.txt"
        html_path.write_text(html_text, encoding="utf-8")
        txt_path.write_text(text_text, encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"could not write into {a.out} "
                        f"({exc.__class__.__name__}: {exc})")
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "make", "brief": brief_path.name,
            "template": template_name,
            "out_dir": str(out_dir),
            "files": [str(html_path), str(txt_path)],
            "business": brief["business"]["name"],
            "client": brief["client"]["name"],
            "project": brief["project"],
            "date": brief["date"],
            "valid_until": brief["valid_until"],
            "money": money_as_json(money),
        }, indent=2))
    else:
        print(f"Wrote {html_path} and {txt_path}")
        print(f"  {brief['project']} — for "
              f"{brief['client']['name']} from "
              f"{brief['business']['name']}")
        print(f"  Template: {template_name} · Date: "
              f"{brief['date']}"
              + (f" · Valid until: {brief['valid_until']}"
                 if brief["valid_until"] else ""))
        total_line = fmt_money(money["total"], money["currency"])
        print(f"  Total: {total_line} "
              f"({len(money['lines'])} line item(s), all amounts "
              f"in {money['currency']})")
        print("  proposal-forge generated the document only — "
              "send it yourself; nothing was sent or tracked.")
    return 0


def cmd_log_add(a):
    path = Path(a.file)
    entries = load_log(path, must_exist=False)
    client = a.client.strip()
    if not client:
        raise ToolError("--client must be a non-empty string")
    project = a.project.strip()
    if not project:
        raise ToolError("--project must be a non-empty string")
    if not _is_number(a.total):
        raise ToolError(f"--total must be a finite number "
                        f"(got {a.total!r})")
    total = _cents(_dec(a.total))
    if total < 0:
        raise ToolError(f"--total must be 0 or more "
                        f"(got {a.total!r})")
    if not _CURRENCY_RE.match(a.currency or ""):
        raise ToolError(f"--currency must be a 3-letter code "
                        f"(got {a.currency!r})")
    currency = a.currency.upper()
    sent = (parse_date(a.sent, "--sent").isoformat() if a.sent
            else date.today().isoformat())
    for e in entries:
        if e["client"].casefold() == client.casefold() \
                and e["project"].casefold() == project.casefold() \
                and e["sent"] == sent:
            if not a.force:
                raise ToolError(
                    f"already recorded: {e['client']} — "
                    f"{e['project']} — sent {sent} is log entry "
                    f"#{e['id']}. Recording it twice would count "
                    f"the proposal twice; pass --force if this "
                    f"really was a second send on the same day.")
    entry = {"id": max((e["id"] for e in entries), default=0) + 1,
             "client": client, "project": project,
             "total": float(total), "currency": currency,
             "sent": sent, "proposal": a.proposal or ""}
    entries.append(entry)
    save_log(path, entries)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "log add", "file": path.name,
            "entry": entry,
            "entries": len(entries),
        }, indent=2))
    else:
        print(f"Recorded proposal #{entry['id']}: {client} — "
              f"{project} — "
              f"{fmt_money(total, currency)} — sent {sent}")
        print(f"Sent-log: {path.name} ({len(entries)} "
              f"proposal(s))")
    return 0


def cmd_log_list(a):
    path = Path(a.file)
    entries = load_log(path)
    ordered = sorted(entries, key=lambda e: (e["sent"], e["id"]))
    totals = log_totals(entries)
    if a.json:
        print(json.dumps({
            "tool": TOOL, "version": __version__,
            "command": "log list", "file": path.name,
            "proposals": ordered,
            "totals": {cur: {"count": t["count"],
                             "amount": _num(t["amount"])}
                       for cur, t in sorted(totals.items())},
        }, indent=2))
    else:
        lines = [f"proposal-forge v{__version__} — log list · "
                 f"file {path.name}", ""]
        if not ordered:
            lines.append("No proposals recorded yet — add one "
                         "with `log add`.")
        for e in ordered:
            line = (f"#{e['id']} · {e['sent']} · {e['client']} — "
                    f"{e['project']} — "
                    f"{fmt_money(_dec(e['total']), e['currency'])}")
            if e["proposal"]:
                line += f" · file: {e['proposal']}"
            lines.append(line)
        if ordered:
            lines.append("")
            parts = [f"{cur} "
                     f"{fmt_money(t['amount'], cur)} "
                     f"({t['count']})"
                     for cur, t in sorted(totals.items())]
            lines.append("Totals by currency: "
                         + " · ".join(parts))
            lines.append("Totals are kept per currency — they "
                         "are never blended into one number.")
        print("\n".join(lines))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    _JsonAwareParser.json_mode = "--json" in argv
    ap = _JsonAwareParser(
        prog=TOOL,
        description="Turn a brief into a self-contained HTML "
                    "proposal (+ plain-text twin) and keep a "
                    "local log of what you sent (stdlib only, "
                    "local only, never sends anything).")
    sub = ap.add_subparsers(dest="command", required=True,
                            parser_class=_JsonAwareParser)

    p_make = sub.add_parser(
        "make", help="render proposal.html + proposal.txt from "
                     "a brief (validates first; a bad brief "
                     "writes nothing)")
    p_make.add_argument("--brief", required=True,
                        help="the brief JSON file")
    p_make.add_argument("--out", required=True,
                        help="folder to write proposal.html and "
                             "proposal.txt into (created if "
                             "missing)")
    p_make.add_argument("--template", default=DEFAULT_TEMPLATE,
                        help="built-in look: clean (default) or "
                             "bold")
    _json_arg(p_make)
    p_make.set_defaults(func=cmd_make)

    p_log = sub.add_parser(
        "log", help="the sent-log: record proposals you sent "
                    "and list them with per-currency totals")
    p_log.add_argument("--file", default="sent-log.json",
                       help="sent-log file (default: "
                            "sent-log.json in the current "
                            "folder; created by the first add)")
    log_sub = p_log.add_subparsers(dest="log_command",
                                   required=True,
                                   parser_class=_JsonAwareParser)

    p_ladd = log_sub.add_parser(
        "add", help="record a proposal you sent (the tool "
                    "itself never sends)")
    p_ladd.add_argument("--client", required=True,
                        help="who the proposal went to")
    p_ladd.add_argument("--project", required=True,
                        help="the proposal's project title")
    p_ladd.add_argument("--total", type=float, required=True,
                        help="the proposal's total, in its "
                             "currency (>= 0)")
    p_ladd.add_argument("--sent", default=None,
                        help="date sent, YYYY-MM-DD (default: "
                             "today)")
    p_ladd.add_argument("--currency", default=DEFAULT_CURRENCY,
                        help="3-letter currency code for the "
                             "total (default: CAD)")
    p_ladd.add_argument("--proposal", default="",
                        help="path of the proposal file you "
                             "sent (recorded, never opened)")
    p_ladd.add_argument("--force", action="store_true",
                        help="record even if the same client + "
                             "project + date is already logged")
    _json_arg(p_ladd)
    p_ladd.set_defaults(func=cmd_log_add)

    p_llist = log_sub.add_parser(
        "list", help="every recorded proposal, with totals "
                     "grouped by currency")
    _json_arg(p_llist)
    p_llist.set_defaults(func=cmd_log_list)

    a = ap.parse_args(argv)

    def fail(msg):
        if getattr(a, "json", False):
            print(json.dumps({"error": msg}))
        else:
            print(f"ERROR: {msg}")
        return 2

    try:
        return a.func(a)
    except ToolError as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
