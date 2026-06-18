# GLM-5.2 ZCode Operator Guide

<p align="right">
  <a href="./glm-5.2-zcode-operator-guide.md"><kbd>English</kbd></a>
  <a href="./glm-5.2-zcode-operator-guide.ja.md"><kbd>日本語</kbd></a>
</p>

この guide は、公開されている GLM-5.2 の情報を Codex-to-ZCode の実用的な運用手順に落とし込むためのものです。

Sources:

- https://z.ai/blog/glm-5.2
- https://docs.z.ai/guides/llm/glm-5.2
- https://huggingface.co/zai-org/GLM-5.2

## セットアップ手順の次に読む

最初は repo の README から始めてください。この guide は2段階目です。target repo に
ZCode routing hint を入れた後で、「どの task を ZCode に任せるべきか」を決めるために使います。

この guide を使う前に確認すること:

1. ZCode が install 済みで、sign in も済んでいる。
2. target repo で
   `zcode-install-repo /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO` を一度実行済み。
3. `zcode-auto-route --workspace /ABSOLUTE/PATH/TO/YOUR/TARGET_REPO --objective "..."`
   が route decision を返す。
4. Codex が小さな allowed-file set と実際の validation command を選んでいる。

workspace path を絶対パスで渡すなら、command は Terminal のどの folder から実行しても大丈夫です。
例の `/ABSOLUTE/PATH/TO/YOUR/TARGET_REPO` は、target repo の中で `pwd` を実行して出た path に置き換えてください。

## Codex Delegation で大事なこと

GLM-5.2 は、1M context、128K maximum output tokens、thinking modes、tool/function calling、context caching、structured output、MCP support を持つ long-horizon engineering model として位置づけられています。

実務上の要点は「context をたくさん貼る」ことではありません。architecture、standards、過去の判断を安定して保ちながら、長い coding agent trajectory を進めるために使うことです。

ZCode では、長い記憶と multi-step execution が効く task を ZCode に任せ、final acceptance と safety gate は Codex に残します。

GLM-5.2 は ZCode、Claude Code、OpenCode、hosted APIs、open weights から使えると説明されています。これは benchmark の機会です。同じ model を別の agent harness で比べ、model だけで結果が決まると決めつけないようにします。

## Time-Sensitive Plan Notes

Z.AI blog にある Coding Plan quota や ZCode quota promotion は、日付と plan に依存します。benchmark 判断へ hard-code しないでください。quota efficiency が重要な日は、current plan page または app UI を確認し、日付、timezone、visible quota、peak/off-peak window を記録します。

ZCode 3.1.0 は Usage and Quota entry point を追加し、3.1.1 は task startup、model retention、remote workspace behavior、tool environment inheritance を改善しました。3.1.2 は proxy certificate / bypass controls を追加し、resumed-task thinking level と MCP HTTP header handling を修正しました。

supervisor run では、各 task の前後に `zcodectl usage` で Usage Stats を取り、evaluation ledger に `tokens_used` と `quota_percent_used` を記録します。remote workspace や WSL workspace は、local snapshot で変更内容を厳密に証明できるまでは higher-audit surface として扱います。

この環境の installed ZCode 3.1.2 desktop bundle には `/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs` に headless CLI があり、bundled CLI version は `0.14.8` です。Codex orchestration では、可能な限り GUI/CDP より `zcodectl run-packet` を優先します。CLI は `--prompt`、`--cwd`、`--mode`、`--target`、`--resume`、`--json` を受け取れるため、bounded packet の automation surface として扱いやすいです。

現在の ZCode Agent docs では、project instructions は user-level `~/.zcode/AGENTS.md` と current workspace `AGENTS.md` から読まれ、workspace instructions が primary project source です。`CLAUDE.md` は one-time onboarding migration source であり、継続的に読まれる runtime file ではありません。delegation では bounded worker contract を workspace `AGENTS.md` に置きます。

現在の ZCode subagent docs で supported とされているのは built-in read-only Explore subagent だけです。user-defined custom subagent markdown files に runtime behavior を依存させず、reusable workflow は Skills または Commands にします。

## Task Classes

`zcode_supervisor packet --task-class <class>` で、ZCode に GLM-5.2 の使い方を伝えます。

