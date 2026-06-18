import test from "node:test";
import assert from "node:assert/strict";
import { execFile as execFileCallback } from "node:child_process";
import http from "node:http";
import { mkdtemp, writeFile, mkdir, readFile, chmod, symlink, unlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { promisify } from "node:util";

const ROOT = resolve(import.meta.dirname, "..");
const ZCODECTL = resolve(ROOT, "tools", "zcode_control", "zcodectl.mjs");
const SUPERVISOR = resolve(ROOT, "tools", "zcode_supervisor", "zcode_supervisor.py");
const execFile = promisify(execFileCallback);

async function makeWorkspace(initialText, validationText, options = {}) {
  const root = await mkdtemp(join(tmpdir(), "zcode-run-packet-e2e-"));
  const workspace = join(root, "workspace");
  await mkdir(join(workspace, "src"), { recursive: true });
  await writeFile(join(workspace, "src", "app.js"), initialText);
  if (options.visionImage) {
    await mkdir(join(workspace, "screenshots"), { recursive: true });
    await writeFile(
      join(workspace, "screenshots", "state.png"),
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    );
  }
  await writeFile(
    join(workspace, "check.py"),
    [
      "from pathlib import Path",
      `raise SystemExit(0 if Path('src/app.js').read_text() == ${JSON.stringify(validationText)} else 1)`,
      "",
    ].join("\n"),
  );
  const packet = join(root, "packet.json");
  const packetArgs = [
    SUPERVISOR,
    "packet",
    "--workspace",
    workspace,
    "--objective",
    "synthetic provider overload regression test",
    "--allowed",
    "src/app.js",
    "--validation",
    "python3 check.py",
    "--out",
    packet,
  ];
  if (options.visionImage) packetArgs.push("--vision-image", "screenshots/state.png");
  if (options.visionRequired) packetArgs.push("--vision-required");
  await execFile("python3", packetArgs);
  return { root, workspace, packet };
}

async function writeFakeCli(root, source, name = "fake-zcode.cjs") {
  const cli = join(root, name);
  await writeFile(cli, source);
  await chmod(cli, 0o755);
  return cli;
}

async function runPacket({ packet, cli, codexbar, usageSnapshotSource = "none", extraArgs = [], env = {} }) {
  const out = join(dirname(packet), "run.json");
  await execFile(
    "node",
    [
      ZCODECTL,
      "run-packet",
      "--packet",
      packet,
      "--max-attempts",
      "2",
      "--retry-delay-ms",
      "0",
      "--no-bootstrap",
      "--usage-snapshot-source",
      usageSnapshotSource,
      ...extraArgs,
      "--out",
      out,
    ],
    {
      env: {
        ...process.env,
        ZCODE_CLI_PATH: cli,
        ...(codexbar ? { CODEXBAR_PATH: codexbar } : {}),
        ...env,
      },
      cwd: ROOT,
      maxBuffer: 10 * 1024 * 1024,
    },
  ).catch(() => {});
  return JSON.parse(await readFile(out, "utf8"));
}

async function withQuotaServer(percentages, callback, options = {}) {
  let calls = 0;
  const server = http.createServer((request, response) => {
    assert.equal(request.headers.authorization, "Bearer local-fixture-value");
    const percentage = percentages[Math.min(calls, percentages.length - 1)];
    calls += 1;
    const tokenLimit = {
      type: "TOKENS_LIMIT",
      percentage,
      nextResetTime: 1781680000000,
    };
    if (options.includeTokenCounts) {
      tokenLimit.usage = percentage * 1000;
      tokenLimit.remaining = 100000 - tokenLimit.usage;
    }
    response.setHeader("content-type", "application/json");
    response.end(JSON.stringify({
      code: 200,
      data: {
        level: "pro",
        limits: [
          tokenLimit,
          {
            type: "TIME_LIMIT",
            percentage: 0.5,
            usage: 30,
            remaining: 70,
          },
        ],
      },
    }));
  });
  await new Promise((resolveListen) => server.listen(0, "127.0.0.1", resolveListen));
  try {
    const { port } = server.address();
    return await callback(`http://127.0.0.1:${port}/quota`, () => calls);
  } finally {
    await new Promise((resolveClose) => server.close(resolveClose));
  }
}

const overloadStderr = `
process.stderr.write("ProviderBusinessError: [1305][The service may be temporarily overloaded, please try again later][synthetic]\\n  code: 'PROVIDER_BUSINESS_ERROR',\\n  isProviderBusinessError: true,\\n  providerCode: '1305',\\n  providerId: 'zai',\\n  providerKind: 'anthropic',\\n  providerMessage: '[1305][The service may be temporarily overloaded, please try again later][synthetic]'\\n");
process.exit(143);
`;

test("run-packet retries no-change provider overload and reports retryable state", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n");
  const cli = await writeFakeCli(fixture.root, `#!/usr/bin/env node\n${overloadStderr}`);

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, false);
  assert.equal(result.cli_ok, false);
  assert.equal(result.supervisor_state, "retryable_provider_error");
  assert.equal(result.provider_error, true);
  assert.equal(result.provider_code, "1305");
  assert.equal(result.attempts, 2);
  assert.equal(result.attempt_count, 2);
  assert.equal(result.retry_count, 1);
  assert.deepEqual(result.retry_delays_ms, [0]);
  assert.equal(result.safe_to_retry_later, true);
  assert.equal(result.partial_artifacts_possible, false);
  assert.equal(result.usage_available, false);
  assert.equal(result.no_usage_reason, "provider_error_without_zcode_cli_usage");
  assert.equal(result.usage_accounting.no_usage_reason, "provider_error_without_zcode_cli_usage");
  assert.equal(result.attempt_results[0].changed_count, 0);
  assert.equal(result.attempt_results[0].no_usage_reason, "provider_error_without_zcode_cli_usage");
});

