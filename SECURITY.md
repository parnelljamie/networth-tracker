# Security

Waymark holds sensitive information: a household's balances, holdings and history, and optionally
a Trading 212 API key. If you find a way for that to leak or be tampered with, please tell me
privately first.

## Reporting a problem

Use **[Report a vulnerability](https://github.com/parnelljamie/networth-tracker/security/advisories/new)**
(the repository's Security tab → Advisories). Please don't open a public issue.

Helpful things to include: the version (Settings → Updates), the platform, what an attacker would
need (for example, being on the same Wi-Fi as the PC), and steps to reproduce.

I'll acknowledge a report within a week. This is a spare-time project, so fixes take as long as they
take, but security problems go to the front of the queue, and I'll credit you in the release notes
unless you'd rather I didn't.

## Supported versions

Only the latest release gets fixes. Settings → Updates will tell you if you're behind.

## How Waymark is meant to be exposed

- The PC app's server listens on `127.0.0.1` only.
- Phone sync, when you turn it on, listens on your local network. It serves only the sync endpoints
  and needs the token from the pairing QR code.
- Broker API keys live outside the database, in `<data folder>/secrets/`, encrypted with Windows
  DPAPI on Windows. On Linux the key file is readable only by your user account.
- The app makes network calls only to Yahoo Finance (prices), GitHub (update checks) and, if you
  connect it, Trading 212.

Anything that breaks one of those assumptions is worth reporting.
