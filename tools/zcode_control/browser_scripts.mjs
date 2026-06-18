export function usageSnapshotExpression() {
  return String.raw`(() => {
    const bodyText = document.body?.innerText || "";
    const parseHumanNumber = (raw, suffix) => {
      const numeric = Number(String(raw).replace(/,/g, ""));
      if (!Number.isFinite(numeric)) return null;
      const multiplier = suffix === "K" ? 1_000 : suffix === "M" ? 1_000_000 : suffix === "B" ? 1_000_000_000 : 1;
      return numeric * multiplier;
    };
    const lines = bodyText.split(/\n+/).map((line) => line.trim()).filter(Boolean);
    const relevant = lines.filter((line) =>
      /\b(token|tokens|quota|usage|remaining|used|coding plan|prompt pool|weekly|monthly|context|glm)\b/i.test(line),
    );
    const tokenCandidates = [];
    const quotaPercentCandidates = [];
    for (const line of relevant) {
      for (const match of line.matchAll(/([\d,.]+)\s*([KMB])?\s*(?:tokens?|token)\b/gi)) {
        const value = parseHumanNumber(match[1], match[2]?.toUpperCase());
        if (value !== null) tokenCandidates.push({ line, value });
      }
      for (const match of line.matchAll(/(\d+(?:\.\d+)?)\s*%/g)) {
        const value = Number(match[1]);
        if (Number.isFinite(value)) quotaPercentCandidates.push({ line, value });
      }
    }
    const tokenBest =
      tokenCandidates.find((item) => /\b(total|token usage|all time)\b/i.test(item.line)) ||
      tokenCandidates[0] ||
      null;
    const quotaBest =
      quotaPercentCandidates.find((item) => /\b(quota|remaining|prompt pool|weekly|monthly)\b/i.test(item.line)) ||
      quotaPercentCandidates.find((item) => !/\bcontext\b/i.test(item.line)) ||
      quotaPercentCandidates[0] ||
      null;
    return {
      captured_at: new Date().toISOString(),
      title: document.title,
      visible_usage_lines: relevant.slice(0, 80),
      token_candidates: tokenCandidates.slice(0, 20),
      quota_percent_candidates: quotaPercentCandidates.slice(0, 20),
      best: {
        tokens_total: tokenBest?.value ?? null,
        tokens_line: tokenBest?.line ?? null,
        quota_percent: quotaBest?.value ?? null,
        quota_percent_line: quotaBest?.line ?? null,
      },
    };
  })()`;
}

export function openUsageExpression() {
  return `(() => {
    const dispatchClick = (el) => {
      const r = el.getBoundingClientRect();
      const x = Math.round(r.x + r.width / 2);
      const y = Math.round(r.y + r.height / 2);
      for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
        el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
      }
      return { x, y };
    };
    const clickCandidate = (needles) => {
      const candidates = Array.from(document.querySelectorAll('button,[role=button],a,[role=menuitem],[data-testid]'));
      const el = candidates.find((node) => {
        const text = (node.innerText || node.textContent || node.getAttribute('aria-label') || '').trim().toLowerCase();
        const testid = (node.getAttribute('data-testid') || '').toLowerCase();
        const rect = node.getBoundingClientRect();
        const visible = rect.width > 0 && rect.height > 0;
        return visible && needles.some((needle) => text.includes(needle) || testid.includes(needle));
      });
      if (!el) return null;
      return { text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim(), ...dispatchClick(el) };
    };
    const direct = clickCandidate(['usage stats', 'usage', 'quota', 'coding plan']);
    if (direct) return { ok: true, phase: 'usage', clicked: direct };
    const settings = clickCandidate(['settings', 'preferences']);
    if (settings) return { ok: true, phase: 'settings', clicked: settings, next: 'run open-usage again if usage is not visible' };
    return { ok: false, reason: 'usage entry not found' };
  })()`;
}

export function summaryExpression() {
  return `(() => {
    const bodyText = document.body?.innerText || "";
    const buttons = Array.from(document.querySelectorAll('button,[role=button]')).map((el) => {
      const r = el.getBoundingClientRect();
      return {
        text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 120),
        aria: el.getAttribute('aria-label'),
        disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
        rect: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      };
    });
    const visibleButtons = buttons.filter((button) => button.rect.w > 0 && button.rect.h > 0);
    return {
      running: /\\bWorking for\\b/.test(bodyText) || visibleButtons.some((button) => button.text === 'Stop' || button.aria === 'Stop'),
      awaitingApproval: /Awaiting approval|Permission required/.test(bodyText),
      workedFor: (bodyText.match(/Worked for\\s+([^\\n]+)/) || [])[1] || null,
      contextUsage: (bodyText.match(/Context usage\\s+[^\\n]+/) || [])[0] || null,
      activeMode: visibleButtons.find((button) => button.aria === 'Switch mode')?.text || null,
      activeModel: visibleButtons.find((button) => button.aria === 'Choose model')?.text || null,
      activeWorkspace: visibleButtons.find((button) => button.aria === 'Choose workspace')?.text || null,
      lastText: bodyText.slice(-3000),
    };
  })()`;
}
