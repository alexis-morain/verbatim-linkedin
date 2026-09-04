"""What the project page says, assembled from the repository README.

`readme = "../README.md"` in the project file does not build. Hatchling
refuses a readme path outside the project directory, which is the one place
`force-include` is allowed to reach: the bundle travels up, the metadata
cannot. So the README arrives here as text rather than as a path, and the
project file names this hook instead of a file it may not name.

Its links are relative because it is read on GitHub, where they resolve
against the repository. PyPI keeps them verbatim and serves the same
markdown from a host with no `docs/` under it, so they are made absolute on
the way through. That is a build step and not an edit: the file in the
repository stays the one somebody reads in a clone.

app/tests/test_packaging.py holds both halves.
"""

import re
from pathlib import Path

try:
    from hatchling.metadata.plugin.interface import MetadataHookInterface
except ModuleNotFoundError:
    # The tests import the rewriting below and run where the build backend
    # is not installed, which is both of the runs check.sh makes: a bare
    # interpreter first, then the project environment, and a build
    # dependency belongs to neither. The hook is dead weight there and the
    # rewriting is the half with a decision in it.
    MetadataHookInterface = object

#: A markdown link or image whose target is a path in this repository. The
#: leading `!` is kept because the two go to different hosts. A scheme, a
#: protocol relative URL and a fragment are all already somewhere.
RELATIVE = re.compile(r"(!?)\[([^\]]*)\]\((?!\w+:|//|#)([^)\s]+)\)")


def absolute_links(markdown: str, repository: str, ref: str = "main") -> str:
    """The same prose, with every relative target pointed at `repository`.

    Three destinations, because GitHub has three. A file is a `blob` and a
    directory is a `tree`, and telling them apart by the trailing slash is
    enough for a README that writes them that way. An image has to reach the
    file itself, on `raw.githubusercontent.com`, since a `blob` URL serves
    the page around the file and an `img` pointed at it renders nothing.

    The ref is a branch rather than the tag being cut, so that the page of a
    published version keeps working when a link moves. A dead link on PyPI
    outlives the release it shipped with.
    """
    repository = repository.rstrip("/")
    host = "https://github.com/"
    if not repository.startswith(host):
        raise ValueError(f"not a GitHub repository, so the raw and tree URLs "
                         f"cannot be derived: {repository}")
    raw = f"https://raw.githubusercontent.com/{repository[len(host):]}/{ref}/"

    def absolute(match: re.Match) -> str:
        image, label, target = match.groups()
        if image:
            return f"![{label}]({raw}{target})"
        kind = "tree" if target.endswith("/") else "blob"
        return f"[{label}]({repository}/{kind}/{ref}/{target})"

    return RELATIVE.sub(absolute, markdown)


class ReadmeFromAbove(MetadataHookInterface):
    """Reads the README that sits one level above this project file."""

    PLUGIN_NAME = "custom"

    def update(self, metadata: dict) -> None:
        readme = Path(self.root).parent / "README.md"
        metadata["readme"] = {
            "content-type": "text/markdown",
            # The repository is read out of the URLs the project already
            # declares. A second copy here is a second thing to move.
            "text": absolute_links(readme.read_text(encoding="utf-8"),
                                   metadata["urls"]["Source"]),
        }
