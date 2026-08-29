"""The one place this app turns markdown into anything else.

Every document an instance holds is markdown: `profile.md`, `voice.md`,
`pillars.md`, `linkedin-page.md`, the files in `corpus/`, and the session
notes under a post. This module renders them, and nothing else in `app/` is
allowed to import the parser. `check.sh` holds that rule, the same way it
holds the one about model instructions: a second renderer is a second reading
of the same file, and the one nobody looks at is the one that would be wrong.

**The body of a post is not a document and is never rendered here.** LinkedIn
has no markdown. The one piece that crosses, `**bold**`, crosses inside
`publish.to_scheduler_html` and therefore only on a tier that builds HTML: on
the `copy` tier, which is the default and the one the copy button serves, the
text is pasted as it stands and the feed shows the asterisks. A rendered
draft would show a heading where the feed shows `## Heading`, at the moment
somebody decides to publish.

Four rules, none of them a preference:

**`html=False`.** Raw HTML in a file is escaped, never passed through.
`corpus/` receives exports from other tools and `profile.md` receives whatever
somebody pasted into it; this is the injection boundary. It being on loopback
does not make somebody's browser a place to run what an export contains.

**Images render as a link to their source.** `html=False` says nothing about
this one: a markdown image is an outbound request the moment the page paints,
made from a screen whose own rail says nothing leaves this machine, and the
file carrying it came from somewhere else. A one pixel GIF in a corpus export
would report every time its file is opened. As a link nothing is fetched and
the address is still there to click.

**Every link carries `rel="noreferrer noopener"`.** Same reason one step
later: without it, clicking a link in somebody's corpus file hands the third
party the address of the page it was clicked from.

**Nothing ever emits an anchor inside an anchor**, and there are two ways to
write one: an image inside a link, and a bare URL inside link text, which the
parser refuses for `[a](b)` and allows for an autolink. HTML has no such
element, so a parser splits the pair into siblings: the outer link comes out
empty, the words after the inner one fall out of both, and the address a
reader lands on is the third party one from inside the document. Both cases
render their content without an anchor, and the depth is counted in the per
render `env`. This one took two rounds of review, because the first fix
covered the image and not its sibling.

The `default` preset rather than `commonmark`, because `profile.md` has a
table in it and the commonmark preset has no tables.
"""

from __future__ import annotations

import threading

from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markupsafe import Markup

#: Deep enough for prose, shallow enough that a file from somewhere else does
#: not get to try. This is the commonmark preset's own figure; the `default`
#: preset raises it to 100, which is a number for a document nobody wrote.
MAX_NESTING = 20

#: How deep in links the renderer is, kept in the per render `env` rather than
#: anywhere that survives a render.
IN_LINK = "verbatim_in_link"

#: One parser per thread. The app serves synchronous routes from a thread
#: pool, so a module level parser is shared state across concurrent renders;
#: whether this particular parser minds is not a thing worth being nearly
#: sure about, and a local costs one construction per worker.
_local = threading.local()


def _parser() -> MarkdownIt:
    parser = getattr(_local, "md", None)
    if parser is None:
        parser = MarkdownIt("default", {
            "html": False,
            "linkify": False,
            "typographer": False,
            "maxNesting": MAX_NESTING,
        })
        _reroute(parser.renderer)
        _local.md = parser
    return parser


# ------------------------------------------------------------------- renderer

