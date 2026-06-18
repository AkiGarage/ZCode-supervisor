#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest tests/test_zcode_supervisor.py tests/test_zcode_repo_setup.py tests/test_zcode_eval.py tests/test_zcode_release.py tests/test_homebrew_formula.py tests/test_distribution_packaging.py tests/test_pypi_readiness.py
python3 -m py_compile tools/zcode_supervisor/zcode_supervisor.py tools/zcode_supervisor/repo_setup.py tools/zcode_supervisor/auto_route.py tools/zcode_eval/zcode_eval.py tools/zcode_eval/zcode_release.py tools/zcode_eval/pypi_readiness.py tools/zcode_control/__init__.py scripts/zcode-install-repo scripts/zcode-auto-route scripts/update-homebrew-formula scripts/verify-python-wheel scripts/check-pypi-release-readiness
ruby -c packaging/homebrew/zcode-supervisor.rb >/dev/null
node --check tools/zcode_control/zcodectl.mjs
node --check tools/zcode_control/browser_scripts.mjs
node --test tests/zcode_provider_errors.test.mjs tests/zcode_run_packet_e2e.test.mjs

rm -rf .local/check/wheelhouse
PIP_DISABLE_PIP_VERSION_CHECK=1 python3 -m pip wheel . --no-deps --no-build-isolation -w .local/check/wheelhouse >/dev/null
python3 scripts/verify-python-wheel .local/check/wheelhouse/*.whl >/dev/null

python3 tools/zcode_supervisor/zcode_supervisor.py packet \
  --workspace benchmarks/zcode-goal-mode \
  --objective "Audit the ledger implementation; it must pass npm test." \
  --allowed src/ledger.js \
  --forbidden test/ledger.test.js \
  --validation "npm test" \
  --effort max \
  --task-class production-gate \
  --risk-budget low \
  --max-changed-files 1 \
  --goal \
  --out .local/check/ledger.packet.json \
  --prompt-out .local/check/ledger.prompt.txt >/dev/null

python3 tools/zcode_supervisor/zcode_supervisor.py snapshot \
  --workspace benchmarks/zcode-goal-mode \
  --out .local/check/ledger.before.json >/dev/null

python3 tools/zcode_supervisor/zcode_supervisor.py audit \
  --workspace benchmarks/zcode-goal-mode \
  --snapshot .local/check/ledger.before.json \
  --packet .local/check/ledger.packet.json >/dev/null
