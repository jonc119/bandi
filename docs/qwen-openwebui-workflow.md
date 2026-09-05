# Qwen Coding Workflow

## Purpose

Use Qwen through Open WebUI while away from the AI rig, without giving it access to the live Delivery
QC workspace, local credentials, or the protected `main` branch.

## Workspace and Git

- Host workspace: `C:\Users\jonc1\AI\bandi-qwen`
- Branch: `qwen/agent`
- Remote: `https://github.com/jonc119/bandi.git`
- Qwen can commit only after tests pass. The host sync task pushes committed work to `qwen/agent`
  every five minutes. It never merges into `main`.

## Open WebUI Use

1. Connect to Open WebUI through Tailscale.
2. Select `qwen3.8:latest` and the `Bandi Qwen Terminal` connection.
3. Start with: `Read AGENTS.md and HANDOFF.md. Inspect Git status and the last commits. Explain the
   current state before editing. Work only on qwen/agent. Run tests, commit, and update HANDOFF.md.`
4. Use GitHub to review the `qwen/agent` branch. Astra or a human reviews and merges it into `main`.

## Boundaries

- The terminal mount contains only the dedicated Git clone. It does not mount the live QC project,
  Docker socket, user profile, browser data, Stratus credentials, or report data.
- The terminal has no host port and no internet route. It can communicate only with the existing
  Open WebUI container over a private Docker network.
- The terminal may not merge, force-push, or modify `main`.
- The host sync task refuses an unexpected branch, unexpected remote, or uncommitted work.
- Open WebUI must use an admin terminal connection so the terminal API key stays server-side.
