# idotadsb

Personal **ADS-B** feeder → **iDotMatrix** LED panel: poll `aircraft.json`, render a small flight UI, optionally upload over Bluetooth. See **[docs/PRODUCTION.md](docs/PRODUCTION.md)** for architecture, configuration, and how to run it.

## Why this exists (and how to read it)

This is a **hobby project** to get more **hands-on** with the software development lifecycle from a **product** perspective—not a polished product or a library you should depend on.

Everything here should be treated as **experimental at best**. The approach was intentional “vibe code”: a written spec, fast iteration, and enough automated tests to exercise the workflows I cared about. For that goal, it worked.

I’m sharing it **transparently** as-is. If you want to change or build on it, **fork the repo** and work from your fork. I’m **not expecting to maintain** this project or review pull requests; opening issues here is unlikely to be useful compared to carrying changes in your own fork.

## License

**GNU General Public License v3.0** — see [LICENSE](LICENSE).

Display output uses [markusressel/idotmatrix-api-client](https://github.com/markusressel/idotmatrix-api-client) (GPL-3); see [docs/PRODUCTION.md](docs/PRODUCTION.md#acknowledgments) for a short acknowledgment.
