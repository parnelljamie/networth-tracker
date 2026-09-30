"""PC <-> phone sync (docs/07-mobile.md). The PC is the master copy: the phone records its API
changes in an outbox, the PC replays them through its own API, then the phone takes a fresh copy
of the PC's database."""
