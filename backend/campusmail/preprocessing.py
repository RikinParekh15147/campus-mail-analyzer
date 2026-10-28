"""Versioned, source-aligned preparation shared by research and runtime."""

from dataclasses import dataclass
import re


PREPROCESSING_VERSION = "source-blocks-v1"
_QUOTED_LINE = re.compile(r"(?m)^[ \t]*>[^\n]*")
_REPLY_HEADER = re.compile(
    r"\n(?:On .{5,180}wrote:|[- ]*Original Message|From:)", re.I,
)
_SIGNATURE = re.compile(r"(?m)^--[ \t]*$")


@dataclass(frozen=True)
class Region:
    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class TextBlock:
    field: str
    source_type: str
    original: str
    canonical: str
    regions: tuple[Region, ...]

    def source_span(self, start: int, end: int) -> tuple[str, int, int, str]:
        """Canonical offsets are identity mapped to the original block."""
        if not 0 <= start < end <= len(self.canonical):
            raise ValueError("Invalid canonical span")
        if any(start < region.end and region.start < end for region in self.regions):
            raise ValueError("Canonical span crosses a masked region")
        if not self.canonical[start:end].strip():
            raise ValueError("Masked spans have no source evidence")
        return self.field, start, end, self.original[start:end]


@dataclass(frozen=True)
class PreparedDocument:
    version: str
    subject: TextBlock
    body: TextBlock
    attachments: tuple[TextBlock, ...]

    @property
    def classifier_text(self) -> str:
        return (self.subject.canonical + " " + self.body.canonical).strip()


def _mask(text: str, regions: list[Region]) -> str:
    chars = list(text)
    for region in regions:
        for index in range(region.start, region.end):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def prepare_body(text: str, source_type: str = "body",
                 field: str = "body") -> TextBlock:
    if not isinstance(text, str):
        raise ValueError("Source text must be a string")
    reply = _REPLY_HEADER.search(text)
    signature = _SIGNATURE.search(text)
    boundary = min(
        (match.start() for match in (reply, signature) if match is not None),
        default=len(text),
    )
    regions = [Region("quoted", m.start(), m.end())
               for m in _QUOTED_LINE.finditer(text[:boundary])]
    if boundary < len(text):
        kind = "reply_history" if reply and reply.start() == boundary else "signature"
        regions.append(Region(kind, boundary, len(text)))
    canonical = _mask(text, regions)
    if len(canonical) != len(text):
        raise AssertionError("Preprocessing must preserve source offsets")
    return TextBlock(field, source_type, text, canonical, tuple(regions))


def prepare_document(subject: str, body: str,
                     attachments: tuple[str, ...] = (),
                     source_type: str = "body") -> PreparedDocument:
    if not isinstance(subject, str):
        raise ValueError("Subject must be a string")
    return PreparedDocument(
        PREPROCESSING_VERSION,
        TextBlock("subject", "subject", subject, subject, ()),
        prepare_body(body, source_type),
        tuple(prepare_body(item, "attachment", f"attachment:{index}")
              for index, item in enumerate(attachments)),
    )