test("run-packet preserves audited partial artifacts after provider overload", async () => {
  const fixture = await makeWorkspace("before\n", "after\n");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const cwdIndex = process.argv.indexOf('--cwd');
const cwd = cwdIndex >= 0 ? process.argv[cwdIndex + 1] : process.cwd();
fs.writeFileSync(path.join(cwd, 'src/app.js'), 'after\\n');
${overloadStderr}`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, true);
  assert.equal(result.cli_ok, false);
  assert.equal(result.supervisor_state, "partial_success");
  assert.equal(result.provider_error, true);
  assert.equal(result.provider_code, "1305");
  assert.equal(result.attempts, 1);
  assert.equal(result.attempt_count, 1);
  assert.equal(result.retry_count, 0);
  assert.equal(result.safe_to_retry_later, false);
  assert.equal(result.partial_artifacts_possible, true);
  assert.equal(result.usage_available, false);
  assert.equal(result.no_usage_reason, "provider_error_without_zcode_cli_usage");
  assert.equal(result.usage_accounting.no_usage_reason, "provider_error_without_zcode_cli_usage");
  assert.equal(result.audit.ok, true);
  assert.equal(result.audit.changed_count, 1);
  assert.equal(result.audit.validation.ok, true);
});

test("run-packet audits successful CLI output before accepting it", async () => {
  const fixture = await makeWorkspace("before\n", "after\n");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const cwdIndex = process.argv.indexOf('--cwd');
const cwd = cwdIndex >= 0 ? process.argv[cwdIndex + 1] : process.cwd();
fs.writeFileSync(path.join(cwd, 'src/app.js'), 'after\\n');
process.stdout.write(JSON.stringify({
  response: "done",
  usage: { totalTokens: 15, inputTokens: 10, outputTokens: 5 }
}) + "\\n");
`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, true);
  assert.equal(result.cli_ok, true);
  assert.equal(result.supervisor_state, "success");
  assert.equal(result.audit.ok, true);
  assert.equal(result.audit.changed_count, 1);
  assert.equal(result.audit.validation.ok, true);
  assert.equal(result.validation.ok, true);
  assert.equal(result.validation_ok, true);
});

