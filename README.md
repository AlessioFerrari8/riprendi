# riprendi

**Resume Claude Code sessions automatically when their usage limit resets.**

You leave Claude Code working, it hits the usage limit ("…your session limit resets 11am"),
and the work sits there until you come back and type "continue". `riprendi` (Italian for
"resume") watches the sessions you choose and, a couple of minutes after the limit resets,
picks them up again on its own — then tells you on the desktop.

```
$ cd ~/code/my-app
$ riprendi follow
Following 1c5e183f-d612-441f-931b-704d1f7f2b3f (/home/you/code/my-app)

$ riprendi status
1c5e183f-d612-441f-931b-704d1f7f2b3f  /home/you/code/my-app  blocked until 11:02  attempts: 0
```

It does not get around the limit: it waits for it to reset, exactly like you would.

## Requirements

- Linux with **systemd user services** (the watcher runs as a `systemctl --user` service)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) — the `claude` command on your `PATH`, already logged in
- Python **3.10+** (standard library only, no dependencies)
- Optional: `notify-send` (package `libnotify-bin`) for desktop notifications

## Install

```bash
pipx install git+https://github.com/<you>/riprendi.git
riprendi install        # writes and starts ~/.config/systemd/user/riprendi.service
```

Or from a clone, without installing the package:

```bash
git clone https://github.com/<you>/riprendi.git && cd riprendi
python3 -m riprendi install
```

## Usage

| Command | What it does |
|---|---|
| `riprendi follow [SESSION_ID]` | Follow the most recent session of the current folder (or a specific one) |
| `riprendi unfollow [SESSION_ID]` | Stop following it |
| `riprendi status` | Followed sessions and their state: `active`, `blocked until HH:MM`, `resuming`, `stopped: too many attempts`, `error` |
| `riprendi watch [--once] [--interval N]` | The watcher loop; systemd runs it for you |
| `riprendi install` / `riprendi uninstall` | Start / remove the systemd user service |

Only sessions you `follow` are ever resumed. A good habit: when you hand Claude Code a long
task, run `riprendi follow` in that project folder (or ask Claude to run it for you).

## How it works

1. Every 60 seconds the watcher reads the last event of each followed session in
   `~/.claude/projects/<folder>/<session-id>.jsonl`.
2. A usage limit shows up there as an assistant message with `isApiErrorMessage: true`,
   `error: "rate_limit"` and a text such as *"…your session limit resets 11am (Europe/Rome)"*.
   The reset time is read from that text (`11am`, `3:30pm`, `15:00`, with or without a time zone).
   If it cannot be read, the watcher tries again every 30 minutes.
3. Two minutes after the reset it runs, in the session's own folder:

   ```
   claude --resume <session-id> -p "The usage limit has reset: continue from where you left off. If the work was already finished, say so and stop." --permission-mode auto
   ```

   Output goes to `~/.local/state/riprendi/logs/`, and you get a notification when it starts
   and when it finishes (or gets blocked again).

## Safety

- **`--permission-mode auto`.** Nobody is there to answer permission prompts, so the resumed
  session runs in Claude Code's `auto` mode: it can keep working, while risky actions (pushes,
  deletions, anything outside the project) stay blocked. `bypassPermissions` is never used.
- **It never races you.** If the session moved on after the limit error — you resumed it
  yourself — it does nothing. It never starts two resumes of the same session.
- **It gives up.** After 3 resumes in a row that end on the limit again, it stops and tells
  you. That is what a *monthly* spending limit looks like: it does not reset at a clock time,
  and insisting would only waste attempts. A resume that wrote nothing waits 30 minutes before
  the next try instead of looping.
- **No credentials.** It uses your existing `claude` login and never reads or stores tokens.
  The state file (`~/.local/state/riprendi/state.json`) holds only session ids, paths and times.

## Limitations

- Your computer has to be on: the watcher runs locally.
- It resumes the main session, not its subagents (the resumed session can start them again).
- It relies on the format Claude Code uses for session logs and limit messages today. If a
  future version changes it, `riprendi status` will just keep showing `active`.

## Uninstall

```bash
riprendi uninstall
pipx uninstall riprendi
rm -rf ~/.local/state/riprendi   # state and logs, if you want them gone too
```

## Development

```bash
python3 -m unittest discover -s tests -v
```

Tests use a fake `claude` on `PATH`; they never call the real one. Set `RIPRENDI_HOME` and
`RIPRENDI_PROJECTS` to point the tool at other folders.

## License

[MIT](LICENSE)
