# Running client commands from an agent

Use the host agent's command timeout and long-running process facilities where available.
GNU `timeout` is an optional fallback, not a portable prerequisite. Check for it before using
it; macOS and Windows don't supply it by default. A timed-out wait can leave a process running:
retain its session handle or PID, inspect its state and stop that process when needed.

For a foreground tunnel, keep its process handle/PID and a private log path. Verify startup and
make the Service request while the tunnel runs. Stop a temporary test through that handle with
a graceful interrupt. For a connection the user wants to keep, report its handle and stop
procedure. Detached mode has platform-specific privilege prompts (see [connecting.md](connecting.md)).
Don't use a broad process kill or disconnect another existing connection as cleanup.

Browser login needs a human on the machine running the CLI. Reuse an existing valid Session,
direct access token or authenticated proxy when available; don't inspect token contents to
diagnose connectivity. If login is needed, hand it to the user, or execute a bounded login
when the user has authorized that method and can approve the browser request.

## Claude Code adapter

In Claude Code, the human can run `! octelium login --domain <DOMAIN>` in the interactive
terminal. This is Claude Code's Bash-mode syntax, not an Octelium flag or a portable agent
command. Other agents should use their own terminal facility.

Reference: [Claude Code interactive mode](https://code.claude.com/docs/en/interactive-mode).