def _reroute(renderer) -> None:
    """Replace two of the renderer's rules.

    Closures rather than functions assigned onto the table: the table holds
    the renderer's own rules as bound methods, so a rule is called with four
    arguments and never sees a `self`. `renderInlineAsText` and `renderToken`
    are on the renderer, so it is captured here instead.
    """

    def image(tokens, idx, options, env) -> str:
        """An image, shown as the address it points at rather than fetched.

        The destination arrives already normalised and already judged: an
        image whose source is `javascript:` or `data:` never reaches this
        rule at all, because the inline rule refuses it and leaves the
        source text alone.

        Inside a link it is not an anchor. `[![alt](picture)](page)` is an
        ordinary way to write a clickable image, and an anchor inside an
        anchor is not something HTML has: a parser splits the pair into
        siblings, and what comes out is an empty unclickable outer link
        beside a link to the picture. So the picture's own address is the one
        that gives way, which is the right one to lose: the document meant
        the reader to arrive at the page. An image with no alt text keeps its
        address as its text, so the case worth seeing, a bare tracking pixel,
        is still readable.
        """
        token = tokens[idx]
        source = token.attrGet("src") or ""
        alt = renderer.renderInlineAsText(token.children, options, env).strip()
        if env.get(IN_LINK):
            return '<span class="image-link">' + escapeHtml(alt or source) \
                + "</span>"
        return ('<a class="image-link" rel="noreferrer noopener" href="'
                + escapeHtml(source) + '">' + escapeHtml(alt or source)
                + "</a>")

    def link_open(tokens, idx, options, env) -> str:
        """A link, unless it is already inside one, in which case its text
        stands on its own.

        `[a](b)` inside link text is refused by the parser, so the only way
        one link lands inside another is an autolink: the autolink rule is
        not excluded from link text. It is not exotic, it is what pasting a
        URL into a sentence that is already a link does. An anchor inside an
        anchor is not something HTML has, and here the split is worse than
        with an image: the words after the inner one fall out of both, and
        the address a reader lands on is the third party one from inside the
        document rather than the one the document pointed at.

        Nothing is lost by dropping the inner anchor, because an autolink's
        text is its address and stays on the page as text.
        """
        # Counted in `env`, which markdown-it makes fresh for every render
        # call and hands to every rule. A counter held in this closure would
        # outlive a render that raised half way and change what the next one
        # produced.
        depth = env.get(IN_LINK, 0)
        env[IN_LINK] = depth + 1
        if depth:
            return ""
        tokens[idx].attrSet("rel", "noreferrer noopener")
        return renderer.renderToken(tokens, idx, options, env)

    def link_close(tokens, idx, options, env) -> str:
        depth = max(0, env.get(IN_LINK, 0) - 1)
        env[IN_LINK] = depth
        # Still inside one, so the link just closed was a nested one and its
        # opening tag was not written either.
        if depth:
            return ""
        return renderer.renderToken(tokens, idx, options, env)

    renderer.rules["image"] = image
    renderer.rules["link_open"] = link_open
    renderer.rules["link_close"] = link_close


def render(text: str) -> Markup:
    """A document, as HTML, ready to place without the `safe` filter.

    Returning `Markup` rather than a string is the point. A template that
    writes `| safe` is a template somebody copies to a place where the value
    is not safe; the guarantee belongs to the function that made it.
    """
    return Markup(_parser().render(text or ""))


# ---------------------------------------------------------------- plain text

#: Two spaces per level of list, which is what a nested list is written with.
INDENT = "  "


