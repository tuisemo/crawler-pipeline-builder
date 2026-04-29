# Script Sandbox Technical Evaluation

## Product Goal
Generated crawler scripts should be executable on demand from the workbench. Each execution should produce structured logs that help operators and prompt engineers understand whether failures came from prompt drift, Playwright API misuse, selector mismatch, page runtime behavior, or environment limits.

The sandbox is intentionally manual: generation returns the script first, and users choose when to execute the current generated or edited version.

## Options Evaluated
### Docker Container Sandbox
- Fit: Strong default for productized local/server deployments.
- Strengths:
  - Mature ecosystem and operational familiarity.
  - CPU, memory, pids, network, filesystem, and security options are available via `docker run`.
  - Can use a Playwright-ready image such as `mcr.microsoft.com/playwright/python`.
- Risks:
  - Docker availability varies on developer machines.
  - Docker alone is not a perfect untrusted-code boundary.
  - Browser automation may need network access, so network policy should be explicit per workflow.
- Recommendation: Preferred baseline for production-like use.

References:
- Docker resource constraints: https://docs.docker.com/engine/containers/resource_constraints/
- Docker seccomp profiles: https://docs.docker.com/engine/security/seccomp/
- Docker security overview: https://docs.docker.com/engine/security/

### gVisor / runsc
- Fit: Stronger isolation for untrusted workloads when Linux container runtime control is available.
- Strengths:
  - OCI-compatible runtime.
  - Adds a userspace kernel boundary between the containerized process and host kernel.
- Risks:
  - More deployment complexity, especially on Windows developer machines.
  - Playwright/browser compatibility needs validation in the target environment.
- Recommendation: Best next step for hardened server deployments after Docker baseline.

References:
- gVisor overview: https://gvisor.dev/docs
- gVisor architecture/security intro: https://gvisor.dev/docs/architecture_guide/intro/
- gVisor filesystem model: https://gvisor.dev/docs/user_guide/filesystem/

### Local Subprocess Sandbox
- Fit: Developer fallback and CI-friendly baseline.
- Strengths:
  - No third-party runtime required.
  - Easy to capture stdout/stderr, timeout, exit code, and logs.
- Risks:
  - Not a security boundary for untrusted code.
  - Shares host Python environment and OS permissions.
- Recommendation: Keep as fallback only, clearly labeled as `subprocess`.

Reference:
- Python subprocess timeout/capture APIs: https://docs.python.org/3/library/subprocess.html

### RestrictedPython
- Fit: Policy-limited Python subsets, not browser crawler execution.
- Strengths:
  - Useful for restricted expression-like Python execution.
- Risks:
  - Does not provide the OS/process/browser isolation needed for generated Playwright crawlers.
- Recommendation: Do not use for this feature.

Reference:
- RestrictedPython documentation: https://restrictedpython.readthedocs.io/

## Current Implementation
- Manual endpoint: `POST /api/workflows/run-script-sandbox`
- Frontend action: script workspace `运行沙箱`
- Runtime backend: built-in Python subprocess sandbox (`subprocess.run([sys.executable, ...])`)
- Logs: `logs/script-sandbox/runs/<run_id>/execution.jsonl`

## Recommended Roadmap
1. Keep manual execution in the workbench so users control cost, network effects, and runtime side effects.
2. If stronger isolation is required, add a third-party sandbox runtime as an optional execution backend.
3. Add per-workflow network policy: `none`, `target-only`, or `open`.
4. Add server deployment option for gVisor/runsc once Playwright compatibility is validated.
5. Aggregate `script_sandbox_completed` logs into prompt quality reports.
