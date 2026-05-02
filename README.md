# A-organizi

## Context

This module uses [A-workspace](https://github.com/Ron-RONZZ-org/A-workspace) as a **git submodule**:


```bash
# Clone with submodules
git clone --recurse-submodules https://github.com/Ron-RONZZ-org/A-organizi.git
# Or if already cloned:
git submodule update --init --recursive
```

**DO NOT edit workspace/ directly** - see [A-workspace](https://github.com/Ron-RONZZ-org/A-workspace) for master context.


A-organizi - calendar, todo, and journal microapp

## Install

```bash
pip install A-organizi
```

Requires **A-core** (automatically installed as dependency).

## Usage

```bash
A organizi kalendaro ls    # List calendars
A organiszi kalendaro nun  # Show upcoming events
A organizi todo ls       # List tasks
A organizi todo aldoni <text>  # Add a task
A organizi taglibro nun  # Show today's journal
A organizi taglibro skribi <text>  # Add journal entry
```

## Commands

A-organizi provides three subcommands:

| Command | Description |
|---------|-------------|
| kalendaro | Calendar/event management with CalDAV sync |
| todo | Task management with labels and priority |
| taglibro | Daily journal |

## About

A-organizi is a plugin for the [A](https://github.com/Ron-RONZZ-org/A-core/) framework.

**A-organizi depends on A-core** for:
- Plugin discovery via entry points
- i18n (tr() for multilingual support)
- SQLite with WAL mode
- Shared utilities (error(), info(), run())

See the [A-core documentation](https://github.com/Ron-RONZZ-org/A-core/) for more on the framework.

## History

A-organizi combines [autish kalendaro](https://github.com/Ron-RONZZ-org/autish/), [autish todo](https://github.com/Ron-RONZZ-org/autish/), and [autish taglibro](https://github.com/Ron-RONZZ-org/autish/) into one plugin.

## License

GPL-3.0-only