test("run-packet rejects successful CLI output when supervisor audit fails", async () => {
  const fixture = await makeWorkspace("before\n", "after\n");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
const fs = require('node:fs');
const path = require('node:path');
const cwdIndex = process.argv.indexOf('--cwd');
const cwd = cwdIndex >= 0 ? process.argv[cwdIndex + 1] : process.cwd();
fs.writeFileSync(path.join(cwd, 'src/app.js'), 'wrong\\n');
process.stdout.write(JSON.stringify({
  response: "done",
  usage: { totalTokens: 15, inputTokens: 10, outputTokens: 5 }
}) + "\\n");
`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, false);
  assert.equal(result.cli_ok, true);
  assert.equal(result.supervisor_state, "audit_failed");
  assert.equal(result.audit.ok, false);
  assert.equal(result.audit.changed_count, 1);
  assert.equal(result.audit.validation.ok, false);
  assert.equal(result.validation.ok, false);
  assert.equal(result.validation_ok, false);
  assert.equal(result.partial_artifacts_possible, true);
});

test("run-packet attaches packet vision images when image service is configured", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const argvPath = join(fixture.root, "argv.json");
  const envPath = join(fixture.root, "env.json");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
const fs = require('node:fs');
fs.writeFileSync(${JSON.stringify(argvPath)}, JSON.stringify(process.argv));
fs.writeFileSync(${JSON.stringify(envPath)}, JSON.stringify({
  zAiApiKey: process.env.Z_AI_API_KEY || null
}));
process.stdout.write(JSON.stringify({
  response: "vision done",
  usage: { totalTokens: 11, inputTokens: 7, outputTokens: 4 }
}) + "\\n");
`,
  );
  const cliConfig = join(fixture.root, "cli-config.json");
  await writeFile(cliConfig, JSON.stringify({
    provider: {
      zai: {
        options: {
          ["api" + "Key"]: "fixture-" + "zai-value",
        },
      },
    },
    mcp: {
      servers: {
        "image-service": {
          command: "npx",
          args: ["-y", "@z_ai/mcp-server"],
        },
      },
    },
  }));

  const result = await runPacket({
    packet: fixture.packet,
    cli,
    extraArgs: ["--cli-config", cliConfig],
    env: {
      ["Z_AI_" + "API" + "_KEY"]: "",
      ["ZAI_" + "API" + "_KEY"]: "legacy-" + "fixture-value",
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.vision.required, true);
  assert.deepEqual(result.vision.image_files, ["screenshots/state.png"]);
  assert.equal(result.vision_preflight.ok, true);
  assert.equal(result.vision_preflight.detected_server, "image-service");
  assert.equal(result.audit.ok, true);
  assert.equal(result.validation.ok, true);
  assert.equal(result.vision_service_credential_source, "env:ZAI_API_KEY");
  const argv = JSON.parse(await readFile(argvPath, "utf8"));
  const attachIndex = argv.indexOf("--attach");
  assert.notEqual(attachIndex, -1);
  assert.equal(argv[attachIndex + 1], result.vision.attached_files[0]);
  const envSeen = JSON.parse(await readFile(envPath, "utf8"));
  assert.equal(envSeen.zAiApiKey, "legacy-fixture-value");
});

test("run-packet stops required vision packets before CLI when image service is missing", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const calledPath = join(fixture.root, "called.txt");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
require('node:fs').writeFileSync(${JSON.stringify(calledPath)}, 'called');
process.stdout.write(JSON.stringify({ response: "should not run" }) + "\\n");
`,
  );
  const cliConfig = join(fixture.root, "cli-config.json");
  await writeFile(cliConfig, JSON.stringify({
    mcp: {
      servers: {
        "generic-vision": {
          command: "vision-mcp",
          args: ["serve"],
        },
      },
    },
  }));

  const result = await runPacket({
    packet: fixture.packet,
    cli,
    extraArgs: ["--cli-config", cliConfig],
  });

  assert.equal(result.ok, false);
  assert.equal(result.status, "vision_service_unavailable");
  assert.equal(result.supervisor_state, "vision_service_unavailable");
  assert.equal(result.vision_preflight.ok, false);
  await assert.rejects(readFile(calledPath, "utf8"));
});

test("run-packet does not satisfy custom vision service with default ZAI MCP", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const calledPath = join(fixture.root, "called.txt");
  const payload = JSON.parse(await readFile(fixture.packet, "utf8"));
  payload.vision.service = "custom-image-service";
  await writeFile(fixture.packet, JSON.stringify(payload));
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
require('node:fs').writeFileSync(${JSON.stringify(calledPath)}, 'called');
process.stdout.write(JSON.stringify({ response: "should not run" }) + "\\n");
`,
  );
  const cliConfig = join(fixture.root, "cli-config.json");
  await writeFile(cliConfig, JSON.stringify({
    mcp: {
      servers: {
        "default-zai": {
          command: "npx",
          args: ["-y", "@z_ai/mcp-server"],
        },
      },
    },
  }));

  const result = await runPacket({
    packet: fixture.packet,
    cli,
    extraArgs: ["--cli-config", cliConfig],
  });

  assert.equal(result.ok, false);
  assert.equal(result.status, "vision_service_unavailable");
  assert.equal(result.vision.service, "custom-image-service");
  assert.equal(result.vision_preflight.ok, false);
  await assert.rejects(readFile(calledPath, "utf8"));
});

