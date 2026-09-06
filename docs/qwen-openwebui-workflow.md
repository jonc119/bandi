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

The configured coding chat is:
http://100.82.38.123:3000/c/b0f8b209-635a-4d9e-8f0c-1b42eca837f1

Open it while connected to Tailscale and signed into Open WebUI. It has native function calling,
the project terminal, and a coding system prompt. Bookmark this chat on the iPhone. The AI rig,
Docker, Ollama, and Tailscale must stay running. This route uses local Qwen, independently of
hosted OpenAI usage availability.

1. Connect to Open WebUI through Tailscale.
2. Select `qwen3.8:latest`. In the message box, click the cloud-shaped terminal button, then choose
   `Bandi Qwen Terminal` from the **System** list. Do not use the four-diamond **Integrations** menu or
   the Code Interpreter icon; those are separate features.
3. Start with: `Read AGENTS.md and HANDOFF.md. Inspect Git status and the last commits. Explain the
   current state before editing. Work only on qwen/agent. Run tests, commit, and update HANDOFF.md.`
4. Use GitHub to review the `qwen/agent` branch. Astra or a human reviews and merges it into `main`.

For a new chat, explicitly set Controls > Function Calling to Native. The installed version's
Default mode did not reliably execute the requested command. Always require actual tool output.

## Review Before Merge

Qwen leaves commits on `qwen/agent` and updates `HANDOFF.md`. Host sync publishes that branch only;
it does not merge. Astra selects the OpenAI reviewer based on the change: Luna for small documentation,
Terra for ordinary code, and Astra for QC rules or security. Record the reviewed commit SHA, reviewer,
test evidence, and resolution of findings before a merge. Further edits require another review.
If hosted usage is unavailable, Qwen can keep working locally but the merge waits.

This is an operating policy; GitHub branch protection has not been verified by this setup.

For a harmless connection check after choosing `qwen3.8:latest` and the terminal connection, send:

```text
Use the terminal to run: git status --short --branch
Reply with the exact output. Do not edit files or run any other command.
```

The expected branch begins with `## qwen/agent` and has no modified files.

The Open Terminal connection is a server-side **Admin > Integrations > Open Terminal** connection with URL
`http://bandi-qwen-terminal:8000`. Its API key remains in the ignored local secret store and is never
entered into source control. `scripts/replace-open-webui-for-qwen.ps1` preserves the existing Open WebUI
data volume, creates a stable ignored `WEBUI_SECRET_KEY`, and retains the stopped original container for
rollback. It configures the terminal connection server-side, so the terminal API key never reaches the phone
browser.

## Boundaries

- The terminal mount contains only the dedicated Git clone. It does not mount the live QC project,
  Docker socket, user profile, browser data, Stratus credentials, or report data.
- The terminal has no host port and no internet route. It can communicate only with the existing
  Open WebUI container over a private Docker network.
- The Open Terminal image requires its normal Linux capability set to launch its bundled runtime;
  it still runs with `no-new-privileges`, CPU, memory, and process limits.
- The terminal may not merge, force-push, or modify `main`.
- The host sync task refuses an unexpected branch, unexpected remote, or uncommitted work.
- Open WebUI must use an admin terminal connection so the terminal API key stays server-side.
