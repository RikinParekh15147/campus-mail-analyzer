from dataclasses import dataclass
from datetime import datetime

CATEGORIES = (
    "examinations",
    "assignments",
    "workshops_events",
    "placements",
    "scholarships",
    "administration",
    "course_materials",
    "nonacademic_other",
)


@dataclass
class Notice:
    text: str
    subject: str = ""
    reference_date: datetime | None = None
    owner_id: str | None = None
    source_key: str | None = None

    def __post_init__(self):
        if not self.text.strip():
            raise ValueError("Notice text is empty")
        if len(self.text) > 2_000_000:
            raise ValueError("Notice exceeds the text limit")