test("run-packet rejects unsafe packet vision attachments before CLI", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const calledPath = join(fixture.root, "called.txt");
  await writeFile(join(fixture.workspace, "screenshots", "credential.png"), Buffer.from([0x89, 0x50]));
  const payload = JSON.parse(await readFile(fixture.packet, "utf8"));
  payload.vision.image_files = ["screenshots/credential.png"];
  await writeFile(fixture.packet, JSON.stringify(payload));
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
require('node:fs').writeFileSync(${JSON.stringify(calledPath)}, 'called');
process.stdout.write(JSON.stringify({ response: "should not run" }) + "\\n");
`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, false);
  assert.equal(result.status, "vision_attachment_invalid");
  assert.match(result.error, /secret-like vision attachment/);
  await assert.rejects(readFile(calledPath, "utf8"));
});

test("run-packet rejects non-image packet vision attachments before CLI", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const calledPath = join(fixture.root, "called.txt");
  await writeFile(join(fixture.workspace, "screenshots", "state.txt"), "not an image");
  const payload = JSON.parse(await readFile(fixture.packet, "utf8"));
  payload.vision.image_files = ["screenshots/state.txt"];
  await writeFile(fixture.packet, JSON.stringify(payload));
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
require('node:fs').writeFileSync(${JSON.stringify(calledPath)}, 'called');
process.stdout.write(JSON.stringify({ response: "should not run" }) + "\\n");
`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, false);
  assert.equal(result.status, "vision_attachment_invalid");
  assert.match(result.error, /must be an image file/);
  await assert.rejects(readFile(calledPath, "utf8"));
});

