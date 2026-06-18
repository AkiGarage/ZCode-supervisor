#!/usr/bin/env node
// Minimal Codex-side controller for ZCode.
// Uses stable surfaces first: app metadata, cua-driver launch, and Electron CDP.

import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { access, chmod, mkdir, open, readFile, realpath, rename, unlink, writeFile } from "node:fs/promises";
import http from "node:http";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { openUsageExpression, summaryExpression, usageSnapshotExpression } from "./browser_scripts.mjs";
import {
  DEFAULT_PROVIDER_MAX_ATTEMPTS,
  DEFAULT_PROVIDER_RETRY_DELAY_MS,
  classifyProviderError,
  classifyProviderRunState,
  usageAvailableFromStdout,
} from "./provider_errors.mjs";

const execFileAsync = promisify(execFile);
const DEFAULT_PORT = 9223;
const DEFAULT_BUNDLE_ID = "dev.zcode.app";
const DEFAULT_ZCODE_CLI = "/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs";
const PROMPT_TIMEOUT_MS = 30 * 60 * 1000;
const TOOL_DIR = dirname(fileURLToPath(import.meta.url));
const SUPERVISOR_SCRIPT = resolve(TOOL_DIR, "..", "zcode_supervisor", "zcode_supervisor.py");
const DEFAULT_USAGE_PROVIDER = "zai";
const DEFAULT_USAGE_SNAPSHOT_TIMEOUT_MS = 20_000;
const DEFAULT_ZAI_QUOTA_URL = "https://api.z.ai/api/monitor/usage/quota/limit";
const DEFAULT_VISION_SERVICE = "zai-mcp-server";
const IMAGE_EXTENSIONS = new Set([".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"]);
const SECRET_PATH_NEEDLES = [".env", "id_rsa", "id_ed25519", ".ssh", "credential", "credentials"];

function usage() {
  console.log(`zcodectl

Usage:
  node tools/zcode_control/zcodectl.mjs doctor
  node tools/zcode_control/zcodectl.mjs cli-path
  node tools/zcode_control/zcodectl.mjs cli-doctor
  node tools/zcode_control/zcodectl.mjs cli-preflight
  node tools/zcode_control/zcodectl.mjs cli-version
  node tools/zcode_control/zcodectl.mjs bootstrap-cli-config [--provider zai|bigmodel] [--model glm-5.2] [--source-config <json>] [--cli-config <json>] [--out <json>]
  node tools/zcode_control/zcodectl.mjs vision-preflight [--workspace <path>] [--vision-service zai-mcp-server] [--cli-config <json>] [--out <json>]
  node tools/zcode_control/zcodectl.mjs cli-prompt (--text <prompt> | --text-file <path>) [--workspace <path>] [--mode plan|edit|build|yolo] [--json] [--out <json>]
  node tools/zcode_control/zcodectl.mjs run-packet --packet <json> [--mode plan|edit|build|yolo] [--max-attempts 2] [--retry-delay-ms 60000] [--validation-timeout 60] [--usage-snapshot-source auto|zai-api|codexbar|none] [--usage-provider zai] [--vision-preflight auto|required|off] [--json] [--out <json>]
  node tools/zcode_control/zcodectl.mjs launch [--port 9223] [--new-instance]
  node tools/zcode_control/zcodectl.mjs targets [--port 9223]
  node tools/zcode_control/zcodectl.mjs text [--port 9223] [--max 4000]
  node tools/zcode_control/zcodectl.mjs eval --expr <js> [--port 9223]
  node tools/zcode_control/zcodectl.mjs textboxes [--port 9223]
  node tools/zcode_control/zcodectl.mjs buttons [--port 9223]
  node tools/zcode_control/zcodectl.mjs summary [--port 9223]
  node tools/zcode_control/zcodectl.mjs open-usage [--port 9223]
  node tools/zcode_control/zcodectl.mjs usage [--out <json>] [--port 9223]
  node tools/zcode_control/zcodectl.mjs new-task --workspace <name> [--port 9223]
  node tools/zcode_control/zcodectl.mjs set-mode --mode <mode> [--port 9223]
  node tools/zcode_control/zcodectl.mjs set-composer (--text <text> | --text-file <path>) [--port 9223]
  node tools/zcode_control/zcodectl.mjs submit-task (--text <prompt> | --text-file <path>) [--port 9223]
  node tools/zcode_control/zcodectl.mjs goal (--text <prompt> | --text-file <path>) [--port 9223]
  node tools/zcode_control/zcodectl.mjs wait-idle [--timeout-ms 300000] [--interval-ms 2000] [--port 9223]
  node tools/zcode_control/zcodectl.mjs click --text <label> [--port 9223]
  node tools/zcode_control/zcodectl.mjs click-contains --text <needle> [--port 9223]
  node tools/zcode_control/zcodectl.mjs screenshot --out <png> [--port 9223]

Notes:
  - launch uses cua-driver with Electron remote debugging enabled.
  - cli-* and run-packet use the bundled ZCode headless CLI when available.
  - vision-preflight checks for the ZCode/Z.AI image MCP service without printing secrets.
  - run-packet captures before/after quota snapshots via the Z.AI API or CodexBar when available.
  - eval runs JavaScript inside the ZCode renderer. Do not use it for secrets.
`);
}

