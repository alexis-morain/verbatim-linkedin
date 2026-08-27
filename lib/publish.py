#!/usr/bin/env python3
"""Dispatch a finished post to whichever publishing tier is configured.

Three tiers, and the default one needs no configuration at all:

  copy      print the post, ready to paste. The default.
  postiz    a self hosted Postiz instance. Emits the scheduling payload; the
            network call belongs to the agent, through the Postiz MCP.
  command   your own binary. The post arrives on its stdin.

Set the tier with LINKEDIN_PUBLISH. Anything that leaves this machine needs
--confirm, and without it the script prints what it would do and stops.

    python3 lib/publish.py draft.txt
    python3 lib/publish.py draft.txt --when 2026-09-01T07:30:00 --confirm
"""

from __future__ import annotations

import argparse
import html as html_module
import json
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass

# LinkedIn refuses a post past this length. Mechanical, verifiable in a
# browser in under a minute.
MAX_CHARS = 3000

# Where LinkedIn truncates a feed post. Approximate and device dependent,
# used for a warning, never for a refusal. See references/platform.md.
FOLD_CHARS = 200


class ConfigError(Exception):
    """The publishing tier is not usable as configured."""


class PostError(Exception):
    """The post itself cannot be published."""


class PublishError(Exception):
    """The configured tier was reached and it failed."""


@dataclass
class Tier:
    name: str
    target: str = ""
    label: str = ""
    command: str = ""
    leaves_the_machine: bool = False


@dataclass
class Result:
    sent: bool
    payload: str
    note: str = ""


def resolve(env) -> Tier:
    """Read the tier out of the environment. Never guesses a missing value."""
    name = (env.get("LINKEDIN_PUBLISH") or "copy").strip().lower()

    if name == "copy":
        return Tier("copy")

    if name == "postiz":
        target = (env.get("POSTIZ_INTEGRATION_ID") or "").strip()
        if not target:
            raise ConfigError(
                "LINKEDIN_PUBLISH=postiz needs POSTIZ_INTEGRATION_ID. "
                "List your integrations first and copy the id of the channel "
                "you actually mean: a personal profile and a company page look "
                "alike in a config file and do not look alike in a feed."
            )
        return Tier("postiz", target=target,
                    label=(env.get("POSTIZ_INTEGRATION_NAME") or "").strip(),
                    leaves_the_machine=True)

    if name == "command":
        command = (env.get("LINKEDIN_PUBLISH_CMD") or "").strip()
        if not command:
            raise ConfigError(
                "LINKEDIN_PUBLISH=command needs LINKEDIN_PUBLISH_CMD, the "
                "program to run. The post arrives on its stdin."
            )
        return Tier("command", command=command, label=command,
                    leaves_the_machine=True)

    raise ConfigError(
        f"unknown publishing tier {name!r}. Use copy, postiz, or command."
    )


def check(text: str) -> str:
    """Guard the post itself. Returns the text as it will be published."""
    body = text.strip()
    if not body:
        raise PostError("the post is empty")
    if len(body) > MAX_CHARS:
        raise PostError(
            f"{len(body)} characters, the platform refuses anything over "
            f"{MAX_CHARS}. Cut it before publishing, not after."
        )
    return body



def to_scheduler_html(text: str) -> str:
    """Turn a post into the HTML a scheduling tool expects.

    Three things, and each one was learned from a post that came out wrong:

    **Empty paragraphs between blocks.** A feed renders consecutive <p> with no
    gap, so a post sent without separators arrives as a wall of text. The blank
    line a reader sees is an empty paragraph, not a margin.

    **NFC normalisation.** A decomposed accent, "e" followed by a combining
    acute, survives a database and a JSON payload intact and then shows up in
    the feed as a letter with something floating next to it. This is the
    "accents dropped on publish" failure, and it is fixed here, once.

    **Escaping.** The post is text, not markup. Only ``**bold**`` crosses over,
    because a short heading in the middle of a post reads better in bold and
    that is the one piece of formatting a feed reliably keeps.
    """
    body = check(text)
    body = unicodedata.normalize("NFC", body)

    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]

    out = []
    for block in blocks:
        block = re.sub(r"\s*\n\s*", " ", block)
        block = html_module.escape(block, quote=False)
        block = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", block)
        out.append("<p>" + block + "</p>")
    return "<p></p>".join(out)

def plan(text: str, tier: Tier, when) -> str:
    """What is about to happen, in words, before anything happens."""
    body = check(text)
    first = body.splitlines()[0]
    target = {
        "copy": "nothing. the post is printed here and goes nowhere.",
        "postiz": f"Postiz channel {tier.target}"
        + (f" ({tier.label})" if tier.label else " (no name configured)"),
        "command": f"your command: {tier.command}",
    }[tier.name]

    lines = [
        f"tier      {tier.name}",
        f"target    {target}",
        f"when      {when or 'now'}",
        f"length    {len(body)} characters",
        f"opens on  {first}",
    ]
    if len(first) > FOLD_CHARS:
        lines.append(
            f"warning   the first line is longer than the fold (~{FOLD_CHARS} "
            "characters). Part of it is hidden behind 'see more'."
        )
    if tier.name == "postiz" and not tier.label:
        lines.append(
            "warning   POSTIZ_INTEGRATION_NAME is not set, so this plan cannot "
            "show you which channel that id belongs to. Set it."
        )
    return "\n".join(lines)


def dispatch(text: str, tier: Tier, when, confirmed: bool) -> Result:
    body = check(text)

    if tier.name == "copy":
        return Result(sent=False, payload=body,
                      note="copy this and paste it into the composer.")

    if not confirmed:
        return Result(sent=False, payload=plan(body, tier, when),
                      note="nothing was sent. Re-run with --confirm.")

    if tier.name == "postiz":
        payload = {
            "integrationId": tier.target,
            "content": to_scheduler_html(body),
            "publishDate": when,
        }
        return Result(
            sent=False,
            payload=json.dumps(payload, ensure_ascii=False, indent=2),
            note=("payload ready. The scheduling call itself goes through the "
                  "Postiz MCP, from the agent, so that the channel list can be "
                  "checked against this id first."),
        )

    if tier.name == "command":
        try:
            proc = subprocess.run(
                tier.command, shell=True, input=body, text=True,
                capture_output=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise PublishError(f"{tier.command} did not finish in time") from exc
        if proc.returncode != 0:
            raise PublishError(
                f"{tier.command} exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout).strip()[:400]}"
            )
        return Result(sent=True, payload=proc.stdout or body,
                      note=f"{tier.command} accepted the post.")

    raise ConfigError(f"unknown tier {tier.name!r}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", nargs="?", default="-",
                    help="file holding the post, or - for stdin")
    ap.add_argument("--when", help="ISO 8601 datetime, omit to publish now")
    ap.add_argument("--confirm", action="store_true",
                    help="required for any tier that leaves this machine")
    ap.add_argument("--plan", action="store_true",
                    help="print what would happen and stop")
    args = ap.parse_args(argv)

    try:
        tier = resolve(os.environ)
        text = sys.stdin.read() if args.path == "-" else open(
            args.path, encoding="utf-8").read()
        if args.plan:
            print(plan(text, tier, args.when))
            return 0
        result = dispatch(text, tier, args.when, args.confirm)
    except (ConfigError, PostError, PublishError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(result.payload)
    if result.note:
        print(f"\n{result.note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