test("run-packet rejects fake image-extension vision attachments before CLI", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const calledPath = join(fixture.root, "called.txt");
  await writeFile(join(fixture.workspace, "screenshots", "fake.png"), "not an image");
  const payload = JSON.parse(await readFile(fixture.packet, "utf8"));
  payload.vision.image_files = ["screenshots/fake.png"];
  await writeFile(fixture.packet, JSON.stringify(payload));
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
require('node:fs').writeFileSync(${JSON.stringify(calledPath)}, 'called');
process.stdout.write(JSON.stringify({ response: "should not run" }) + "\\n");
`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, false);
  assert.equal(result.status, "vision_attachment_invalid");
  assert.match(result.error, /not a valid image file/);
  await assert.rejects(readFile(calledPath, "utf8"));
});

test("run-packet rejects symlinked vision attachments outside workspace before CLI", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n", { visionImage: true });
  const calledPath = join(fixture.root, "called.txt");
  const outsideImage = join(fixture.root, "outside.png");
  await writeFile(outsideImage, Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  await unlink(join(fixture.workspace, "screenshots", "state.png"));
  await symlink(outsideImage, join(fixture.workspace, "screenshots", "state.png"));
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
require('node:fs').writeFileSync(${JSON.stringify(calledPath)}, 'called');
process.stdout.write(JSON.stringify({ response: "should not run" }) + "\\n");
`,
  );

  const result = await runPacket({ packet: fixture.packet, cli });

  assert.equal(result.ok, false);
  assert.equal(result.status, "vision_attachment_invalid");
  assert.match(result.error, /target escapes workspace/);
  await assert.rejects(readFile(calledPath, "utf8"));
});

test("run-packet captures CodexBar quota snapshots and ZCode CLI token usage", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
process.stdout.write(JSON.stringify({
  response: "done",
  usage: {
    totalTokens: 1234,
    inputTokens: 1000,
    outputTokens: 234,
    cacheReadTokens: 456
  },
  projection: { contextWindow: 200000 }
}) + "\\n");
`,
  );
  const counterPath = join(fixture.root, "codexbar-count.txt");
  const codexbar = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
const fs = require('node:fs');
const path = ${JSON.stringify(counterPath)};
const previous = fs.existsSync(path) ? Number(fs.readFileSync(path, 'utf8')) : 0;
const next = previous + 1;
fs.writeFileSync(path, String(next));
const usedPercent = next === 1 ? 1.25 : 1.75;
process.stdout.write(JSON.stringify([{
  provider: "zai",
  source: "api",
  usage: {
    identity: { providerID: "zai" },
    primary: {
      resetDescription: "5 hours window",
      resetsAt: "2026-06-17T18:30:44Z",
      usedPercent,
      windowMinutes: 300
    },
    secondary: {
      resetDescription: "Monthly",
      resetsAt: "2026-07-04T05:08:05Z",
      usedPercent: 0.5
    },
    tertiary: null,
    updatedAt: "2026-06-17T14:01:03Z"
  }
}]) + "\\n");
`,
    "fake-codexbar.cjs",
  );

  const result = await runPacket({
    packet: fixture.packet,
    cli,
    codexbar,
    usageSnapshotSource: "codexbar",
  });

  assert.equal(result.ok, true);
  assert.equal(result.supervisor_state, "success");
  assert.equal(result.usage_snapshots.before.ok, true);
  assert.equal(result.usage_snapshots.after.ok, true);
  assert.equal(result.usage_snapshots.before.best.quota_percent, 1.25);
  assert.equal(result.usage_snapshots.after.best.quota_percent, 1.75);
  assert.equal(result.usage_accounting.tokens_source, "zcode_cli_json_usage");
  assert.equal(result.usage_accounting.tokens_used, 1234);
  assert.equal(result.usage_accounting.input_tokens, 1000);
  assert.equal(result.usage_accounting.output_tokens, 234);
  assert.equal(result.usage_accounting.cache_read_tokens, 456);
  assert.equal(result.usage_accounting.quota_source, "codexbar");
  assert.equal(result.usage_accounting.quota_percent_direction, "used");
  assert.equal(result.usage_accounting.quota_percent_before, 1.25);
  assert.equal(result.usage_accounting.quota_percent_after, 1.75);
  assert.equal(result.usage_accounting.quota_percent_used, 0.5);
  assert.equal(result.usage_accounting.quota_windows.primary.used_percent_delta, 0.5);
  assert.equal(result.usage_normalized.total_tokens, 1234);
  assert.equal(result.attempt_results[0].tokens_total, 1234);
});

