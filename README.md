# idotadsb

Personal **ADS-B** feeder → **iDotMatrix** LED panel: poll `aircraft.json` from a raspberry pi, render a small flight UI, upload over Bluetooth to a 64x64 idotmatrix display. See **[docs/PRODUCTION.md](docs/PRODUCTION.md)** for architecture, configuration, and how to run it. Optional refactor ideas (not commitments) are in **[docs/REFACTOR_ROADMAP.md](docs/REFACTOR_ROADMAP.md)**.

## Why this exists (and how to read it)

This is a **hobby project** to get more **hands-on** with the software development lifecycle from a **product** perspective—not a polished product or a library you should depend on.

Everything here should be treated as **experimental at best**. The approach was intentional “vibe code”: a written spec, fast iteration, and enough manual tests to exercise the workflows I cared about. For that goal, it worked - I have a rotating backdrop display of nearby planes! 

I’m sharing it **transparently** as-is. If you want to change or build on it, you should probably **fork the repo** and work from your fork. I’m **not expecting to maintain** this project or review pull requests; opening issues here is unlikely to be useful compared to carrying changes in your own fork.

A few things I would love to potentially add:
- Improve the flight path data, I'm currently fetching results from [adsbdb](https://www.adsbdb.com/) as they have a pretty generous API - **PLEASE DO NOT ABUSE THEIR API by cranking up the polling of them**.
- Support for other enrichment sources. Opensky is interesting, i didnt pursue it.  flightaware is doable, but you'd quickly exhaust included limits for feeders


## License

**GNU General Public License v3.0** — see [LICENSE](LICENSE).

Display output uses [markusressel/idotmatrix-api-client](https://github.com/markusressel/idotmatrix-api-client) (GPL-3); see [docs/PRODUCTION.md](docs/PRODUCTION.md#acknowledgments) for a short acknowledgment.
