#!/usr/bin/env python3
"""Tests for proposal-forge. Stdlib unittest only.

Run from the pack root:
    python3 -m unittest discover -s tests -v

All money expectations are worked by hand here — never copied
from the tool's own output. The sample brief
(examples/sample-brief.json), by hand:
    Discovery and sitemap          1   x   600.00 =   600.00
    Design — homepage + templates  1   x 1,450.00 = 1,450.00
    Page build                     6   x   275.50 = 1,653.00
    Copy polish                    6   x    85.25 =   511.50
    Booking setup                  1   x   420.00 =   420.00
    Training session               2.5 x    95.00 =   237.50
    Subtotal                                        4,872.00
    GST (5%)                 4,872.00 x 0.05      =   243.60
    TOTAL (CAD)                                     5,115.60
Rounding pins (Decimal, half-up — computed by hand):
    3 x 0.335 = 1.005 -> 1.01 (the line rounds half-up)
    1 x 2.675 = 2.675 -> 2.68 (a float would give 2.67)
    tax on 199.99 at 0.05 = 9.9995 -> 10.00, total 209.99
The sample sent-log, by hand: 1,890.00 + 5,115.60 = CAD
7,005.60 across 2 proposals.
Both directions are covered: good briefs render (exit 0), bad
briefs fail cleanly (exit 2, nothing written, the brief file
byte-identical), duplicates are refused, and a corrupt log is
left untouched.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[1]
SRC = PACK_ROOT / "src" / "proposal_forge.py"
EXAMPLES = PACK_ROOT / "examples"
sys.path.insert(0, str(PACK_ROOT / "src"))

import proposal_forge as pf  # noqa: E402

D = Decimal


def brief(**over):
    base = {
        "business": {"name": "Test Studio",
                     "contact": "hi@test.example"},
        "client": {"name": "Test Client", "contact": ""},
        "project": "Test project",
        "date": "2026-11-04",
        "items": [{"description": "Work", "qty": 1,
                   "unit_price": 100}],
    }
    base.update(over)
    return pf.validate_brief(base)


def run_cli(*args):
    return subprocess.run(
        [sys.executable, str(SRC), *args],
        capture_output=True, text=True, timeout=60)


class TestMoney(unittest.TestCase):

    def test_sample_brief_totals_by_hand(self):
        data = json.loads(
            (EXAMPLES / "sample-brief.json").read_text(
                encoding="utf-8"))
        money = pf.compute_money(pf.validate_brief(data))
        amounts = [l["amount"] for l in money["lines"]]
        self.assertEqual(amounts, [D("600.00"), D("1450.00"),
                                   D("1653.00"), D("511.50"),
                                   D("420.00"), D("237.50")])
        self.assertEqual(money["subtotal"], D("4872.00"))
        self.assertEqual(money["tax"]["amount"], D("243.60"))
        self.assertEqual(money["total"], D("5115.60"))
        self.assertEqual(money["currency"], "CAD")

    def test_qty_multiplication_and_fractional_qty(self):
        b = brief(items=[{"description": "Pages", "qty": 6,
                          "unit_price": 275.50},
                         {"description": "Hours", "qty": 2.5,
                          "unit_price": 95}])
        money = pf.compute_money(b)
        self.assertEqual(money["lines"][0]["amount"],
                         D("1653.00"))
        self.assertEqual(money["lines"][1]["amount"], D("237.50"))

    def test_line_rounding_is_half_up_decimal(self):
        b = brief(items=[{"description": "A", "qty": 3,
                          "unit_price": 0.335},
                         {"description": "B", "qty": 1,
                          "unit_price": 2.675}])
        money = pf.compute_money(b)
        self.assertEqual(money["lines"][0]["amount"], D("1.01"))
        self.assertEqual(money["lines"][1]["amount"], D("2.68"))
        self.assertEqual(money["subtotal"], D("3.69"))

    def test_tax_rounding_and_total(self):
        b = brief(items=[{"description": "Work", "qty": 1,
                          "unit_price": 199.99}],
                  tax={"label": "GST (5%)", "rate": 0.05})
        money = pf.compute_money(b)
        self.assertEqual(money["tax"]["amount"], D("10.00"))
        self.assertEqual(money["total"], D("209.99"))

    def test_no_tax_means_total_is_subtotal(self):
        money = pf.compute_money(brief())
        self.assertIsNone(money["tax"])
        self.assertEqual(money["total"], D("100.00"))

    def test_zero_price_line_is_allowed(self):
        b = brief(items=[{"description": "Included tweak",
                          "qty": 2, "unit_price": 0}])
        money = pf.compute_money(b)
        self.assertEqual(money["total"], D("0.00"))

    def test_fmt_qty_and_money(self):
        self.assertEqual(pf.fmt_qty(D("6")), "6")
        self.assertEqual(pf.fmt_qty(D("2.5")), "2.5")
        self.assertEqual(pf.fmt_qty(D("0.25")), "0.25")
        self.assertEqual(pf.fmt_money(D("5115.60"), "CAD"),
                         "$5,115.60")
        self.assertEqual(pf.fmt_money(D("100"), "EUR"),
                         "€100.00")
        self.assertEqual(pf.fmt_money(D("100"), "CHF"),
                         "CHF 100.00")


class TestBriefValidation(unittest.TestCase):

    def problems_of(self, data):
        with self.assertRaises(pf.ToolError) as ctx:
            pf.validate_brief(data)
        return str(ctx.exception)

    def test_empty_brief_names_every_required_field(self):
        msg = self.problems_of({})
        for needle in ("business", "client", "project", "items"):
            self.assertIn(needle, msg)

    def test_root_must_be_an_object(self):
        self.problems_of([1, 2, 3])

    def test_item_problems_are_named_by_position(self):
        msg = self.problems_of({
            "business": {"name": "B"}, "client": {"name": "C"},
            "project": "P",
            "items": [{"description": "X"},
                      {"description": "Y", "qty": 0,
                       "unit_price": -5}]})
        self.assertIn("items[0].qty", msg)
        self.assertIn("items[0].unit_price", msg)
        self.assertIn("items[1].qty", msg)
        self.assertIn("items[1].unit_price", msg)

    def test_problems_are_collected_not_first_only(self):
        msg = self.problems_of({"items": []})
        self.assertIn("project", msg)
        self.assertIn("items", msg)

    def test_tax_is_all_or_nothing(self):
        base = {"business": {"name": "B"},
                "client": {"name": "C"}, "project": "P",
                "items": [{"description": "X", "qty": 1,
                           "unit_price": 10}]}
        msg = self.problems_of({**base, "tax": {"label": "GST"}})
        self.assertIn("tax.rate", msg)
        msg = self.problems_of({**base, "tax": {"rate": 0.05}})
        self.assertIn("tax.label", msg)
        msg = self.problems_of(
            {**base, "tax": {"label": "GST", "rate": 5}})
        self.assertIn("tax.rate", msg)

    def test_bad_dates_and_currency(self):
        base = {"business": {"name": "B"},
                "client": {"name": "C"}, "project": "P",
                "items": [{"description": "X", "qty": 1,
                           "unit_price": 10}]}
        self.assertIn("valid_until", self.problems_of(
            {**base, "valid_until": "2026-13-40"}))
        self.assertIn("'date'", self.problems_of(
            {**base, "date": "Nov 4 2026"}))
        self.assertIn("currency", self.problems_of(
            {**base, "currency": "CADD"}))

    def test_lowercase_currency_is_normalised(self):
        b = brief(currency="usd")
        self.assertEqual(b["currency"], "USD")

    def test_valid_until_before_the_proposal_date_is_a_problem(
            self):
        msg = self.problems_of({
            "business": {"name": "B"}, "client": {"name": "C"},
            "project": "P", "date": "2026-11-04",
            "valid_until": "2026-11-01",
            "items": [{"description": "X", "qty": 1,
                       "unit_price": 10}]})
        self.assertIn("valid_until", msg)

    def test_scope_item_must_be_a_string(self):
        msg = self.problems_of({
            "business": {"name": "B"}, "client": {"name": "C"},
            "project": "P", "scope": ["fine", 42],
            "items": [{"description": "X", "qty": 1,
                       "unit_price": 10}]})
        self.assertIn("scope[1]", msg)


class TestMakeCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_brief(self, data, name="brief.json"):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def sample_data(self):
        return json.loads(
            (EXAMPLES / "sample-brief.json").read_text(
                encoding="utf-8"))

    def test_make_sample_writes_both_files(self):
        out = self.root / "out"
        res = run_cli("make", "--brief",
                      str(EXAMPLES / "sample-brief.json"),
                      "--out", str(out))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("$5,115.60", res.stdout)
        html_text = (out / "proposal.html").read_text(
            encoding="utf-8")
        txt = (out / "proposal.txt").read_text(encoding="utf-8")
        for needle in ("$1,653.00", "$511.50", "$237.50",
                       "$4,872.00", "$243.60", "$5,115.60"):
            self.assertIn(needle, html_text)
            self.assertIn(needle, txt)
        self.assertIn("New website for Delgado Family Dental",
                      html_text)

    def test_rendering_is_deterministic_both_templates(self):
        for template in ("clean", "bold"):
            rendered = []
            for i in (1, 2):
                out = self.root / f"out-{template}-{i}"
                res = run_cli("make", "--brief",
                              str(EXAMPLES / "sample-brief.json"),
                              "--out", str(out),
                              "--template", template)
                self.assertEqual(res.returncode, 0)
                rendered.append((
                    (out / "proposal.html").read_bytes(),
                    (out / "proposal.txt").read_bytes()))
            self.assertEqual(rendered[0], rendered[1],
                             f"{template} is not deterministic")

    def test_templates_differ_but_carry_the_same_numbers(self):
        outs = {}
        for template in ("clean", "bold"):
            out = self.root / template
            run_cli("make", "--brief",
                    str(EXAMPLES / "sample-brief.json"),
                    "--out", str(out), "--template", template)
            outs[template] = (out / "proposal.html").read_text(
                encoding="utf-8")
        self.assertNotEqual(outs["clean"], outs["bold"])
        for text in outs.values():
            self.assertIn("$5,115.60", text)

    def test_unknown_template_lists_available_and_writes_nothing(
            self):
        out = self.root / "nope"
        res = run_cli("make", "--brief",
                      str(EXAMPLES / "sample-brief.json"),
                      "--out", str(out), "--template", "fancy")
        self.assertEqual(res.returncode, 2)
        self.assertIn("clean", res.stdout)
        self.assertIn("bold", res.stdout)
        self.assertFalse(out.exists())

    def test_bad_brief_writes_nothing_and_names_all_fields(self):
        bad = self.write_brief({})
        out = self.root / "never"
        res = run_cli("make", "--brief", str(bad), "--out",
                      str(out))
        self.assertEqual(res.returncode, 2)
        for needle in ("business", "client", "project", "items"):
            self.assertIn(needle, res.stdout)
        self.assertFalse(out.exists())
        self.assertNotIn("Traceback", res.stdout + res.stderr)

    def test_corrupt_brief_is_clean_and_file_untouched(self):
        bad = self.root / "broken.json"
        bad.write_text("{not json", encoding="utf-8")
        before = bad.read_bytes()
        res = run_cli("make", "--brief", str(bad), "--out",
                      str(self.root / "o"))
        self.assertEqual(res.returncode, 2)
        self.assertNotIn("Traceback", res.stdout + res.stderr)
        self.assertEqual(bad.read_bytes(), before)

    def test_missing_brief_file_is_a_clean_error(self):
        res = run_cli("make", "--brief",
                      str(self.root / "ghost.json"), "--out",
                      str(self.root / "o"))
        self.assertEqual(res.returncode, 2)
        self.assertNotIn("Traceback", res.stdout + res.stderr)

    def test_out_path_that_is_a_file_is_a_clean_error(self):
        blocker = self.root / "afile"
        blocker.write_text("x", encoding="utf-8")
        res = run_cli("make", "--brief",
                      str(EXAMPLES / "sample-brief.json"),
                      "--out", str(blocker))
        self.assertEqual(res.returncode, 2)

    def test_make_json_is_one_object_with_the_money(self):
        out = self.root / "j"
        res = run_cli("make", "--brief",
                      str(EXAMPLES / "sample-brief.json"),
                      "--out", str(out), "--json")
        self.assertEqual(res.returncode, 0)
        obj = json.loads(res.stdout)
        self.assertEqual(obj["command"], "make")
        self.assertEqual(obj["money"]["subtotal"], 4872)
        self.assertEqual(obj["money"]["tax"]["amount"], 243.6)
        self.assertEqual(obj["money"]["total"], 5115.6)
        self.assertEqual(len(obj["files"]), 2)
        self.assertEqual(obj["valid_until"], "2026-12-04")

    def test_json_mode_errors_are_json(self):
        res = run_cli("make", "--brief",
                      str(EXAMPLES / "sample-brief.json"),
                      "--out", str(self.root / "o"),
                      "--template", "fancy", "--json")
        self.assertEqual(res.returncode, 2)
        self.assertIn("error", json.loads(res.stdout))

    def test_argparse_error_in_json_mode_is_json(self):
        res = run_cli("make", "--json")
        self.assertEqual(res.returncode, 2)
        self.assertIn("error", json.loads(res.stdout))

    def test_no_tax_brief_renders_no_tax_row(self):
        data = self.sample_data()
        del data["tax"]
        path = self.write_brief(data)
        out = self.root / "notax"
        res = run_cli("make", "--brief", str(path), "--out",
                      str(out))
        self.assertEqual(res.returncode, 0)
        html_text = (out / "proposal.html").read_text(
            encoding="utf-8")
        self.assertNotIn("GST", html_text)
        self.assertIn("Total (CAD)", html_text)
        self.assertIn("$4,872.00", html_text)

    def test_no_valid_until_means_no_deadline_anywhere(self):
        data = self.sample_data()
        del data["valid_until"]
        path = self.write_brief(data)
        out = self.root / "nodate"
        run_cli("make", "--brief", str(path), "--out", str(out))
        for name in ("proposal.html", "proposal.txt"):
            text = (out / name).read_text(encoding="utf-8")
            self.assertNotIn("Valid until", text)
            self.assertNotIn("valid until", text)

    def test_brief_text_is_escaped_in_html_raw_in_text(self):
        data = self.sample_data()
        data["client"] = {
            "name": "<script>alert(1)</script>",
            "contact": 'A & B "quoted"'}
        path = self.write_brief(data)
        out = self.root / "esc"
        res = run_cli("make", "--brief", str(path), "--out",
                      str(out))
        self.assertEqual(res.returncode, 0)
        html_text = (out / "proposal.html").read_text(
            encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",
                      html_text)
        self.assertNotIn("<script>alert", html_text)
        self.assertIn("A &amp; B &quot;quoted&quot;", html_text)
        txt = (out / "proposal.txt").read_text(encoding="utf-8")
        self.assertIn("<script>alert(1)</script>", txt)

    def test_rendered_html_has_no_external_references(self):
        out = self.root / "clean-room"
        run_cli("make", "--brief",
                str(EXAMPLES / "sample-brief.json"), "--out",
                str(out))
        html_text = (out / "proposal.html").read_text(
            encoding="utf-8")
        for banned in ("http://", "https://", "<script", "<img",
                       "<link", "url(", "@import", "src="):
            self.assertNotIn(banned, html_text)

    def test_acceptance_uses_brief_contact_only(self):
        out = self.root / "acc"
        run_cli("make", "--brief",
                str(EXAMPLES / "sample-brief.json"), "--out",
                str(out))
        txt = (out / "proposal.txt").read_text(encoding="utf-8")
        self.assertIn("contact Harbour & Pine Web Studio at "
                      "hello@harbourpine.example", txt)
        self.assertIn("valid until 2026-12-04", txt)
        data = self.sample_data()
        data["business"] = {"name": "Solo Studio"}
        path = self.write_brief(data, "nocontact.json")
        out2 = self.root / "acc2"
        run_cli("make", "--brief", str(path), "--out", str(out2))
        txt2 = (out2 / "proposal.txt").read_text(encoding="utf-8")
        self.assertIn("contact Solo Studio.", txt2)


class TestLogCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "sent.json"

    def add(self, *extra, client="Delgado Family Dental",
            project="New website", total="5115.60",
            sent="2026-11-04"):
        return run_cli("log", "--file", str(self.log), "add",
                       "--client", client, "--project", project,
                       "--total", total, "--sent", sent, *extra)

    def test_add_creates_the_log_and_list_shows_it(self):
        res = self.add()
        self.assertEqual(res.returncode, 0, res.stdout)
        data = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(len(data["proposals"]), 1)
        entry = data["proposals"][0]
        self.assertEqual(entry["id"], 1)
        self.assertEqual(entry["total"], 5115.6)
        self.assertEqual(entry["currency"], "CAD")
        res = run_cli("log", "--file", str(self.log), "list")
        self.assertEqual(res.returncode, 0)
        self.assertIn("$5,115.60", res.stdout)

    def test_sent_defaults_to_today(self):
        res = run_cli("log", "--file", str(self.log), "add",
                      "--client", "C", "--project", "P",
                      "--total", "10")
        self.assertEqual(res.returncode, 0)
        data = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(data["proposals"][0]["sent"],
                         date.today().isoformat())

    def test_duplicate_is_refused_and_file_unchanged(self):
        self.assertEqual(self.add().returncode, 0)
        before = self.log.read_bytes()
        res = self.add()
        self.assertEqual(res.returncode, 2)
        self.assertIn("--force", res.stdout)
        self.assertEqual(self.log.read_bytes(), before)

    def test_duplicate_matching_is_case_insensitive(self):
        self.add()
        res = self.add(client="delgado family dental",
                       project="NEW WEBSITE")
        self.assertEqual(res.returncode, 2)

    def test_force_records_the_second_send(self):
        self.add()
        res = self.add("--force")
        self.assertEqual(res.returncode, 0)
        data = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual([e["id"] for e in data["proposals"]],
                         [1, 2])

    def test_same_client_project_another_day_is_not_a_duplicate(
            self):
        self.add()
        res = self.add(sent="2026-11-05")
        self.assertEqual(res.returncode, 0)

    def test_ids_are_never_reused(self):
        self.log.write_text(json.dumps({"proposals": [
            {"id": 3, "client": "A", "project": "P",
             "total": 10, "currency": "CAD",
             "sent": "2026-01-01", "proposal": ""}]}),
            encoding="utf-8")
        res = self.add(client="B")
        self.assertEqual(res.returncode, 0)
        data = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(data["proposals"][-1]["id"], 4)

    def test_corrupt_log_errors_cleanly_and_is_never_wiped(self):
        self.log.write_text("{oops", encoding="utf-8")
        before = self.log.read_bytes()
        for args in (("list",), ("add", "--client", "C",
                                 "--project", "P", "--total",
                                 "10")):
            res = run_cli("log", "--file", str(self.log), *args)
            self.assertEqual(res.returncode, 2)
            self.assertNotIn("Traceback",
                             res.stdout + res.stderr)
        self.assertEqual(self.log.read_bytes(), before)

    def test_log_with_wrong_root_is_a_clean_error(self):
        self.log.write_text(json.dumps({"entries": []}),
                            encoding="utf-8")
        res = run_cli("log", "--file", str(self.log), "list")
        self.assertEqual(res.returncode, 2)
        self.assertIn("proposals", res.stdout)

    def test_log_entry_missing_total_names_the_entry(self):
        self.log.write_text(json.dumps({"proposals": [
            {"id": 1, "client": "A", "project": "P",
             "sent": "2026-01-01"}]}), encoding="utf-8")
        res = run_cli("log", "--file", str(self.log), "list")
        self.assertEqual(res.returncode, 2)
        self.assertIn("log entry 1", res.stdout)
        self.assertIn("total", res.stdout)

    def test_list_on_missing_log_is_a_clean_error(self):
        res = run_cli("log", "--file", str(self.log), "list")
        self.assertEqual(res.returncode, 2)
        self.assertIn("not found", res.stdout)

    def test_bad_add_inputs_are_clean_errors(self):
        self.assertEqual(self.add(total="-1").returncode, 2)
        self.assertEqual(self.add(sent="2026-02-30").returncode, 2)
        res = run_cli("log", "--file", str(self.log), "add",
                      "--client", "C", "--project", "P",
                      "--total", "10", "--currency", "CADD")
        self.assertEqual(res.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_totals_are_grouped_by_currency_never_blended(self):
        self.add(client="A", project="P1", total="100")
        self.add(client="B", project="P2", total="25")
        run_cli("log", "--file", str(self.log), "add",
                "--client", "C", "--project", "P3",
                "--total", "50", "--currency", "usd",
                "--sent", "2026-11-04")
        res = run_cli("log", "--file", str(self.log), "list")
        self.assertEqual(res.returncode, 0)
        self.assertIn("CAD $125.00 (2)", res.stdout)
        self.assertIn("USD $50.00 (1)", res.stdout)
        res = run_cli("log", "--file", str(self.log), "list",
                      "--json")
        obj = json.loads(res.stdout)
        self.assertEqual(obj["totals"]["CAD"]["amount"], 125)
        self.assertEqual(obj["totals"]["USD"]["amount"], 50)
        self.assertEqual(
            [p["client"] for p in obj["proposals"]],
            ["A", "B", "C"])

    def test_sample_sent_log_matches_hand_totals(self):
        res = run_cli("log", "--file",
                      str(EXAMPLES / "sample-sent-log.json"),
                      "list")
        self.assertEqual(res.returncode, 0)
        self.assertIn("CAD $7,005.60 (2)", res.stdout)
        self.assertIn("Okanagan Trail Outfitters", res.stdout)


if __name__ == "__main__":
    unittest.main()
