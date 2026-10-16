# Car Thing knowledge base

Background reference on the Spotify Car Thing (codename **superbird**):
hardware, burn mode, flashing tools, other custom OS options (DeskThing,
Nocturne, LlizardOS), getting it online, and recovery. For bridgething, which
this repo uses, see [bridgething.com](https://bridgething.com). Compiled from the
community sources credited inside it; verify against
[carthing.wiki](https://carthing.wiki) before anything destructive.

- [carthing-wiki.md](carthing-wiki.md): the readable version
- [carthing-wiki.yaml](carthing-wiki.yaml): the same facts, structured
- [skills/spotify-carthing/](skills/spotify-carthing): an agent skill
  (`SKILL.md` + `REFERENCE.md`) for AI coding assistants that help with Car
  Thing work. Copy the folder into your assistant's skills directory (for
  Claude Code, `~/.claude/skills/`).

The wiki's networking section describes the classic `g_ether` scheme
(`172.16.42.x`). bridgething uses USB NCM on `10.42.1.x` instead; see
[../docs/02-raspberry-pi-gateway.md](../docs/02-raspberry-pi-gateway.md).
