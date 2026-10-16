# Security Policy

Atoll reads credentials that belong to other tools on your computer:
- the Claude Code OAuth token in `~/.claude/.credentials.json`;
- the OpenRouter API key in `~/.pi/agent/auth.json` or `$OPENROUTER_API_KEY`.

Each one is sent only to its own service (`api.anthropic.com` or `openrouter.ai`), over HTTPS. Atoll never prints, logs or saves them.

## Supported versions

Security fixes go into the latest release only.

## Reporting a vulnerability

**Please don't open a public issue.** Report it privately instead, through GitHub's [private vulnerability reporting](https://github.com/donjordano/atoll/security/advisories/new) (the repository's Security tab → *Report a vulnerability*).

Please include what's affected, how to reproduce it, and what an attacker could do with it. You can expect a reply within a week. Once a fix is released, you'll be credited unless you'd rather not be.

Issues that especially count as security issues:
- a token or key being sent anywhere other than its own service;
- a token or key ending up in a log, file or the screen;
- Atoll running code or commands taken from a session log or alert file.
