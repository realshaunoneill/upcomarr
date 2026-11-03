# Security

upcomarr exists to show arr data to people who must not get into the arrs, so a leak of
anything beyond what the page is meant to show counts as a security bug. That covers an API
key, a URL or host, a file path, an internal id, or a way to reach an arr through either
container.

Please report one privately through GitHub's **Report a vulnerability** button on this
repository, not in a public issue.

## In scope

- Anything from an arr reaching the published site outside the allowlist in
  `src/upcomarr/model.py` (`Entry`).
- The generator sending an API key anywhere but the configured arr URL.
- The web image serving anything outside the current build and `/_status.json`, or serving it
  without the security headers in `web/headers.conf`.
- Script injection through arr-supplied text.

## Out of scope

- Who can see the page. upcomarr has no logins; that is the job of whatever you put in front
  of it.
- The arrs' own security, including the fact that their API keys are admin keys.
