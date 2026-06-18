import test from "node:test";
import assert from "node:assert/strict";

import {
  classifyProviderError,
  classifyProviderRunState,
  usageAvailableFromStdout,
} from "../tools/zcode_control/provider_errors.mjs";

const overloadStderr = `ProviderBusinessError: [1305][The service may be temporarily overloaded, please try again later][req-1]
  code: 'PROVIDER_BUSINESS_ERROR',
  isProviderBusinessError: true,
  providerCode: '1305',
  providerId: 'zai',
  providerKind: 'anthropic',
  providerMessage: '[1305][The service may be temporarily overloaded, please try again later][req-1]'`;

test("classifies ZCode provider overload stderr", () => {
  const provider = classifyProviderError({ stderr: overloadStderr, exitCode: 143 });

  assert.equal(provider.provider_error, true);
  assert.equal(provider.provider_code, "1305");
  assert.equal(provider.provider_id, "zai");
  assert.equal(provider.provider_kind, "anthropic");
  assert.equal(provider.provider_error_temporary, true);
  assert.equal(provider.retryable_provider_error, true);
});

test("exit code 143 is classified for supervisor handling", () => {
  const provider = classifyProviderError({ stderr: "", exitCode: 143 });

  assert.equal(provider.provider_error, true);
  assert.equal(provider.provider_code, null);
  assert.equal(provider.retryable_provider_error, true);
});

test("no-change provider error is retryable while valid changed artifacts are partial success", () => {
  const provider = classifyProviderError({ stderr: overloadStderr, exitCode: 143 });

  assert.equal(
    classifyProviderRunState({ cliOk: false, provider, audit: { changed_count: 0, ok: false } }).supervisor_state,
    "retryable_provider_error",
  );
  assert.equal(
    classifyProviderRunState({ cliOk: false, provider, audit: { changed_count: 2, ok: true } }).supervisor_state,
    "partial_success",
  );
});

test("successful CLI result is blocked when supervisor audit fails", () => {
  assert.equal(
    classifyProviderRunState({
      cliOk: true,
      provider: { provider_error: false },
      audit: { changed_count: 1, ok: false },
    }).supervisor_state,
    "audit_failed",
  );
  assert.equal(
    classifyProviderRunState({
      cliOk: true,
      provider: { provider_error: false },
      audit: { changed_count: 0, ok: true },
    }).supervisor_state,
    "success",
  );
});

test("detects usage JSON only when token usage is present", () => {
  assert.equal(usageAvailableFromStdout('{"usage":{"input_tokens":10,"output_tokens":2}}\n'), true);
  assert.equal(usageAvailableFromStdout("plain final answer\n"), false);
});
