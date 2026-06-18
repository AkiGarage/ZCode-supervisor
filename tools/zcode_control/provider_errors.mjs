const OVERLOAD_RE = /temporarily overloaded|try again later|overloaded_error/i;

export const DEFAULT_PROVIDER_MAX_ATTEMPTS = 2;
export const DEFAULT_PROVIDER_RETRY_DELAY_MS = 60_000;

function firstMatch(text, patterns) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return match[1];
  }
  return null;
}

function firstProviderLine(text) {
  return text.split(/\r?\n/).find((line) => /ProviderBusinessError|PROVIDER_BUSINESS_ERROR/i.test(line)) ?? null;
}

export function classifyProviderError({ stdout = "", stderr = "", exitCode = null } = {}) {
  const text = `${stderr}\n${stdout}`;
  const exitCodeNumber = Number(exitCode);
  const exit143 = Number.isFinite(exitCodeNumber) && exitCodeNumber === 143;
  const providerBusiness = /ProviderBusinessError|PROVIDER_BUSINESS_ERROR|isProviderBusinessError:\s*true/i.test(text);
  const providerCode = firstMatch(text, [
    /providerCode:\s*['"]?(\d+)['"]?/,
    /"providerCode"\s*:\s*"(\d+)"/,
    /\[(\d{3,})\]\[/,
    /\bcode:\s*['"]?(\d{3,})['"]?/,
    /"code"\s*:\s*"(\d{3,})"/,
  ]);
  const temporary = OVERLOAD_RE.test(text) || providerCode === "1305";
  const providerError = providerBusiness || temporary || providerCode === "1305" || exit143;
  const providerMessage = firstMatch(text, [
    /providerMessage:\s*'([^']+)'/,
    /providerMessage:\s*"([^"]+)"/,
    /"providerMessage"\s*:\s*"([^"]+)"/,
    /ProviderBusinessError:\s*([^\n]+)/,
  ]) ?? (exit143 ? "ZCode CLI exited with code 143" : null);

  return {
    provider_error: providerError,
    provider_code: providerCode,
    provider_message: providerMessage,
    provider_id: firstMatch(text, [/providerId:\s*'([^']+)'/, /providerId:\s*"([^"]+)"/, /"providerId"\s*:\s*"([^"]+)"/]),
    provider_kind: firstMatch(text, [/providerKind:\s*'([^']+)'/, /providerKind:\s*"([^"]+)"/, /"providerKind"\s*:\s*"([^"]+)"/]),
    provider_request_id: firstMatch(text, [
      /providerRequestId:\s*'([^']+)'/,
      /providerRequestId:\s*"([^"]+)"/,
      /"providerRequestId"\s*:\s*"([^"]+)"/,
      /request_id:\s*'([^']+)'/,
      /"request_id"\s*:\s*"([^"]+)"/,
    ]),
    provider_error_line: firstProviderLine(text),
    provider_error_temporary: temporary,
    retryable_provider_error: providerError && (temporary || exit143),
  };
}

function parsedJsonObjects(stdout) {
  const trimmed = stdout.trim();
  if (!trimmed) return [];
  const candidates = [trimmed, ...trimmed.split(/\r?\n/).filter((line) => line.trim().startsWith("{"))];
  const objects = [];
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) objects.push(parsed);
    } catch {
      // CLI output may be prose, JSONL, or empty; non-JSON chunks are ignored.
    }
  }
  return objects;
}

function hasUsageShape(value) {
  if (!value || typeof value !== "object") return false;
  const usage = value.usage;
  if (usage && typeof usage === "object") return true;
  return [
    "tokens_total",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
  ].some((key) => typeof value[key] === "number");
}

export function usageAvailableFromStdout(stdout = "") {
  return parsedJsonObjects(stdout).some(hasUsageShape);
}

export function classifyProviderRunState({ cliOk, provider, audit }) {
  if (cliOk) {
    if (audit?.ok === false) {
      const changedCount = Number.isFinite(Number(audit?.changed_count)) ? Number(audit.changed_count) : null;
      return {
        supervisor_state: "audit_failed",
        partial_artifacts_possible: changedCount === null ? true : changedCount > 0,
        safe_to_retry_later: false,
      };
    }
    return {
      supervisor_state: "success",
      partial_artifacts_possible: false,
      safe_to_retry_later: false,
    };
  }
  if (!provider?.provider_error) {
    return {
      supervisor_state: "cli_error",
      partial_artifacts_possible: false,
      safe_to_retry_later: false,
    };
  }

  const changedCount = Number.isFinite(Number(audit?.changed_count)) ? Number(audit.changed_count) : null;
  if (changedCount === 0 && provider.retryable_provider_error) {
    return {
      supervisor_state: "retryable_provider_error",
      partial_artifacts_possible: false,
      safe_to_retry_later: true,
    };
  }
  if (changedCount !== null && changedCount > 0 && audit?.ok === true) {
    return {
      supervisor_state: "partial_success",
      partial_artifacts_possible: true,
      safe_to_retry_later: false,
    };
  }
  return {
    supervisor_state: "unsafe_partial",
    partial_artifacts_possible: changedCount === null ? true : changedCount > 0,
    safe_to_retry_later: false,
  };
}
