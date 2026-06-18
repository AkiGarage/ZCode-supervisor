import assert from "node:assert/strict";
import { test } from "node:test";

import { summarizeLedger } from "../src/ledger.js";

test("summarizeLedger separates income and expenses", () => {
  const result = summarizeLedger([
    { type: "income", amount: 1200 },
    { type: "expense", amount: 350 },
    { type: "income", amount: 200 },
    { type: "expense", amount: 50 }
  ]);

  assert.deepEqual(result, {
    count: 4,
    income: 1400,
    expense: 400,
    net: 1000
  });
});

test("summarizeLedger ignores unknown entry types", () => {
  const result = summarizeLedger([
    { type: "income", amount: 100 },
    { type: "transfer", amount: 999 },
    { type: "expense", amount: 30 }
  ]);

  assert.deepEqual(result, {
    count: 3,
    income: 100,
    expense: 30,
    net: 70
  });
});

test("summarizeLedger handles an empty ledger", () => {
  assert.deepEqual(summarizeLedger([]), {
    count: 0,
    income: 0,
    expense: 0,
    net: 0
  });
});