function parseArgs(argv) {
  const [command, ...rest] = argv;
  const args = { command, port: DEFAULT_PORT };
  for (let index = 0; index < rest.length; index += 1) {
    const arg = rest[index];
    if (arg === "--port") args.port = Number(rest[++index]);
    else if (arg === "--max") args.max = Number(rest[++index]);
    else if (arg === "--expr") args.expr = rest[++index];
    else if (arg === "--out") args.out = rest[++index];
    else if (arg === "--text") args.text = rest[++index];
    else if (arg === "--text-file") args.textFile = rest[++index];
    else if (arg === "--packet") args.packet = rest[++index];
    else if (arg === "--workspace") args.workspace = rest[++index];
    else if (arg === "--mode") args.mode = rest[++index];
    else if (arg === "--provider") args.provider = rest[++index];
    else if (arg === "--model") args.model = rest[++index];
    else if (arg === "--lite-model") args.liteModel = rest[++index];
    else if (arg === "--source-config") args.sourceConfig = rest[++index];
    else if (arg === "--cli-config") args.cliConfig = rest[++index];
    else if (arg === "--json") args.json = true;
    else if (arg === "--dry-run") args.dryRun = true;
    else if (arg === "--no-bootstrap") args.noBootstrap = true;
    else if (arg === "--attach") {
      args.attach ??= [];
      args.attach.push(rest[++index]);
    }
    else if (arg === "--resume") args.resume = rest[++index];
    else if (arg === "--continue") args.continue = true;
    else if (arg === "--target") args.target = rest[++index];
    else if (arg === "--target-replace") args.targetReplace = true;
    else if (arg === "--timeout-ms") args.timeoutMs = Number(rest[++index]);
    else if (arg === "--interval-ms") args.intervalMs = Number(rest[++index]);
    else if (arg === "--max-attempts") args.maxAttempts = Number(rest[++index]);
    else if (arg === "--retry-delay-ms") args.retryDelayMs = Number(rest[++index]);
    else if (arg === "--validation-timeout") args.validationTimeout = Number(rest[++index]);
    else if (arg === "--usage-snapshot-source") args.usageSnapshotSource = rest[++index];
    else if (arg === "--usage-provider") args.usageProvider = rest[++index];
    else if (arg === "--usage-snapshot-timeout-ms") args.usageSnapshotTimeoutMs = Number(rest[++index]);
    else if (arg === "--codexbar-path") args.codexbarPath = rest[++index];
    else if (arg === "--zai-quota-url") args.zaiQuotaUrl = rest[++index];
    else if (arg === "--vision-preflight") args.visionPreflight = rest[++index];
    else if (arg === "--vision-service") args.visionService = rest[++index];
    else if (arg === "--new-instance") args.newInstance = true;
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return args;
}

async function readPrompt(args) {
  if (args.text && args.textFile) {
    throw new Error("Use either --text or --text-file, not both");
  }
  if (args.textFile) {
    return readFile(resolve(args.textFile), "utf8");
  }
  if (args.text) return args.text;
  throw new Error("--text or --text-file is required");
}

async function runJson(cmd, args) {
  const { stdout } = await execFileAsync(cmd, args, {
    maxBuffer: 10 * 1024 * 1024,
  });
  return JSON.parse(stdout);
}

async function pathExists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function homeFile(...parts) {
  const home = process.env.HOME;
  if (!home) throw new Error("HOME is not set");
  return join(home, ...parts);
}

function defaultCliConfigPath() {
  return homeFile(".zcode", "cli", "config.json");
}

function defaultGuiConfigPath() {
  return homeFile(".zcode", "v2", "config.json");
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

async function readJsonFile(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function readJsonFileOrEmpty(path) {
  if (!(await pathExists(path))) return {};
  const value = await readJsonFile(path);
  if (!isRecord(value)) throw new Error(`Config file must be a JSON object: ${path}`);
  return value;
}

async function writeJsonFileAtomic(path, value) {
  await mkdir(dirname(path), { recursive: true, mode: 0o700 });
  const tempPath = join(
    dirname(path),
    `.config.json.${process.pid}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`,
  );
  try {
    await writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, {
      mode: 0o600,
    });
    await rename(tempPath, path);
    await chmod(path, 0o600).catch(() => {});
  } catch (error) {
    await unlink(tempPath).catch(() => {});
    throw error;
  }
}

async function resolveZcodeCliPath() {
  const candidates = [process.env.ZCODE_CLI_PATH, DEFAULT_ZCODE_CLI].filter(Boolean);
  for (const candidate of candidates) {
    if (await pathExists(candidate)) return candidate;
  }
  throw new Error(`ZCode CLI not found. Set ZCODE_CLI_PATH or install ZCode.app.`);
}

async function runZcodeCli(cliArgs, options = {}) {
  const cliPath = await resolveZcodeCliPath();
  const timeout = options.timeoutMs ?? 0;
  try {
    const { stdout, stderr } = await execFileAsync("node", [cliPath, ...cliArgs], {
      cwd: options.cwd ?? process.cwd(),
      env: {
        ...process.env,
        ...(options.env ?? {}),
      },
      maxBuffer: 50 * 1024 * 1024,
      timeout: timeout > 0 ? timeout : undefined,
    });
    return enrichCliResult({ ok: true, cli_path: cliPath, stdout, stderr, exit_code: 0 });
  } catch (error) {
    return enrichCliResult({
      ok: false,
      cli_path: cliPath,
      stdout: error.stdout ?? "",
      stderr: error.stderr ?? error.message,
      exit_code: typeof error.code === "number" ? error.code : 1,
    });
  }
}

function enrichCliResult(result) {
  const provider = classifyProviderError({
    stdout: result.stdout,
    stderr: result.stderr,
    exitCode: result.exit_code,
  });
  return {
    ...result,
    cli_ok: result.ok,
    usage_available: usageAvailableFromStdout(result.stdout),
    ...provider,
  };
}

async function printCliResult(result, out) {
  if (out) {
    const outputPath = resolve(out);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`);
  }
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (!result.ok) process.exitCode = result.exit_code || 1;
}

async function cliPath() {
  console.log(await resolveZcodeCliPath());
}

async function cliDoctor(out) {
  const result = await runZcodeCli(["doctor", "--json"]);
  await printCliResult(result, out);
}

async function cliVersion(out) {
  const result = await runZcodeCli(["version", "--json"]);
  await printCliResult(result, out);
}

function redactCliConfig(config) {
  const modelConfig = isRecord(config.model) ? config.model : {};
  const providerConfig = isRecord(config.provider) ? config.provider : {};
  const mcpServers = summarizeMcpServers(config);
  const visionService = detectVisionService(config, DEFAULT_VISION_SERVICE);
  const availableModels = Array.isArray(modelConfig.available) ? modelConfig.available : null;
  const availableShapeOk = availableModels === null || availableModels.every(
    (model) => isRecord(model) && typeof model.provider === "string" && typeof model.model === "string",
  );
  const providers = Object.entries(providerConfig).map(([id, provider]) => {
    const providerRecord = isRecord(provider) ? provider : {};
    const options = isRecord(providerRecord.options) ? providerRecord.options : {};
    return {
      id,
      kind: typeof providerRecord.kind === "string" ? providerRecord.kind : null,
      name: typeof providerRecord.name === "string" ? providerRecord.name : null,
      base_url: typeof options.baseURL === "string" ? options.baseURL : null,
      api_key_required: Boolean(options.apiKeyRequired),
      has_api_key: typeof options.apiKey === "string" && options.apiKey.trim().length > 0,
      models: Object.keys(isRecord(providerRecord.models) ? providerRecord.models : {}).sort(),
    };
  });
  const mainModel = typeof config.model === "string"
    ? config.model
    : typeof modelConfig.main === "string"
      ? modelConfig.main
      : null;
  const liteModel = typeof modelConfig.lite === "string" ? modelConfig.lite : null;
  return {
    has_model: Boolean(mainModel),
    main_model: mainModel,
    lite_model: liteModel,
    provider_ids: providers.map((provider) => provider.id),
    providers,
    mcp_servers: mcpServers,
    vision_service: {
      configured: Boolean(visionService),
      service: DEFAULT_VISION_SERVICE,
      server: visionService?.name ?? null,
    },
    has_coding_plan_api_key: providers.some(
      (provider) => ["zai", "bigmodel"].includes(provider.id) && provider.has_api_key,
    ),
    config_shape_ok: availableShapeOk,
    diagnostics: availableShapeOk
      ? []
      : ["model.available must not be an array of strings in ZCode CLI 0.14.5 config"],
  };
}

function mcpServerEntries(config) {
  const mcpConfig = isRecord(config.mcp) ? config.mcp : {};
  if (isRecord(mcpConfig.servers)) return Object.entries(mcpConfig.servers);
  if (isRecord(config.mcpServers)) return Object.entries(config.mcpServers);
  return [];
}

function summarizeMcpServers(config) {
  return mcpServerEntries(config).map(([name, server]) => {
    const record = isRecord(server) ? server : {};
    return {
      name,
      enabled: record.enable !== false,
      type: typeof record.type === "string" ? record.type : "stdio",
      command: typeof record.command === "string" ? record.command : null,
      args_count: Array.isArray(record.args) ? record.args.length : 0,
      has_env: isRecord(record.env) && Object.keys(record.env).length > 0,
    };
  });
}

function detectVisionService(config, serviceName) {
  const normalizedService = normalizeVisionServiceName(serviceName);
  const compactService = compactVisionServiceName(serviceName);
  const allowZaiAliases = compactService === compactVisionServiceName(DEFAULT_VISION_SERVICE);
  for (const [name, server] of mcpServerEntries(config)) {
    const record = isRecord(server) ? server : {};
    if (record.enable === false) continue;
    const haystack = [
      name,
      record.command,
      ...(Array.isArray(record.args) ? record.args : []),
    ]
      .filter((item) => typeof item === "string")
      .join(" ")
      .toLowerCase();
    const normalizedHaystack = normalizeVisionServiceName(haystack);
    const compactHaystack = compactVisionServiceName(haystack);
    if (
      normalizedHaystack.includes(normalizedService)
      || compactHaystack.includes(compactService)
      || (
        allowZaiAliases
        && (
          compactHaystack.includes("zaimcpserver")
          || compactHaystack.includes("zaimcp")
          || normalizedHaystack.includes("zai-mcp")
        )
      )
    ) {
      return {
        name,
        command: typeof record.command === "string" ? record.command : null,
      };
    }
  }
  return null;
}

function normalizeVisionServiceName(value) {
  return String(value ?? "").toLowerCase().replaceAll("_", "-");
}

function compactVisionServiceName(value) {
  return String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

async function inspectMcpConfig(path, source, serviceName) {
  const exists = await pathExists(path);
  if (!exists) {
    return {
      source,
      path,
      exists: false,
      servers: [],
      vision_service: null,
    };
  }
  const config = await readJsonFileOrEmpty(path);
  return {
    source,
    path,
    exists: true,
    note: "secret values are redacted",
    servers: summarizeMcpServers(config),
    vision_service: detectVisionService(config, serviceName),
  };
}

async function inspectVisionServices(args, workspace, serviceName) {
  const configs = [];
  configs.push(await inspectMcpConfig(argsPathOrDefault(args.cliConfig, defaultCliConfigPath()), "user-cli", serviceName));
  configs.push(await inspectMcpConfig(join(workspace, ".zcode", "config.json"), "workspace-zcode", serviceName));
  configs.push(await inspectMcpConfig(join(workspace, ".agents", "mcp.json"), "workspace-agents", serviceName));
  const detected = configs.find((config) => Boolean(config.vision_service));
  return {
    ok: Boolean(detected),
    service: serviceName,
    workspace,
    detected_source: detected?.source ?? null,
    detected_server: detected?.vision_service?.name ?? null,
    configs,
    next_action: detected
      ? null
      : `Configure and enable ${serviceName} in ZCode MCP settings before running required image-understanding tasks.`,
  };
}

async function inspectCliConfig(path = defaultCliConfigPath()) {
  const exists = await pathExists(path);
  if (!exists) {
    return {
      path,
      exists: false,
      note: "CLI config does not exist",
    };
  }
  const config = await readJsonFileOrEmpty(path);
  return {
    path,
    exists: true,
    note: "secret values are redacted",
    ...redactCliConfig(config),
  };
}

async function cliPreflight(args) {
  const cliPathValue = await resolveZcodeCliPath();
  const configPath = argsPathOrDefault(args.cliConfig, defaultCliConfigPath());
  const version = await runZcodeCli(["--version"]);
  const doctorResult = await runZcodeCli(["doctor", "--json"]);
  const config = await inspectCliConfig(configPath);
  const promptReady = Boolean(
    config.exists && config.has_model && config.has_coding_plan_api_key && config.config_shape_ok,
  );
  const payload = {
    ok: version.ok && doctorResult.ok && promptReady,
    cli_path: cliPathValue,
    cli_version: version.stdout.trim() || null,
    config,
    doctor: parseJsonOrText(doctorResult.stdout),
    prompt_ready: promptReady,
  };
  if (!payload.prompt_ready) {
    payload.next_action = "Run zcodectl bootstrap-cli-config, or run ZCode CLI login/configuration before headless prompts.";
  }
  const textPayload = JSON.stringify(payload, null, 2);
  if (args.out) {
    const outputPath = resolve(args.out);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${textPayload}\n`);
  }
  console.log(textPayload);
  if (!payload.ok) process.exitCode = 1;
}

function argsPathOrDefault(path, fallback) {
  return path ? resolve(path) : fallback;
}

function normalizeModelId(model) {
  const value = String(model ?? "").trim();
  if (!value) throw new Error("model must not be empty");
  return value.toLowerCase();
}

function sourceProviderCandidates(providerId) {
  if (providerId === "zai") {
    return ["builtin:zai-coding-plan", "builtin:zai", "builtin:zai-start-plan"];
  }
  if (providerId === "bigmodel") {
    return ["builtin:bigmodel-coding-plan", "builtin:bigmodel", "builtin:bigmodel-start-plan"];
  }
  throw new Error("--provider must be zai or bigmodel");
}

function displayProviderName(providerId) {
  return providerId === "bigmodel" ? "Bigmodel Coding Plan" : "Z.AI Coding Plan";
}

function fallbackProviderBaseUrl(providerId) {
  return providerId === "bigmodel"
    ? "https://open.bigmodel.cn/api/anthropic"
    : "https://api.z.ai/api/anthropic";
}

function pickSourceProvider(guiConfig, providerId) {
  const providers = isRecord(guiConfig.provider) ? guiConfig.provider : {};
  for (const id of sourceProviderCandidates(providerId)) {
    const provider = providers[id];
    if (!isRecord(provider)) continue;
    const options = isRecord(provider.options) ? provider.options : {};
    const apiKey = typeof options.apiKey === "string" ? options.apiKey.trim() : "";
    if (!apiKey) continue;
    return { id, provider, options, apiKey };
  }
  throw new Error(`No ${providerId} API key found in GUI config`);
}

function normalizedSourceModelIds(sourceProvider, preferredModels) {
  const sourceModels = isRecord(sourceProvider.models) ? sourceProvider.models : {};
  const ids = new Set(preferredModels.map(normalizeModelId));
  for (const model of Object.keys(sourceModels)) ids.add(normalizeModelId(model));
  return [...ids];
}

function modelDisplayName(modelId) {
  return modelId
    .split("-")
    .map((part) => (part === "glm" ? "GLM" : part.toUpperCase()))
    .join("-");
}

async function bootstrapCliConfig(args) {
  const providerId = args.provider ?? "zai";
  const mainModelId = normalizeModelId(args.model ?? "glm-5.2");
  const sourceConfigPath = argsPathOrDefault(args.sourceConfig, defaultGuiConfigPath());
  const cliConfigPath = argsPathOrDefault(args.cliConfig, defaultCliConfigPath());
  const existedBefore = await pathExists(cliConfigPath);
  const guiConfig = await readJsonFile(sourceConfigPath);
  if (!isRecord(guiConfig)) throw new Error(`GUI config must be a JSON object: ${sourceConfigPath}`);
  const source = pickSourceProvider(guiConfig, providerId);
  const existing = await readJsonFileOrEmpty(cliConfigPath);
  const providerConfig = isRecord(existing.provider) ? existing.provider : {};
  const existingProvider = isRecord(providerConfig[providerId]) ? providerConfig[providerId] : {};
  const existingOptions = isRecord(existingProvider.options) ? existingProvider.options : {};
  const existingModels = isRecord(existingProvider.models) ? existingProvider.models : {};
  const sourceBaseUrl = typeof source.options.baseURL === "string" && source.options.baseURL.trim()
    ? source.options.baseURL.trim()
    : fallbackProviderBaseUrl(providerId);
  const sourceModelIds = normalizedSourceModelIds(source.provider, [mainModelId]);
  const liteModelId = args.liteModel
    ? normalizeModelId(args.liteModel)
    : sourceModelIds.includes("glm-5-turbo")
      ? "glm-5-turbo"
      : null;
  const preferredModelIds = liteModelId ? [mainModelId, liteModelId, ...sourceModelIds] : [mainModelId, ...sourceModelIds];
  const modelIds = [...new Set(preferredModelIds)];
  const models = { ...existingModels };
  for (const modelId of modelIds) {
    models[modelId] = {
      ...(isRecord(models[modelId]) ? models[modelId] : {}),
      name: isRecord(models[modelId]) && typeof models[modelId].name === "string"
        ? models[modelId].name
        : modelDisplayName(modelId),
    };
  }
  const modelConfig = isRecord(existing.model) ? { ...existing.model } : {};
  modelConfig.main = `${providerId}/${mainModelId}`;
  if (liteModelId) modelConfig.lite = `${providerId}/${liteModelId}`;
  delete modelConfig.available;
  const nextConfig = {
    ...existing,
    provider: {
      ...providerConfig,
      [providerId]: {
        ...existingProvider,
        kind: typeof source.provider.kind === "string" ? source.provider.kind : "anthropic",
        name: typeof source.provider.name === "string" ? source.provider.name : displayProviderName(providerId),
        options: {
          ...existingOptions,
          apiKeyRequired: true,
          baseURL: sourceBaseUrl,
          apiKey: source.apiKey,
        },
        models,
      },
    },
    model: modelConfig,
  };
  if (!args.dryRun) await writeJsonFileAtomic(cliConfigPath, nextConfig);
  const payload = {
    ok: true,
    dry_run: Boolean(args.dryRun),
    cli_config: {
      path: cliConfigPath,
      existed_before: existedBefore,
      wrote_file: !args.dryRun,
      permissions: args.dryRun ? null : "0600",
    },
    source: {
      path: sourceConfigPath,
      provider_id: source.id,
      base_url: sourceBaseUrl,
      has_api_key: true,
    },
    target: {
      provider_id: providerId,
      main_model: modelConfig.main,
      lite_model: modelConfig.lite ?? null,
      configured_models: modelIds.map((modelId) => `${providerId}/${modelId}`),
    },
    secret_handling: "API key copied locally from GUI config to CLI config; secret values were not printed.",
    preflight: redactCliConfig(nextConfig),
  };
  const textPayload = JSON.stringify(payload, null, 2);
  if (!args.quiet && args.out) {
    const outputPath = resolve(args.out);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${textPayload}\n`);
  }
  if (!args.quiet) console.log(textPayload);
  return payload;
}

async function ensureCliPromptReady(args) {
  if (args.noBootstrap) return;
  const config = await inspectCliConfig(argsPathOrDefault(args.cliConfig, defaultCliConfigPath()));
  if (config.exists && config.has_model && config.has_coding_plan_api_key && config.config_shape_ok) return;
  await bootstrapCliConfig({
    provider: args.provider,
    model: args.model,
    liteModel: args.liteModel,
    sourceConfig: args.sourceConfig,
    cliConfig: args.cliConfig,
    dryRun: false,
    quiet: true,
  });
}

function parseJsonOrText(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function parseJsonObject(raw) {
  const parsed = parseJsonOrText(raw);
  return isRecord(parsed) ? parsed : null;
}

function finiteNumber(value) {
  if (value === null || value === undefined || typeof value === "boolean") return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    const number = finiteNumber(value);
    if (number !== null) return number;
  }
  return null;
}

function tailText(value, max = 2000) {
  return String(value ?? "").slice(-max);
}

function normalizedZcodeUsageFromStdout(stdout) {
  const payload = parseJsonObject(stdout);
  const usage = isRecord(payload?.usage) ? payload.usage : null;
  if (!usage) {
    return {
      payload,
      usage: null,
      normalized: null,
      projection: isRecord(payload?.projection) ? payload.projection : null,
      response: payload?.response ?? null,
    };
  }
  const normalized = {
    total_tokens: firstFiniteNumber(usage.totalTokens, usage.total_tokens, usage.tokens_total, usage.tokensUsed),
    input_tokens: firstFiniteNumber(usage.inputTokens, usage.input_tokens),
    output_tokens: firstFiniteNumber(usage.outputTokens, usage.output_tokens),
    cache_read_tokens: firstFiniteNumber(usage.cacheReadTokens, usage.cache_read_tokens),
    cache_write_tokens: firstFiniteNumber(usage.cacheWriteTokens, usage.cache_write_tokens),
  };
  return {
    payload,
    usage,
    normalized,
    projection: isRecord(payload?.projection) ? payload.projection : null,
    response: payload?.response ?? null,
  };
}

function usageSnapshotMode(args) {
  const mode = String(
    args.usageSnapshotSource ?? process.env.ZCODE_USAGE_SNAPSHOT_SOURCE ?? "auto",
  ).trim().toLowerCase();
  if (["off", "false", "0"].includes(mode)) return "none";
  if (["auto", "zai-api", "codexbar", "none"].includes(mode)) return mode;
  throw new Error("--usage-snapshot-source must be auto, zai-api, codexbar, or none");
}

function usageProvider(args) {
  return args.usageProvider ?? process.env.ZCODE_USAGE_PROVIDER ?? DEFAULT_USAGE_PROVIDER;
}

function codexBarPath(args) {
  return args.codexbarPath ?? process.env.CODEXBAR_PATH ?? "codexbar";
}

function zaiQuotaUrl(args) {
  return args.zaiQuotaUrl ?? process.env.ZCODE_ZAI_QUOTA_URL ?? DEFAULT_ZAI_QUOTA_URL;
}

function isoFromEpochMillis(value) {
  const number = finiteNumber(value);
  if (number === null || number <= 0) return null;
  const millis = number > 10_000_000_000 ? number : number * 1000;
  const date = new Date(millis);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function providerApiKeyFromConfig(config, providerId) {
  const providers = isRecord(config.provider) ? config.provider : {};
  const provider = isRecord(providers[providerId]) ? providers[providerId] : {};
  const options = isRecord(provider.options) ? provider.options : {};
  const apiKey = typeof options.apiKey === "string" ? options.apiKey.trim() : "";
  return apiKey || null;
}

async function launchctlGetenv(name) {
  try {
    const { stdout } = await execFileAsync("launchctl", ["getenv", name], {
      maxBuffer: 1024 * 1024,
      timeout: 5000,
    });
    return stdout.trim() || null;
  } catch {
    return null;
  }
}

async function resolveZaiQuotaApiKey(args) {
  const envKey = typeof process.env.ZAI_API_KEY === "string" ? process.env.ZAI_API_KEY.trim() : "";
  if (envKey) return { ok: true, api_key: envKey, source: "env:ZAI_API_KEY" };
  const launchctlKey = await launchctlGetenv("ZAI_API_KEY");
  if (launchctlKey) return { ok: true, api_key: launchctlKey, source: "launchctl:ZAI_API_KEY" };
  const cliConfigPath = argsPathOrDefault(args.cliConfig, defaultCliConfigPath());
  try {
    const cliConfig = await readJsonFileOrEmpty(cliConfigPath);
    const apiKey = providerApiKeyFromConfig(cliConfig, "zai");
    if (apiKey) return { ok: true, api_key: apiKey, source: "zcode-cli-config" };
  } catch (error) {
    return { ok: false, source: "zcode-cli-config", error: error.message };
  }
  return { ok: false, source: "zcode-cli-config", error: "ZAI_API_KEY not found" };
}

function normalizeCodexBarWindow(name, value) {
  if (!isRecord(value)) return null;
  return {
    name,
    used_percent: finiteNumber(value.usedPercent ?? value.used_percent),
    reset_description: typeof value.resetDescription === "string" ? value.resetDescription : null,
    resets_at: typeof value.resetsAt === "string" ? value.resetsAt : null,
    window_minutes: firstFiniteNumber(value.windowMinutes, value.window_minutes),
  };
}

function normalizeCodexBarPayload(payload, provider) {
  const rows = Array.isArray(payload) ? payload : isRecord(payload) ? [payload] : [];
  const row = rows.find((item) => item?.provider === provider) ?? rows[0] ?? null;
  const usage = isRecord(row?.usage) ? row.usage : {};
  const windows = {};
  for (const name of ["primary", "secondary", "tertiary"]) {
    const normalized = normalizeCodexBarWindow(name, usage[name]);
    if (normalized) windows[name] = normalized;
  }
  const quotaCandidates = Object.values(windows)
    .filter((window) => window.used_percent !== null)
    .map((window) => ({
      name: window.name,
      value: window.used_percent,
      line: `${window.name}.usedPercent (${window.reset_description ?? "quota window"})`,
    }));
  const best = quotaCandidates[0] ?? null;
  return {
    identity: isRecord(usage.identity) ? usage.identity : {},
    codexbar_source: typeof row?.source === "string" ? row.source : null,
    updated_at: typeof usage.updatedAt === "string" ? usage.updatedAt : null,
    windows,
    best: {
      tokens_total: null,
      tokens_line: null,
      quota_percent: best?.value ?? null,
      quota_percent_line: best?.line ?? null,
    },
    token_candidates: [],
    quota_percent_candidates: quotaCandidates,
  };
}

function normalizeZaiLimit(name, limit) {
  if (!isRecord(limit)) return null;
  const rawUsedPercent = finiteNumber(limit.percentage ?? limit.usedPercent ?? limit.used_percent);
  const usage = finiteNumber(limit.usage);
  const remaining = finiteNumber(limit.remaining);
  const tokenCountsAvailable = usage !== null && remaining !== null;
  const authoritative = rawUsedPercent !== null;
  const unavailableReason = rawUsedPercent === null ? "zai_limit_missing_percentage" : null;
  return {
    name,
    type: typeof limit.type === "string" ? limit.type : null,
    used_percent: rawUsedPercent,
    raw_used_percent: rawUsedPercent,
    non_authoritative_used_percent: null,
    authoritative,
    token_counts_available: tokenCountsAvailable,
    quota_percent_unavailable_reason: unavailableReason,
    reset_description: name === "primary" ? "Tokens limit" : "Time limit",
    resets_at: isoFromEpochMillis(limit.nextResetTime ?? limit.resetsAt ?? limit.resets_at),
    usage,
    remaining,
  };
}

function normalizeZaiApiPayload(payload, provider) {
  const data = isRecord(payload?.data) ? payload.data : {};
  const limits = Array.isArray(data.limits) ? data.limits : [];
  const byType = new Map(limits.filter(isRecord).map((limit) => [limit.type, limit]));
  const candidates = [
    ["primary", byType.get("TOKENS_LIMIT")],
    ["secondary", byType.get("TIME_LIMIT")],
  ];
  const windows = {};
  for (const [name, limit] of candidates) {
    const normalized = normalizeZaiLimit(name, limit);
    if (normalized) windows[name] = normalized;
  }
  const primaryWindow = windows.primary ?? null;
  const quotaCandidates = primaryWindow && primaryWindow.used_percent !== null
    ? [
      {
        name: primaryWindow.name,
        value: primaryWindow.used_percent,
        line: `${primaryWindow.type ?? primaryWindow.name}.percentage (${primaryWindow.reset_description})`,
      },
    ]
    : [];
  const rawQuotaCandidates = Object.values(windows)
    .filter((window) => window.raw_used_percent !== null)
    .map((window) => ({
      name: window.name,
      value: window.raw_used_percent,
      line: `${window.type ?? window.name}.percentage (${window.reset_description})`,
      authoritative: window.authoritative !== false,
      unavailable_reason: window.quota_percent_unavailable_reason ?? null,
    }));
  const best = quotaCandidates[0] ?? null;
  const rawBest = rawQuotaCandidates[0] ?? null;
  return {
    identity: { providerID: provider },
    plan: typeof data.level === "string" ? data.level : null,
    windows,
    best: {
      tokens_total: null,
      tokens_line: null,
      quota_percent: best?.value ?? null,
      quota_percent_line: best?.line ?? null,
      raw_quota_percent: rawBest?.value ?? null,
      quota_percent_authoritative: Boolean(best),
      quota_percent_unavailable_reason: best ? null : primaryWindow?.quota_percent_unavailable_reason ?? null,
    },
    token_candidates: [],
    quota_percent_candidates: quotaCandidates,
    quota_percent_raw_candidates: rawQuotaCandidates,
  };
}

async function captureCodexBarUsageSnapshot(args, phase) {
  const mode = usageSnapshotMode(args);
  const provider = usageProvider(args);
  if (mode === "none") {
    return { ok: false, phase, source: "none", provider, reason: "disabled" };
  }
  const startedAt = new Date().toISOString();
  const command = codexBarPath(args);
  const timeoutMs = positiveIntOrDefault(args.usageSnapshotTimeoutMs, DEFAULT_USAGE_SNAPSHOT_TIMEOUT_MS);
  try {
    const { stdout, stderr } = await execFileAsync(
      command,
      ["usage", "--provider", provider, "--format", "json"],
      {
        maxBuffer: 5 * 1024 * 1024,
        timeout: timeoutMs,
      },
    );
    const payload = JSON.parse(stdout);
    return {
      ok: true,
      phase,
      source: "codexbar",
      provider,
      captured_at: startedAt,
      command,
      stderr_tail: tailText(stderr, 1000),
      raw: payload,
      ...normalizeCodexBarPayload(payload, provider),
    };
  } catch (error) {
    const isMissing = error.code === "ENOENT";
    return {
      ok: false,
      phase,
      source: "codexbar",
      provider,
      captured_at: startedAt,
      command,
      error_type: isMissing ? "not_found" : "command_failed",
      exit_code: typeof error.code === "number" ? error.code : null,
      message: error.message,
      stdout_tail: tailText(error.stdout, 1000),
      stderr_tail: tailText(error.stderr, 1000),
      auto_mode: mode === "auto",
    };
  }
}

function snapshotFailure({ phase, source, provider, startedAt, errorType, message, extra = {} }) {
  return {
    ok: false,
    phase,
    source,
    provider,
    captured_at: startedAt,
    error_type: errorType,
    message,
    ...extra,
  };
}

async function captureZaiApiUsageSnapshot(args, phase) {
  const provider = usageProvider(args);
  const startedAt = new Date().toISOString();
  if (provider !== "zai") {
    return snapshotFailure({
      phase,
      source: "zai-api",
      provider,
      startedAt,
      errorType: "unsupported_provider",
      message: "Z.AI quota API snapshots require --usage-provider zai",
    });
  }
  const credential = await resolveZaiQuotaApiKey(args);
  if (!credential.ok) {
    return snapshotFailure({
      phase,
      source: "zai-api",
      provider,
      startedAt,
      errorType: "missing_api_key",
      message: credential.error,
      extra: { credential_source: credential.source },
    });
  }
  return fetchZaiApiUsageSnapshot(args, phase, provider, startedAt, credential);
}

async function fetchZaiApiUsageSnapshot(args, phase, provider, startedAt, credential) {
  const timeoutMs = positiveIntOrDefault(args.usageSnapshotTimeoutMs, DEFAULT_USAGE_SNAPSHOT_TIMEOUT_MS);
  const url = zaiQuotaUrl(args);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${credential.api_key}`,
        "Content-Type": "application/json",
      },
      signal: controller.signal,
    });
    const text = await response.text();
    const payload = parseJsonOrText(text);
    if (!response.ok) {
      return snapshotFailure({
        phase,
        source: "zai-api",
        provider,
        startedAt,
        errorType: "http_error",
        message: `HTTP ${response.status}`,
        extra: { status_code: response.status, body_tail: tailText(text, 1000) },
      });
    }
    if (!isRecord(payload)) {
      return snapshotFailure({
        phase,
        source: "zai-api",
        provider,
        startedAt,
        errorType: "invalid_json",
        message: "Z.AI quota API response was not a JSON object",
      });
    }
    if (payload.code !== undefined && payload.code !== 200) {
      return snapshotFailure({
        phase,
        source: "zai-api",
        provider,
        startedAt,
        errorType: "api_error",
        message: `Z.AI quota API returned code ${payload.code}`,
        extra: { body_tail: tailText(text, 1000) },
      });
    }
    return {
      ok: true,
      phase,
      source: "zai-api",
      provider,
      captured_at: startedAt,
      credential_source: credential.source,
      raw: payload,
      ...normalizeZaiApiPayload(payload, provider),
    };
  } catch (error) {
    return snapshotFailure({
      phase,
      source: "zai-api",
      provider,
      startedAt,
      errorType: error.name === "AbortError" ? "timeout" : "request_failed",
      message: error.message,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function captureUsageSnapshot(args, phase) {
  const mode = usageSnapshotMode(args);
  const provider = usageProvider(args);
  if (mode === "none") return { ok: false, phase, source: "none", provider, reason: "disabled" };
  if (mode === "zai-api") return captureZaiApiUsageSnapshot(args, phase);
  if (mode === "codexbar") return captureCodexBarUsageSnapshot(args, phase);
  const direct = await captureZaiApiUsageSnapshot(args, phase);
  if (direct.ok) return direct;
  const fallback = await captureCodexBarUsageSnapshot(args, phase);
  return fallback.ok
    ? { ...fallback, fallback_from: { source: direct.source, error_type: direct.error_type, message: direct.message } }
    : { ...fallback, fallback_from: direct };
}

function deriveQuotaWindowDelta(beforeWindow, afterWindow) {
  const before = finiteNumber(beforeWindow?.used_percent);
  const after = finiteNumber(afterWindow?.used_percent);
  const beforeAuthoritative = beforeWindow?.authoritative !== false;
  const afterAuthoritative = afterWindow?.authoritative !== false;
  const authoritative = beforeAuthoritative && afterAuthoritative;
  const resetChanged = Boolean(beforeWindow?.resets_at && afterWindow?.resets_at && beforeWindow.resets_at !== afterWindow.resets_at);
  const rawDelta = before !== null && after !== null ? after - before : null;
  const unavailableReason = !authoritative
    ? beforeWindow?.quota_percent_unavailable_reason
      ?? afterWindow?.quota_percent_unavailable_reason
      ?? "quota_percent_window_non_authoritative"
    : before === null || after === null
      ? "quota_percent_window_missing_used_percent"
      : resetChanged
        ? "quota_window_reset_changed"
        : rawDelta < 0
          ? "quota_percent_delta_negative"
          : null;
  const usedDelta = rawDelta !== null && rawDelta >= 0 && !resetChanged && authoritative
    ? Number(rawDelta.toFixed(4))
    : null;
  return {
    before_used_percent: before,
    after_used_percent: after,
    before_raw_used_percent: finiteNumber(beforeWindow?.raw_used_percent),
    after_raw_used_percent: finiteNumber(afterWindow?.raw_used_percent),
    used_percent_delta: usedDelta,
    authoritative,
    quota_percent_unavailable_reason: usedDelta === null ? unavailableReason : null,
    reset_changed: resetChanged,
    before_resets_at: beforeWindow?.resets_at ?? null,
    after_resets_at: afterWindow?.resets_at ?? null,
    reset_description: afterWindow?.reset_description ?? beforeWindow?.reset_description ?? null,
  };
}

function deriveQuotaUsage(beforeSnapshot, afterSnapshot) {
  const available = Boolean(beforeSnapshot?.ok && afterSnapshot?.ok);
  const sources = new Set([beforeSnapshot?.source, afterSnapshot?.source].filter(Boolean));
  const result = {
    available,
    source: available ? (sources.size === 1 ? [...sources][0] : "mixed") : null,
    provider: afterSnapshot?.provider ?? beforeSnapshot?.provider ?? null,
    quota_percent_direction: "used",
    quota_percent_before: null,
    quota_percent_after: null,
    quota_percent_used: null,
    quota_percent_status: "unavailable",
    quota_percent_unavailable_reason: available ? null : "usage_snapshot_unavailable",
    windows: {},
  };
  if (!available) return result;
  const names = new Set([
    ...Object.keys(beforeSnapshot.windows ?? {}),
    ...Object.keys(afterSnapshot.windows ?? {}),
  ]);
  for (const name of names) {
    result.windows[name] = deriveQuotaWindowDelta(
      beforeSnapshot.windows?.[name],
      afterSnapshot.windows?.[name],
    );
  }
  const primary = result.windows.primary ?? Object.values(result.windows)[0] ?? null;
  if (primary) {
    result.quota_percent_before = primary.before_used_percent;
    result.quota_percent_after = primary.after_used_percent;
    result.quota_percent_used = primary.used_percent_delta;
    result.quota_percent_status = primary.used_percent_delta !== null ? "measured" : "unavailable";
    result.quota_percent_unavailable_reason = primary.used_percent_delta !== null
      ? null
      : primary.quota_percent_unavailable_reason ?? "quota_percent_delta_unavailable";
  } else {
    result.quota_percent_unavailable_reason = "quota_percent_window_unavailable";
  }
  return result;
}

function missingUsageReason(finalResult) {
  if (finalResult?.provider_error) return "provider_error_without_zcode_cli_usage";
  if (finalResult?.cli_ok === false || finalResult?.ok === false) return "zcode_cli_result_missing_usage";
  return "zcode_cli_usage_missing";
}

function buildUsageAccounting(finalResult, beforeSnapshot, afterSnapshot) {
  const runUsage = normalizedZcodeUsageFromStdout(finalResult?.stdout ?? "");
  const quota = deriveQuotaUsage(beforeSnapshot, afterSnapshot);
  const usageAvailable = Boolean(runUsage.normalized);
  return {
    usage_available: usageAvailable,
    no_usage_reason: usageAvailable ? null : missingUsageReason(finalResult),
    tokens_source: runUsage.normalized ? "zcode_cli_json_usage" : null,
    tokens_used: runUsage.normalized?.total_tokens ?? null,
    tokens_total: runUsage.normalized?.total_tokens ?? null,
    input_tokens: runUsage.normalized?.input_tokens ?? null,
    output_tokens: runUsage.normalized?.output_tokens ?? null,
    cache_read_tokens: runUsage.normalized?.cache_read_tokens ?? null,
    cache_write_tokens: runUsage.normalized?.cache_write_tokens ?? null,
    quota_source: quota.source,
    quota_provider: quota.provider,
    quota_percent_direction: quota.quota_percent_direction,
    quota_percent_before: quota.quota_percent_before,
    quota_percent_after: quota.quota_percent_after,
    quota_percent_used: quota.quota_percent_used,
    quota_percent_status: quota.quota_percent_status,
    quota_percent_unavailable_reason: quota.quota_percent_unavailable_reason,
    quota_windows: quota.windows,
  };
}

function mapMode(mode) {
  const mapping = {
    "Plan": "plan",
    "Auto Edit": "edit",
    "Full Access": "yolo",
    "Confirm Before Changes": "build",
  };
  return mapping[mode] ?? mode ?? "plan";
}

function positiveIntOrDefault(value, fallback) {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function nonNegativeIntOrDefault(value, fallback) {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function resolveWorkspacePath(workspace, relativePath) {
  const root = resolve(workspace);
  const absolute = resolve(root, relativePath);
  if (absolute !== root && !absolute.startsWith(`${root}/`)) {
    throw new Error(`packet vision image escapes workspace: ${relativePath}`);
  }
  return absolute;
}

function isSecretLikePath(path) {
  const lowered = String(path).toLowerCase();
  return SECRET_PATH_NEEDLES.some((needle) => lowered.includes(needle));
}

function resolveVisionAttachment(workspace, relativePath) {
  if (!relativePath || typeof relativePath !== "string") {
    throw new Error("packet vision image path must be a non-empty string");
  }
  if (isSecretLikePath(relativePath)) {
    throw new Error(`secret-like vision attachment is not allowed: ${relativePath}`);
  }
  const absolute = resolveWorkspacePath(workspace, relativePath);
  if (isSecretLikePath(absolute)) {
    throw new Error(`secret-like vision attachment is not allowed: ${relativePath}`);
  }
  if (!IMAGE_EXTENSIONS.has(extname(absolute).toLowerCase())) {
    throw new Error(`packet vision attachment must be an image file: ${relativePath}`);
  }
  return absolute;
}

function packetVision(packet, workspace) {
  const rawVision = isRecord(packet.vision) ? packet.vision : {};
  const imageFiles = Array.isArray(rawVision.image_files)
    ? rawVision.image_files.filter((item) => typeof item === "string")
    : [];
  const service = typeof rawVision.service === "string" && rawVision.service.trim()
    ? rawVision.service.trim()
    : DEFAULT_VISION_SERVICE;
  return {
    required: Boolean(rawVision.required),
    service,
    image_files: imageFiles,
    attached_files: imageFiles.map((item) => resolveVisionAttachment(workspace, item)),
    model_limit: rawVision.model_limit ?? null,
  };
}

async function missingVisionAttachment(vision) {
  for (const path of vision.attached_files) {
    if (!(await pathExists(path))) return path;
  }
  return null;
}

async function normalizeVisionAttachmentTargets(vision, workspace) {
  const realWorkspace = await realpath(workspace);
  const attachedFiles = [];
  for (let index = 0; index < vision.attached_files.length; index += 1) {
    const path = vision.attached_files[index];
    const rel = vision.image_files[index] ?? path;
    const target = await realpath(path);
    if (target !== realWorkspace && !target.startsWith(`${realWorkspace}/`)) {
      throw new Error(`packet vision attachment target escapes workspace: ${rel}`);
    }
    if (isSecretLikePath(target)) {
      throw new Error(`secret-like vision attachment target is not allowed: ${rel}`);
    }
    if (!IMAGE_EXTENSIONS.has(extname(target).toLowerCase())) {
      throw new Error(`packet vision attachment target must be an image file: ${rel}`);
    }
    attachedFiles.push(target);
  }
  return {
    ...vision,
    attached_files: attachedFiles,
  };
}

async function readFileHeader(path, byteCount = 16) {
  const handle = await open(path, "r");
  try {
    const buffer = Buffer.alloc(byteCount);
    const { bytesRead } = await handle.read(buffer, 0, byteCount, 0);
    return buffer.subarray(0, bytesRead);
  } finally {
    await handle.close();
  }
}

function hasImageSignature(path, header) {
  const extension = extname(path).toLowerCase();
  if (extension === ".png") {
    return header.length >= 8 && header.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]));
  }
  if (extension === ".jpg" || extension === ".jpeg") {
    return header.length >= 3 && header[0] === 0xFF && header[1] === 0xD8 && header[2] === 0xFF;
  }
  if (extension === ".gif") {
    const marker = header.subarray(0, 6).toString("ascii");
    return marker === "GIF87a" || marker === "GIF89a";
  }
  if (extension === ".webp") {
    return header.length >= 12
      && header.subarray(0, 4).toString("ascii") === "RIFF"
      && header.subarray(8, 12).toString("ascii") === "WEBP";
  }
  if (extension === ".bmp") {
    return header.length >= 2 && header[0] === 0x42 && header[1] === 0x4D;
  }
  return false;
}

async function invalidVisionAttachmentContent(vision) {
  for (let index = 0; index < vision.attached_files.length; index += 1) {
    const path = vision.attached_files[index];
    const header = await readFileHeader(path);
    if (!hasImageSignature(path, header)) {
      return `packet vision attachment is not a valid image file: ${vision.image_files[index] ?? path}`;
    }
  }
  return null;
}

function shouldRunVisionPreflight(mode, vision) {
  if (mode === "off") return false;
  if (mode === "required") return true;
  return vision.required;
}

async function buildVisionRunEnv(args, vision, visionPreflight) {
  if (!vision.required || !visionPreflight?.ok) return { env: {}, credential_source: null };
  if (process.env.Z_AI_API_KEY || process.env.ZAI_API_KEY) {
    const legacyKey = process.env.Z_AI_API_KEY ? null : process.env.ZAI_API_KEY;
    return {
      env: {
        Z_AI_MODE: process.env.Z_AI_MODE ?? "ZAI",
        ...(legacyKey ? { Z_AI_API_KEY: legacyKey } : {}),
      },
      credential_source: process.env.Z_AI_API_KEY ? "env:Z_AI_API_KEY" : "env:ZAI_API_KEY",
    };
  }
  const credential = await resolveZaiQuotaApiKey(args);
  if (!credential.ok || !credential.api_key) {
    return { env: {}, credential_source: null, error: credential.error ?? "Z_AI_API_KEY not found" };
  }
  return {
    env: {
      Z_AI_MODE: process.env.Z_AI_MODE ?? "ZAI",
      Z_AI_API_KEY: credential.api_key,
    },
    credential_source: credential.source,
  };
}

async function printJsonPayload(payload, out) {
  const textPayload = JSON.stringify(payload, null, 2);
  if (out) {
    const outputPath = resolve(out);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${textPayload}\n`);
  }
  console.log(textPayload);
  if (!payload.ok) process.exitCode = payload.exit_code ?? 1;
}

function buildPromptArgs(args, promptText, workspace) {
  const cliArgs = ["--cwd", workspace, "--prompt", promptText, "--mode", mapMode(args.mode), "--no-color"];
  if (args.json) cliArgs.push("--json");
  if (args.continue) cliArgs.push("--continue");
  if (args.resume) cliArgs.push("--resume", args.resume);
  if (args.target) cliArgs.push("--target", args.target);
  if (args.targetReplace) cliArgs.push("--target-replace");
  for (const item of args.attach ?? []) cliArgs.push("--attach", resolve(item));
  return cliArgs;
}

async function runSupervisorJson(supervisorArgs, options = {}) {
  try {
    const { stdout, stderr } = await execFileAsync("python3", [SUPERVISOR_SCRIPT, ...supervisorArgs], {
      cwd: options.cwd ?? process.cwd(),
      maxBuffer: 25 * 1024 * 1024,
      timeout: options.timeoutMs ?? undefined,
    });
    const payload = parseJsonOrText(stdout);
    return isRecord(payload) ? { ...payload, command_exit_code: 0, command_stderr: stderr } : payload;
  } catch (error) {
    const payload = parseJsonOrText(error.stdout ?? "");
    if (isRecord(payload)) {
      return {
        ...payload,
        command_exit_code: typeof error.code === "number" ? error.code : 1,
        command_stderr: error.stderr ?? "",
      };
    }
    throw error;
  }
}

async function createRunPacketSnapshot(workspace) {
  const snapshotPath = join(tmpdir(), `zcode-run-packet-${process.pid}-${randomUUID()}.json`);
  await runSupervisorJson(["snapshot", "--workspace", workspace, "--out", snapshotPath], { cwd: workspace });
  return snapshotPath;
}

async function auditRunPacketAttempt({ workspace, packetPath, snapshotPath, validationTimeout }) {
  return runSupervisorJson(
    [
      "audit",
      "--workspace",
      workspace,
      "--snapshot",
      snapshotPath,
      "--packet",
      packetPath,
      "--validation-timeout",
      String(validationTimeout ?? 60),
    ],
    { cwd: workspace },
  );
}

function compactAttemptRecord(attempt, index) {
  const runUsage = normalizedZcodeUsageFromStdout(attempt.stdout ?? "");
  const usageAvailable = Boolean(runUsage.normalized);
  return {
    attempt: index + 1,
    cli_ok: attempt.cli_ok,
    exit_code: attempt.exit_code,
    provider_error: attempt.provider_error,
    provider_code: attempt.provider_code,
    provider_message: attempt.provider_message,
    provider_id: attempt.provider_id,
    provider_kind: attempt.provider_kind,
    retryable_provider_error: attempt.retryable_provider_error,
    usage_available: usageAvailable,
    no_usage_reason: usageAvailable ? null : missingUsageReason(attempt),
    tokens_total: runUsage.normalized?.total_tokens ?? null,
    supervisor_state: attempt.supervisor_state,
    changed_count: attempt.audit?.changed_count ?? null,
    validation_ok: attempt.audit?.validation?.ok ?? null,
    audit_ok: attempt.audit?.ok ?? null,
  };
}

function sleep(ms) {
  return new Promise((resolveSleep) => setTimeout(resolveSleep, ms));
}

async function cliPrompt(args) {
  await ensureCliPromptReady(args);
  const promptText = await readPrompt(args);
  const workspace = resolve(args.workspace ?? process.cwd());
  const cliArgs = buildPromptArgs(args, promptText, workspace);
  const result = await runZcodeCli(cliArgs, {
    cwd: workspace,
    timeoutMs: args.timeoutMs ?? PROMPT_TIMEOUT_MS,
  });
  await printCliResult(result, args.out);
}

async function visionPreflightCommand(args) {
  const workspace = resolve(args.workspace ?? process.cwd());
  const serviceName = args.visionService ?? DEFAULT_VISION_SERVICE;
  const payload = await inspectVisionServices(args, workspace, serviceName);
  await printJsonPayload(payload, args.out);
}

async function runPacket(args) {
  if (!args.packet) throw new Error("--packet is required");
  const packetPath = resolve(args.packet);
  const packet = JSON.parse(await readFile(packetPath, "utf8"));
  if (!packet.prompt) throw new Error(`packet is missing prompt: ${packetPath}`);
  const workspace = resolve(packet.workspace);
  let vision;
  try {
    vision = packetVision(packet, workspace);
  } catch (error) {
    await printJsonPayload(
      {
        ok: false,
        exit_code: 1,
        status: "vision_attachment_invalid",
        supervisor_state: "vision_attachment_invalid",
        packet: packetPath,
        workspace,
        error: error.message,
      },
      args.out,
    );
    return;
  }
  const missingAttachment = await missingVisionAttachment(vision);
  if (missingAttachment) {
    await printJsonPayload(
      {
        ok: false,
        exit_code: 1,
        status: "vision_attachment_missing",
        supervisor_state: "vision_attachment_missing",
        packet: packetPath,
        workspace,
        vision,
        error: `vision attachment does not exist: ${missingAttachment}`,
      },
      args.out,
    );
    return;
  }
  try {
    vision = await normalizeVisionAttachmentTargets(vision, workspace);
  } catch (error) {
    await printJsonPayload(
      {
        ok: false,
        exit_code: 1,
        status: "vision_attachment_invalid",
        supervisor_state: "vision_attachment_invalid",
        packet: packetPath,
        workspace,
        vision,
        error: error.message,
      },
      args.out,
    );
    return;
  }
  const invalidAttachment = await invalidVisionAttachmentContent(vision);
  if (invalidAttachment) {
    await printJsonPayload(
      {
        ok: false,
        exit_code: 1,
        status: "vision_attachment_invalid",
        supervisor_state: "vision_attachment_invalid",
        packet: packetPath,
        workspace,
        vision,
        error: invalidAttachment,
      },
      args.out,
    );
    return;
  }
  const visionPreflightMode = args.visionPreflight ?? "auto";
  if (!["auto", "required", "off"].includes(visionPreflightMode)) {
    throw new Error("--vision-preflight must be auto, required, or off");
  }
  const visionPreflight = shouldRunVisionPreflight(visionPreflightMode, vision)
    ? await inspectVisionServices(args, workspace, vision.service)
    : null;
  const visionPreflightRequired = vision.required || visionPreflightMode === "required";
  if (visionPreflightRequired && visionPreflightMode !== "off" && visionPreflight && !visionPreflight.ok) {
    await printJsonPayload(
      {
        ok: false,
        cli_ok: false,
        exit_code: 1,
        status: "vision_service_unavailable",
        supervisor_state: "vision_service_unavailable",
        packet: packetPath,
        workspace,
        vision,
        vision_preflight: visionPreflight,
        next_action: visionPreflight.next_action,
      },
      args.out,
    );
    return;
  }
  const visionRunEnv = await buildVisionRunEnv(args, vision, visionPreflight);
  if (vision.required && visionPreflight?.ok && visionRunEnv.error) {
    await printJsonPayload(
      {
        ok: false,
        cli_ok: false,
        exit_code: 1,
        status: "vision_service_credentials_unavailable",
        supervisor_state: "vision_service_credentials_unavailable",
        packet: packetPath,
        workspace,
        vision,
        vision_preflight: visionPreflight,
        error: visionRunEnv.error,
        next_action: "Set Z_AI_API_KEY or configure the Z.AI API key in the ZCode CLI config before required image-understanding tasks.",
      },
      args.out,
    );
    return;
  }
  await ensureCliPromptReady(args);
  const cliArgs = buildPromptArgs(
    {
      ...args,
      mode: args.mode ?? packet.mode,
      text: packet.prompt,
      textFile: undefined,
      attach: [...(args.attach ?? []), ...vision.attached_files],
    },
    packet.prompt,
    workspace,
  );
  const maxAttempts = positiveIntOrDefault(args.maxAttempts, DEFAULT_PROVIDER_MAX_ATTEMPTS);
  const retryDelayMs = nonNegativeIntOrDefault(args.retryDelayMs, DEFAULT_PROVIDER_RETRY_DELAY_MS);
  const snapshotPath = await createRunPacketSnapshot(workspace);
  const usageBefore = await captureUsageSnapshot(args, "before");
  const attempts = [];
  const retryDelaysMs = [];
  let finalResult = null;

  try {
    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      const result = await runZcodeCli(cliArgs, {
        cwd: workspace,
        timeoutMs: args.timeoutMs ?? PROMPT_TIMEOUT_MS,
        env: visionRunEnv.env,
      });
      const audit = await auditRunPacketAttempt({
        workspace,
        packetPath,
        snapshotPath,
        validationTimeout: args.validationTimeout,
      });
      const state = classifyProviderRunState({ cliOk: result.cli_ok, provider: result, audit });
      const attemptResult = { ...result, audit, ...state };
      attempts.push(attemptResult);
      const shouldRetry = (
        state.supervisor_state === "retryable_provider_error" &&
        attempt < maxAttempts
      );
      if (shouldRetry) {
        retryDelaysMs.push(retryDelayMs);
        if (retryDelayMs > 0) await sleep(retryDelayMs);
        continue;
      }
      finalResult = attemptResult;
      break;
    }

    const usageAfter = await captureUsageSnapshot(args, "after");
    const runUsage = normalizedZcodeUsageFromStdout(finalResult.stdout ?? "");
    const usageAccounting = buildUsageAccounting(finalResult, usageBefore, usageAfter);
    const finalOk = ["success", "partial_success"].includes(finalResult.supervisor_state);
    await printCliResult(
      {
        ...finalResult,
        ok: finalOk,
        packet: packetPath,
        workspace,
        mode: mapMode(args.mode ?? packet.mode),
        prompt_chars: packet.prompt.length,
        vision,
        vision_preflight: visionPreflight,
        vision_service_credential_source: visionRunEnv.credential_source,
        status: finalResult.supervisor_state,
        attempts: attempts.length,
        attempt_count: attempts.length,
        retry_count: Math.max(0, attempts.length - 1),
        retry_delays_ms: retryDelaysMs,
        max_attempts: maxAttempts,
        safe_to_retry_later: finalResult.safe_to_retry_later && attempts.length >= maxAttempts,
        attempt_results: attempts.map(compactAttemptRecord),
        usage_available: usageAccounting.usage_available,
        no_usage_reason: usageAccounting.no_usage_reason,
        response: runUsage.response,
        audit: finalResult.audit,
        validation: finalResult.audit?.validation ?? null,
        validation_ok: finalResult.audit?.validation?.ok ?? null,
        usage: runUsage.usage,
        usage_normalized: runUsage.normalized,
        projection: runUsage.projection,
        usage_snapshots: {
          before: usageBefore,
          after: usageAfter,
        },
        usage_accounting: usageAccounting,
        quota_percent_status: usageAccounting.quota_percent_status,
        quota_percent_unavailable_reason: usageAccounting.quota_percent_unavailable_reason,
      },
      args.out,
    );
  } finally {
    await unlink(snapshotPath).catch(() => {});
  }
}

async function doctor() {
  const payload = await runJson("python3", [
    "tools/zcode_eval/zcode_eval.py",
    "doctor",
    "--json",
  ]);
  console.log(JSON.stringify(payload, null, 2));
}

async function launch(port, options = {}) {
  const payload = await runJson("cua-driver", [
    "call",
    "launch_app",
    JSON.stringify({
      bundle_id: DEFAULT_BUNDLE_ID,
      electron_debugging_port: port,
      creates_new_application_instance: Boolean(options.newInstance),
    }),
  ]);
  payload.cdp = await probeCdp(port);
  console.log(JSON.stringify(payload, null, 2));
}

async function fetchTargets(port) {
  return getJson(port, "/json/list");
}

async function probeCdp(port) {
  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const version = await getJson(port, "/json/version");
      return { ok: true, browser: version.Browser ?? null };
    } catch (error) {
      lastError = error;
      await new Promise((resolveWait) => setTimeout(resolveWait, 500));
    }
  }
  return { ok: false, error: lastError?.message ?? "unknown CDP error" };
}

function getJson(port, path) {
  return new Promise((resolveJson, rejectJson) => {
    const request = http.get(
      {
        host: "127.0.0.1",
        port,
        path,
        timeout: 5000,
      },
      (response) => {
        let body = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          body += chunk;
        });
        response.on("end", () => {
          if ((response.statusCode ?? 500) >= 400) {
            rejectJson(new Error(`CDP HTTP ${response.statusCode}: ${body.slice(0, 500)}`));
            return;
          }
          try {
            resolveJson(JSON.parse(body));
          } catch (error) {
            rejectJson(error);
          }
        });
      },
    );
    request.on("timeout", () => {
      request.destroy(new Error(`CDP HTTP timeout on port ${port}`));
    });
    request.on("error", rejectJson);
  });
}

function pickMainPage(targets) {
  const page = targets.find(
    (target) =>
      target.type === "page" &&
      target.title === "ZCode" &&
      target.webSocketDebuggerUrl,
  );
  if (!page) {
    throw new Error("No ZCode page target found. Run launch first.");
  }
  return page;
}

async function printTargets(port) {
  const targets = await fetchTargets(port);
  const slim = targets.map((target) => ({
    id: target.id,
    type: target.type,
    title: target.title,
    url: target.url,
    has_websocket: Boolean(target.webSocketDebuggerUrl),
  }));
  console.log(JSON.stringify(slim, null, 2));
}

async function cdpCommand(wsUrl, method, params = {}) {
  const socket = new WebSocket(wsUrl);
  const id = Math.floor(Math.random() * 1_000_000);
  await new Promise((resolveOpen, rejectOpen) => {
    socket.addEventListener("open", resolveOpen, { once: true });
    socket.addEventListener("error", rejectOpen, { once: true });
  });

  const result = await new Promise((resolveMessage, rejectMessage) => {
    const timeout = setTimeout(() => rejectMessage(new Error(`CDP timeout: ${method}`)), 15000);
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id !== id) return;
      clearTimeout(timeout);
      if (message.error) rejectMessage(new Error(JSON.stringify(message.error)));
      else resolveMessage(message.result);
    });
    socket.send(JSON.stringify({ id, method, params }));
  });
  socket.close();
  return result;
}

async function evaluate(port, expression) {
  const result = await runtimeEvaluate(port, expression);
  console.log(JSON.stringify(result, null, 2));
}

async function runtimeEvaluate(port, expression) {
  const target = pickMainPage(await fetchTargets(port));
  const result = await cdpCommand(target.webSocketDebuggerUrl, "Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result.result;
}

async function text(port, max = 4000) {
  const expression = `(() => {
    const text = document.body ? document.body.innerText : "";
    return text.slice(0, ${JSON.stringify(max)});
  })()`;
  await evaluate(port, expression);
}

async function textboxes(port) {
  const expression = `(() => Array.from(document.querySelectorAll('textarea,input,[contenteditable=true],[role=textbox]')).map((el, i) => ({
    i,
    tag: el.tagName,
    role: el.getAttribute('role'),
    contenteditable: el.getAttribute('contenteditable'),
    placeholder: el.getAttribute('placeholder'),
    aria: el.getAttribute('aria-label'),
    text: (el.innerText || el.value || el.textContent || '').slice(0, 160),
    rect: (() => {
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    })(),
  })))()`;
  await evaluate(port, expression);
}

async function buttons(port) {
  const expression = `(() => Array.from(document.querySelectorAll('button,[role=button]')).map((el, i) => ({
    i,
    text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 120),
    aria: el.getAttribute('aria-label'),
    disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
    rect: (() => {
      const r = el.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    })(),
  })))()`;
  await evaluate(port, expression);
}

async function summary(port) {
  await evaluate(port, summaryExpression());
}

async function openUsage(port) {
  await evaluate(port, openUsageExpression());
}

async function usageSnapshot(port, out) {
  const result = await runtimeEvaluate(port, usageSnapshotExpression());
  const payload = result.value ?? {};
  const textPayload = JSON.stringify(payload, null, 2);
  if (out) {
    const outputPath = resolve(out);
    await mkdir(dirname(outputPath), { recursive: true });
    await writeFile(outputPath, `${textPayload}\n`);
  }
  console.log(textPayload);
}

async function newTask(port, workspace) {
  if (!workspace) throw new Error("--workspace is required");
  const expression = `(() => {
    const workspace = ${JSON.stringify(workspace)};
    const buttons = Array.from(document.querySelectorAll('button,[role=button]'));
    const workspaceRows = buttons
      .filter((node) => (node.innerText || node.textContent || '').trim() === workspace)
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 0 && rect.height > 0)
      .sort((a, b) => a.y - b.y);
    if (!workspaceRows.length) return { ok: false, reason: 'workspace not found', workspace };
    const row = workspaceRows[workspaceRows.length - 1];
    const newTaskButton = buttons.find((node) => {
      const r = node.getBoundingClientRect();
      const text = (node.innerText || node.textContent || node.getAttribute('aria-label') || '').trim();
      return text === 'New task' && Math.abs((r.y + r.height / 2) - (row.y + row.height / 2)) < 6;
    });
    if (!newTaskButton) return { ok: false, reason: 'workspace new task button not found', workspace };
    const r = newTaskButton.getBoundingClientRect();
    const x = Math.round(r.x + r.width / 2);
    const y = Math.round(r.y + r.height / 2);
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      newTaskButton.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
    }
    return { ok: true, workspace, x, y };
  })()`;
  await evaluate(port, expression);
}

async function setMode(port, mode) {
  if (!mode) throw new Error("--mode is required");
  const opened = await runtimeEvaluate(port, `(() => {
    const el = Array.from(document.querySelectorAll('button,[role=button]')).find((node) => node.getAttribute('aria-label') === 'Switch mode');
    if (!el) return { ok: false, reason: 'mode switch not found' };
    const r = el.getBoundingClientRect();
    const x = Math.round(r.x + r.width / 2);
    const y = Math.round(r.y + r.height / 2);
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
    }
    return { ok: true, current: (el.innerText || el.textContent || '').trim(), x, y };
  })()`);
  if (!opened.value?.ok) {
    console.log(JSON.stringify(opened, null, 2));
    return;
  }
  await new Promise((resolveWait) => setTimeout(resolveWait, 300));
  const expression = `(() => {
    const mode = ${JSON.stringify(mode)};
    const el = Array.from(document.querySelectorAll('[role=option],button,[role=button]'))
      .find((node) => (node.innerText || node.textContent || '').trim().includes(mode));
    if (!el) return { ok: false, reason: 'mode option not found', mode };
    const r = el.getBoundingClientRect();
    const x = Math.round(r.x + r.width / 2);
    const y = Math.round(r.y + r.height / 2);
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
    }
    return { ok: true, mode, x, y, text: (el.innerText || el.textContent || '').trim() };
  })()`;
  await evaluate(port, expression);
}

async function setComposer(port, promptText) {
  if (!promptText) throw new Error("--text is required");
  const expression = `(() => {
    const text = ${JSON.stringify(promptText)};
    const el = Array.from(document.querySelectorAll('[contenteditable=true],[role=textbox],textarea,input'))
      .find((node) => node.getBoundingClientRect().width > 100 && node.getBoundingClientRect().height > 10);
    if (!el) return { ok: false, reason: 'composer not found' };
    el.focus();
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      el.value = text;
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    } else {
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, text);
      el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    }
    return {
      ok: true,
      text: (el.innerText || el.value || el.textContent || '').slice(0, 500),
    };
  })()`;
  await evaluate(port, expression);
}

async function submitTask(port, promptText) {
  if (!promptText) throw new Error("--text is required");
  await setComposer(port, promptText);
  await clickByText(port, "Send");
}

async function submitGoal(port, promptText) {
  const text = promptText.trimStart().startsWith("/goal")
    ? promptText
    : `/goal ${promptText}`;
  await submitTask(port, text);
}

async function waitIdle(port, timeoutMs = 300_000, intervalMs = 2_000) {
  const deadline = Date.now() + timeoutMs;
  let lastSummary = null;
  while (Date.now() <= deadline) {
    const result = await runtimeEvaluate(port, `(() => {
      const bodyText = document.body?.innerText || "";
      const buttons = Array.from(document.querySelectorAll('button,[role=button]')).map((el) => ({
        text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim(),
        aria: el.getAttribute('aria-label'),
        rect: (() => { const r = el.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height) }; })(),
      })).filter((button) => button.rect.w > 0 && button.rect.h > 0);
      return {
        running: /\\bWorking for\\b/.test(bodyText) || buttons.some((button) => button.text === 'Stop' || button.aria === 'Stop'),
        awaitingApproval: /Awaiting approval|Permission required/.test(bodyText),
        workedFor: (bodyText.match(/Worked for\\s+([^\\n]+)/) || [])[1] || null,
        lastText: bodyText.slice(-3000),
      };
    })()`);
    lastSummary = result.value;
    if (lastSummary?.awaitingApproval) {
      console.log(JSON.stringify({ ok: false, reason: "awaiting_approval", summary: lastSummary }, null, 2));
      return;
    }
    if (lastSummary && !lastSummary.running && lastSummary.workedFor) {
      console.log(JSON.stringify({ ok: true, summary: lastSummary }, null, 2));
      return;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, intervalMs));
  }
  console.log(JSON.stringify({ ok: false, reason: "timeout", summary: lastSummary }, null, 2));
}

async function clickByText(port, label) {
  if (!label) throw new Error("--text is required");
  await clickMatchingText(port, label, false);
}

async function clickByContainedText(port, needle) {
  if (!needle) throw new Error("--text is required");
  await clickMatchingText(port, needle, true);
}

async function clickMatchingText(port, label, contains) {
  const expression = `(() => {
    const label = ${JSON.stringify(label)};
    const contains = ${JSON.stringify(contains)};
    const candidates = Array.from(document.querySelectorAll('button,[role=button]'));
    const el = candidates.find((node) => {
      const text = (node.innerText || node.textContent || node.getAttribute('aria-label') || '').trim();
      const aria = node.getAttribute('aria-label') || '';
      return contains ? text.includes(label) || aria.includes(label) : text === label || aria === label;
    });
    if (!el) return { ok: false, reason: 'button not found', label };
    const disabled = Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true';
    if (disabled) return { ok: false, reason: 'button disabled', label };
    const r = el.getBoundingClientRect();
    const x = Math.round(r.x + r.width / 2);
    const y = Math.round(r.y + r.height / 2);
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
    }
    return { ok: true, label, contains, x, y };
  })()`;
  await evaluate(port, expression);
}

async function screenshot(port, out) {
  if (!out) throw new Error("--out is required");
  const target = pickMainPage(await fetchTargets(port));
  await cdpCommand(target.webSocketDebuggerUrl, "Page.enable");
  const result = await cdpCommand(target.webSocketDebuggerUrl, "Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
  });
  const outputPath = resolve(out);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, Buffer.from(result.data, "base64"));
  console.log(outputPath);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.command || args.command === "help" || args.command === "--help") {
    usage();
    return;
  }
  if (args.command === "doctor") await doctor();
  else if (args.command === "cli-path") await cliPath();
  else if (args.command === "cli-doctor") await cliDoctor(args.out);
  else if (args.command === "cli-preflight") await cliPreflight(args);
  else if (args.command === "cli-version") await cliVersion(args.out);
  else if (args.command === "bootstrap-cli-config") await bootstrapCliConfig(args);
  else if (args.command === "vision-preflight") await visionPreflightCommand(args);
  else if (args.command === "cli-prompt") await cliPrompt(args);
  else if (args.command === "run-packet") await runPacket(args);
  else if (args.command === "launch") await launch(args.port, { newInstance: args.newInstance });
  else if (args.command === "targets") await printTargets(args.port);
  else if (args.command === "text") await text(args.port, args.max ?? 4000);
  else if (args.command === "eval") {
    if (!args.expr) throw new Error("--expr is required");
    await evaluate(args.port, args.expr);
  } else if (args.command === "textboxes") await textboxes(args.port);
  else if (args.command === "buttons") await buttons(args.port);
  else if (args.command === "summary") await summary(args.port);
  else if (args.command === "open-usage") await openUsage(args.port);
  else if (args.command === "usage") await usageSnapshot(args.port, args.out);
  else if (args.command === "new-task") await newTask(args.port, args.workspace);
  else if (args.command === "set-mode") await setMode(args.port, args.mode);
  else if (args.command === "set-composer") await setComposer(args.port, await readPrompt(args));
  else if (args.command === "submit-task") await submitTask(args.port, await readPrompt(args));
  else if (args.command === "goal") await submitGoal(args.port, await readPrompt(args));
  else if (args.command === "wait-idle") await waitIdle(args.port, args.timeoutMs ?? 300_000, args.intervalMs ?? 2_000);
  else if (args.command === "click") await clickByText(args.port, args.text);
  else if (args.command === "click-contains") await clickByContainedText(args.port, args.text);
  else if (args.command === "screenshot") await screenshot(args.port, args.out);
  else throw new Error(`Unknown command: ${args.command}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