| Task class | 使う場面 | Default effort | Context strategy |
|---|---|---:|---|
| `small-fix` | narrow bug または小さな implementation | `high` or `max` | touched files と tests だけ読む |
| `root-cause` | bug が call chain、config、logs、state にまたがる | `max` | edit 前に related modules をたどる |
| `architecture` | project inventory や refactor plan が必要 | `max` | module boundaries と contracts を守る |
| `production-gate` | standards compliance を厳しく見る | `max` | rules、lint/build/test commands、prohibited ops を含める |
| `mobile-debug` | client/mobile/ADB/logcat/screenshots loop | `max` | reproduction path と runtime evidence を含める |
| `research` | automated research または performance optimization | `max` | source map と verification plan を残す |
| `long-horizon` | multi-step build/test/fix loops | `max` | `/goal` と explicit completion criteria を使う |

## Effort Policy

`max` を使う場面:

- long-horizon implementation
- cross-module debugging
- production-grade standard checks
- architecture mapping
- mobile/client debugging
- several repair iterations が想定される task

`high` を使う場面:

- cheap health checks
- simple read-only review
- tight allowed files の小さな code edit
- latency を重視する benchmark probe

GLM-5.2 release material では、flexible effort は latency/cost と coding capability の tradeoff として説明されています。結果を再利用しない trivial probe に `max` effort を使いすぎないようにします。

## Context Policy

1M context は architectural continuity として扱い、何でも貼るための枠として使いません。

良い context:

- repo standards
- module boundary map
- failing tests
- call chain snippets
- relevant config
- logs and reproduction steps
- accepted constraints and prohibited operations

避ける context:

- one-file fix への raw whole-repo dumps
- duplicate transcripts
- secrets or `.env*`
- build outputs and caches
- reproduction question がない screenshots/logs

## UX-Safe Automation Rules

human review work を増やす ritual ではなく、減らす guardrail を優先します。

- packet が `worktree`、`disposable`、`fixture` と示していない限り `Full Access` を block します。
- narrow task には `--max-changed-files` を設定し、広すぎる edit を audit で自動失敗させます。
- default は `--risk-budget low` です。Codex が広い scope を選んだ時だけ上げます。
- destructive validation command は packet creation 時点で reject します。validation は安全性を証明するもので、破壊的に state を変えるものではありません。

## ZCode Prompt Pattern

```text
/goal You are a ZCode worker under Codex audit.
Workspace: <workspace>
Workspace kind: <regular|worktree|disposable|fixture>
Objective: <specific outcome>
GLM-5.2 task class: <task-class>
GLM-5.2 effort: max
Risk budget: low
Max changed files: <limit or not set>
Context policy: <why this context is enough>
Allowed files: <paths>
Forbidden files: <paths>
Validation: <command>

Before editing, map the relevant module boundaries and call chain if the task
class is root-cause, architecture, production-gate, mobile-debug, or
long-horizon. Do not change tests unless they are explicitly allowed. Run
validation and report changed files, result, and residual risk.
```

## ZCode Mode Policy

- `Plan`: requirements が不明、migration、data loss risk、security work。
- `Auto Edit`: normal implementation。command execution には review が必要。
- `Full access`: disposable fixture または isolated worktree のみ。snapshot/audit 必須。
- `/goal`: exact validation と clear stop condition がある objective task。

## Best ZCode-GLM-5.2 Jobs

1. refactor 前の project inventory。
2. cross-module root cause analysis。
3. repeated test/fix loops を含む long-running implementation。
4. production standards stress test。
5. logs、screenshots、runtime feedback を使う client/mobile debugging。
6. benchmark evidence 付き performance optimization。

## Anti-Patterns

- planning、implementation、final acceptance を全部 ZCode に持たせる。
- shared production workspace で Full Access を走らせる。
- `allowed_files` 外の変更を許す。
- targeted packet で済むのに whole repository を渡す。
- Codex が validation を再実行しないまま pass を受け入れる。
- approvals、time、file churn、tests、visible token/quota data を測らずに ZCode と他 worker を比較する。

## Local/Open-Weight Note

Hugging Face model card は GLM-5.2 を MIT license とし、SGLang、vLLM、xLLM、Transformers、KTransformers deployment paths を説明しています。model card には非常に大きな parameter count と BF16/F32 tensor types も記載されています。

この project では local serving は research path であり、default Codex worker route ではありません。default route は ZCode または hosted API access と Codex-side supervision です。
