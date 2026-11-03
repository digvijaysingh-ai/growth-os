// Decision deck state: which visitor choices map to a measured simulation, and what the panel shows for each.
// Pure functions, no DOM; the console and tests/deck.test.mjs both load this file.
//
//   state: { <decision id>: true (approved) | false (rejected) }   all 12 ids, approved = the AI's plan
//   Only priced decisions (those with a simulated effect) decide the family; the unpriced two never change it.
//
//   family   priced decisions approved     numbers come from                 compared with the AI's
//   all      every one                     the all-approved run (measured)   all-approved run
//   none     none                          €0 by definition                  all-approved run
//   loo      all but one                   that leave-one-out run (measured) all-approved run
//   single   exactly one                   that decision's own run (measured) all-approved run
//   approx   any other mix                 sum of single runs (≈)            sum of single runs (≈)
globalThis.GosDeck = (function () {
  var KEYS = ["revenue", "spend", "gross_profit"];

  function zero() { return { revenue: 0, spend: 0, gross_profit: 0 }; }

  function add(a, b) { var o = {}; KEYS.forEach(function (k) { o[k] = a[k] + b[k]; }); return o; }

  function sub(a, b) { var o = {}; KEYS.forEach(function (k) { o[k] = a[k] - b[k]; }); return o; }

  function aiPlan(deck) {
    var s = {};
    deck.cards.forEach(function (c) { s[c.id] = true; });
    return s;
  }

  function classify(deck, state) {
    var on = deck.priced.filter(function (id) { return state[id] !== false; });
    var n = on.length, all = deck.priced.length;
    if (n === all) return { family: "all" };
    if (n === 0) return { family: "none" };
    if (n === all - 1) return { family: "loo", left: deck.priced.filter(function (id) { return state[id] === false; })[0] };
    if (n === 1) return { family: "single", id: on[0] };
    return { family: "approx" };
  }

  function alone(deck, id) {
    for (var i = 0; i < deck.cards.length; i++) if (deck.cards[i].id === id) return deck.cards[i].alone;
    return null;
  }

  // Everything the panel needs for a state: the change against the as-is quarter, the basis it is compared on, the
  // contribution of each approved priced decision, and the measured interaction between them (measured states only).
  function totals(deck, state) {
    var c = classify(deck, state), change, measured = true, ai = deck.all;
    var bars = deck.priced.filter(function (id) { return state[id] !== false; }).map(function (id) { return { id: id, change: alone(deck, id) }; });
    if (c.family === "all") change = deck.all;
    else if (c.family === "none") change = zero();
    else if (c.family === "loo") change = deck.leave_one_out[String(c.left)];
    else if (c.family === "single") change = alone(deck, c.id);
    else { measured = false; ai = deck.sum_singles; change = bars.reduce(function (s, b) { return add(s, b.change); }, zero()); }
    var summed = bars.reduce(function (s, b) { return add(s, b.change); }, zero());
    var interaction = measured && c.family !== "none" ? sub(change, summed) : null;
    var after = add(deck.as_is, change);
    return {
      family: c.family, left: c.left, measured: measured, change: change, bars: bars, interaction: interaction,
      vs_ai: change.gross_profit - ai.gross_profit, ai: ai,
      mer_before: deck.as_is.revenue / deck.as_is.spend, mer_after: after.revenue / after.spend,
      approved_priced: bars.length, approved_unpriced: deck.cards.filter(function (k) { return !k.priced && state[k.id] !== false; }).length,
    };
  }

  // "You beat the AI here": only on the one card the visitor rejected, only when its measured leave-one-out run beats
  // the all-approved run by more than the build's materiality threshold (deck.beat_the_ai lists those ids).
  function beat(deck, state, id) {
    var c = classify(deck, state);
    if (c.family !== "loo" || c.left !== id || deck.beat_the_ai.indexOf(id) < 0) return null;
    return deck.leave_one_out[String(id)].gross_profit - deck.all.gross_profit;
  }

  return { classify: classify, totals: totals, beat: beat, aiPlan: aiPlan };
})();
