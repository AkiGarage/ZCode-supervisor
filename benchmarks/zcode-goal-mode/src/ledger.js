export function summarizeLedger(entries) {
  const summary = {
    count: entries.length,
    income: 0,
    expense: 0,
    net: 0
  };

  for (const entry of entries) {
    if (entry.type === "income") {
      summary.income += entry.amount;
    } else if (entry.type === "expense") {
      summary.expense += entry.amount;
    }
  }

  summary.net = summary.income - summary.expense;
  return summary;
}

