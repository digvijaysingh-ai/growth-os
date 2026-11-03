// Decision deck state (growth_os/console/deck.js): which choices map to a measured run, and what the panel compares.
// Run: node --test tests/deck.test.mjs   (pytest runs it through tests/test_deck_js.py)
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ctx = vm.createContext({});
vm.runInContext(readFileSync(new URL("../growth_os/console/deck.js", import.meta.url), "utf8"), ctx);
const { GosDeck } = ctx;

// Three priced decisions and one unpriced, with made-up but consistent numbers.
const g = (x) => ({ revenue: 2 * x, spend: x / 10, gross_profit: x });
const DECK = {
  cards: [
    { id: 1, priced: true, alone: g(100) },
    { id: 2, priced: true, alone: g(-20) },
    { id: 3, priced: true, alone: g(50) },
    { id: 4, priced: false, alone: null },
  ],
  priced: [1, 2, 3],
  as_is: { revenue: 10000, spend: 1000, gross_profit: 4000 },
  all: g(140), // singles sum to 130; 10 of interaction
  sum_singles: g(130),
  leave_one_out: { 1: g(35), 2: g(160), 3: g(85) },
  beat_the_ai: [2],
};
const st = (off = [], extra = {}) => Object.fromEntries([1, 2, 3, 4].map((id) => [id, !off.includes(id)]).concat(Object.entries(extra)));

test("the AI's plan is the measured all-approved run", () => {
  const t = GosDeck.totals(DECK, GosDeck.aiPlan(DECK));
  assert.equal(t.family, "all");
  assert.equal(t.measured, true);
  assert.equal(t.change.gross_profit, 140);
  assert.equal(t.vs_ai, 0);
  assert.equal(t.interaction.gross_profit, 10);
});

test("rejecting one priced decision reads its leave-one-out run", () => {
  for (const [id, want] of [[1, 35], [2, 160], [3, 85]]) {
    const t = GosDeck.totals(DECK, st([id]));
    assert.equal(t.family, "loo");
    assert.equal(t.left, id);
    assert.equal(t.change.gross_profit, want);
    assert.equal(t.vs_ai, want - 140);
  }
});

test("approving exactly one priced decision reads its own run, no interaction", () => {
  const t = GosDeck.totals(DECK, st([2, 3]));
  assert.equal(t.family, "single");
  assert.equal(t.change.gross_profit, 100);
  assert.equal(t.interaction.gross_profit, 0);
  assert.equal(t.vs_ai, 100 - 140);
});

test("rejecting all is the as-is quarter: zero change", () => {
  const t = GosDeck.totals(DECK, st([1, 2, 3, 4]));
  assert.equal(t.family, "none");
  assert.equal(t.change.gross_profit, 0);
  assert.equal(t.interaction, null);
});

test("unpriced decisions never change totals or the family", () => {
  const a = GosDeck.totals(DECK, st([]));
  const b = GosDeck.totals(DECK, st([4]));
  assert.equal(b.family, a.family);
  assert.deepEqual(b.change, a.change);
  assert.equal(b.approved_unpriced, 0);
  const c = GosDeck.totals(DECK, st([2, 4])); // measured state with the unpriced one also rejected
  assert.equal(c.family, "loo");
  assert.equal(c.change.gross_profit, 160);
});

test("any other mix is a sum of singles, compared with the AI's sum of singles", () => {
  const big = { ...DECK, cards: DECK.cards.concat([{ id: 5, priced: true, alone: g(7) }]), priced: [1, 2, 3, 5], all: g(147), sum_singles: g(137) };
  const t = GosDeck.totals(big, { 1: true, 2: false, 3: false, 4: true, 5: true });
  assert.equal(t.family, "approx");
  assert.equal(t.measured, false);
  assert.equal(t.change.gross_profit, 107);
  assert.equal(t.vs_ai, 107 - 137);
  assert.equal(t.interaction, null);
});

test("beat the AI only on the one rejected card the build flagged", () => {
  assert.equal(GosDeck.beat(DECK, st([2]), 2), 20);
  assert.equal(GosDeck.beat(DECK, st([1]), 1), null); // rejecting #1 loses money
  assert.equal(GosDeck.beat(DECK, st([2, 3]), 2), null); // not a measured leave-one-out state
  assert.equal(GosDeck.beat({ ...DECK, beat_the_ai: [] }, st([2]), 2), null); // under the materiality threshold
});

test("MER follows the totals", () => {
  const t = GosDeck.totals(DECK, GosDeck.aiPlan(DECK));
  assert.equal(t.mer_before, 10);
  assert.equal(t.mer_after, (10000 + 280) / (1000 + 14));
});