def plain(text: str) -> str:
    """A document as text, for a field that has no formatting.

    `linkedin-page.md` is written to be pasted into the About box of a
    profile, which takes no markup at all. The rule is that every word the
    document holds survives and the characters that exist only to tell a
    renderer what to do do not: hashes, asterisks, backticks, angle brackets
    and table rules go, and a list keeps its bullet because the bullet is the
    item boundary and plain text has no other way to draw one.

    Read off the same token stream `render` uses, never off rendered HTML: an
    implementation that stripped tags would hand back a document whose
    ampersands had become entities, and it would be a second reading of the
    file besides.
    """
    blocks: list[str] = []
    lines: list[str] = []
    lists: list = []          # one entry per open list: None, or the next number
    hangs: list[str] = []     # one per open item: what its later lines line up on
    row: list[str] = []       # cells of the table row being built
    marker = None             # the bullet a list item still owes its first line
    in_cell = False

    def flush() -> None:
        if lines:
            blocks.append("\n".join(lines))
            lines.clear()

    def indent() -> str:
        return INDENT * max(0, len(lists) - 1)

    def put(body: str) -> None:
        """One block of text, onto the block being built.

        The first line of a list item takes the bullet; everything after it in
        the same item lines up under the bullet rather than at the margin. An
        item's second paragraph written flush left would read as the next
        item, which is the one thing the bullet is kept for.
        """
        nonlocal marker
        if not body:
            # An empty block, which is what a fence with nothing in it is.
            # Placing it would spend the item's bullet on nothing and leave
            # the line ending in a space; the item still owes its marker, and
            # `list_item_close` writes the bare one if nothing else arrives.
            return
        pieces = body.split("\n")
        if marker is not None:
            head, marker = marker, None
            lines.append(head + pieces[0])
            lines.extend(" " * len(head) + piece for piece in pieces[1:])
        else:
            under = hangs[-1] if hangs else ""
            lines.extend(under + piece for piece in pieces)

    for token in _parser().parse(text or ""):
        kind = token.type

        if kind == "inline":
            if in_cell:
                row.append(_inline(token.children))
            else:
                put(_inline(token.children))

        elif kind in ("bullet_list_open", "ordered_list_open"):
            if not lists:
                flush()
            lists.append(int(token.attrGet("start") or 1)
                         if kind == "ordered_list_open" else None)
        elif kind in ("bullet_list_close", "ordered_list_close"):
            # Guarded like `hangs` below. The parser balances these, so this
            # cannot fire; if it ever did, the cost is a 500 on somebody's
            # profile screen, and every screen in this app renders the
            # conformance report.
            if lists:
                lists.pop()
            if not lists:
                flush()
        elif kind == "list_item_open":
            if lists and lists[-1] is not None:
                marker = f"{indent()}{lists[-1]}. "
                lists[-1] += 1
            else:
                marker = f"{indent()}- "
            hangs.append(" " * len(marker))
        elif kind == "list_item_close":
            if marker is not None:
                lines.append(marker.rstrip())
                marker = None
            if hangs:
                hangs.pop()

        elif kind in ("fence", "code_block"):
            if not lists:
                flush()
            put(token.content.rstrip("\n"))
            if not lists:
                flush()

        elif kind in ("paragraph_close", "heading_close"):
            if not lists:
                flush()

        elif kind in ("table_open", "table_close"):
            # Not inside a list: a table in a list item belongs to the item,
            # and flushing here would hoist it out ahead of the list while
            # leaving the item behind as a bare bullet. This function would
            # then be writing a marker for content no longer under it, which
            # is the opposite of the reason markers are kept at all.
            if not lists:
                flush()
        elif kind == "tr_open":
            row = []
        elif kind == "tr_close":
            if row:
                put(" | ".join(row))
            row = []
        elif kind in ("th_open", "td_open"):
            in_cell = True
        elif kind in ("th_close", "td_close"):
            in_cell = False

        elif kind == "blockquote_close":
            # Same reason as the table above: a quote inside an item is part
            # of the item, and flushing would cut the item in two.
            if not lists:
                flush()

        # hr leaves nothing behind: a thematic break is a drawing.

    flush()
    return "\n\n".join(block for block in blocks if block.strip())


def _inline(children) -> str:
    """One run of inline tokens as text.

    A link keeps its text and, when the address says something the text does
    not, the address after it in brackets. An autolink says both at once and
    is written once.

    The address is the parser's normalised one, so a non ASCII path comes out
    percent encoded: `https://e.example/é` is written `https://e.example/%C3%A9`.
    It resolves to the same page, and decoding it back would corrupt the URLs
    that were percent encoded in the file on purpose. The encoded one is the
    one that is certainly right.
    """
    out: list[str] = []
    opened: list = []
    for token in children or []:
        kind = token.type
        if kind in ("text", "code_inline"):
            out.append(token.content)
        elif kind in ("softbreak", "hardbreak"):
            out.append("\n")
        elif kind == "link_open":
            opened.append((len(out), token.attrGet("href") or ""))
        elif kind == "link_close":
            at, href = opened.pop() if opened else (len(out), "")
            shown = "".join(out[at:])
            if href and href.strip() != shown.strip():
                out.append(f" ({href})")
        elif kind == "image":
            source = token.attrGet("src") or ""
            alt = _inline(token.children).strip()
            out.append(f"{alt} ({source})" if alt else source)
        # em, strong, s and their closes leave nothing: they are drawings.
    return "".join(out)