test("run-packet captures Z.AI quota snapshots without CodexBar", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
process.stdout.write(JSON.stringify({
  response: "done",
  usage: {
    totalTokens: 77,
    inputTokens: 50,
    outputTokens: 27
  }
}) + "\\n");
`,
  );

  await withQuotaServer([2.0, 2.75], async (quotaUrl, calls) => {
    const result = await runPacket({
      packet: fixture.packet,
      cli,
      usageSnapshotSource: "zai-api",
      extraArgs: ["--zai-quota-url", quotaUrl],
      env: { ["ZAI_" + "API_KEY"]: "local-fixture-value" },
    });

    assert.equal(calls(), 2);
    assert.equal(result.ok, true);
    assert.equal(result.supervisor_state, "success");
    assert.equal(result.usage_snapshots.before.ok, true);
    assert.equal(result.usage_snapshots.after.ok, true);
    assert.equal(result.usage_snapshots.before.source, "zai-api");
    assert.equal(result.usage_snapshots.after.source, "zai-api");
    assert.equal(result.usage_snapshots.before.credential_source, "env:ZAI_API_KEY");
    assert.equal(result.usage_snapshots.before.windows.primary.authoritative, true);
    assert.equal(result.usage_snapshots.before.best.quota_percent, 2.0);
    assert.equal(result.usage_snapshots.after.best.quota_percent, 2.75);
    assert.equal(result.usage_accounting.tokens_used, 77);
    assert.equal(result.usage_accounting.quota_source, "zai-api");
    assert.equal(result.usage_accounting.quota_percent_before, 2.0);
    assert.equal(result.usage_accounting.quota_percent_after, 2.75);
    assert.equal(result.usage_accounting.quota_percent_used, 0.75);
    assert.equal(result.usage_accounting.quota_percent_status, "measured");
    assert.equal(result.usage_accounting.quota_windows.primary.used_percent_delta, 0.75);
  }, { includeTokenCounts: true });
});

test("run-packet derives quota delta from Z.AI percentage without token counts", async () => {
  const fixture = await makeWorkspace("ok\n", "ok\n");
  const cli = await writeFakeCli(
    fixture.root,
    `#!/usr/bin/env node
process.stdout.write(JSON.stringify({
  response: "done",
  usage: {
    totalTokens: 77,
    inputTokens: 50,
    outputTokens: 27
  }
}) + "\\n");
`,
  );

  await withQuotaServer([2.0, 2.75], async (quotaUrl, calls) => {
    const result = await runPacket({
      packet: fixture.packet,
      cli,
      usageSnapshotSource: "zai-api",
      extraArgs: ["--zai-quota-url", quotaUrl],
      env: { ["ZAI_" + "API_KEY"]: "local-fixture-value" },
    });

    assert.equal(calls(), 2);
    assert.equal(result.ok, true);
    assert.equal(result.usage_snapshots.before.windows.primary.authoritative, true);
    assert.equal(result.usage_snapshots.before.windows.primary.token_counts_available, false);
    assert.equal(result.usage_snapshots.before.windows.primary.used_percent, 2.0);
    assert.equal(result.usage_snapshots.before.windows.primary.non_authoritative_used_percent, null);
    assert.equal(result.usage_snapshots.before.windows.primary.quota_percent_unavailable_reason, null);
    assert.equal(result.usage_snapshots.before.best.quota_percent, 2.0);
    assert.equal(result.usage_snapshots.before.best.raw_quota_percent, 2.0);
    assert.equal(result.usage_accounting.quota_percent_before, 2.0);
    assert.equal(result.usage_accounting.quota_percent_after, 2.75);
    assert.equal(result.usage_accounting.quota_percent_used, 0.75);
    assert.equal(result.usage_accounting.quota_percent_status, "measured");
    assert.equal(result.usage_accounting.quota_percent_unavailable_reason, null);
    assert.equal(result.usage_accounting.quota_windows.primary.used_percent_delta, 0.75);
  });
});
