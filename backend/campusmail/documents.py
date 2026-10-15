from io import BytesIO
from pathlib import Path
from html.parser import HTMLParser
import csv
import hashlib


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("br", "p", "div", "li"):
            self.parts.append("\n")
        if tag == "a":
            url = dict(attrs).get("href", "")
            if url.startswith(("https://", "http://")):
                self.parts.append(" " + url + " ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def read_document(data, filename):
    if len(data) > 20 * 1024 * 1024:
        raise ValueError("Attachment exceeds 20 MB limit")
    result = {
        "filename": Path(filename).name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "text": "",
        "status": "unsupported",
        "locators": [],
    }
    ext = Path(filename).suffix.lower()
    try:
        if ext in (".txt", ".csv"):
            result["text"] = data.decode("utf-8-sig", errors="replace")
        elif ext in (".html", ".htm"):
            parser = VisibleText()
            parser.feed(data.decode("utf-8", errors="replace"))
            result["text"] = "".join(parser.parts)
        elif ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise ValueError("Password protected")
            if len(reader.pages) > 100:
                raise ValueError("PDF exceeds 100-page processing limit")
            texts = [page.extract_text() or "" for page in reader.pages]
            result["text"] = "\n".join(texts)
            result["locators"] = [
                {"page": i + 1, "text": t} for i, t in enumerate(texts)
            ]
        elif ext == ".docx":
            from docx import Document

            document = Document(BytesIO(data))
            result["text"] = (
                "\n".join(p.text for p in document.paragraphs)
                + "\n"
                + "\n".join(
                    "\t".join(c.text for c in row.cells)
                    for t in document.tables
                    for row in t.rows
                )
            )
        elif ext == ".xlsx":
            from openpyxl import load_workbook

            book = load_workbook(BytesIO(data), read_only=True, data_only=True)
            chunks = []
            for sheet in book:
                if sheet.max_row > 10000:
                    raise ValueError("Spreadsheet exceeds 10,000 rows")
                chunks.append(
                    "[SHEET: "
                    + sheet.title
                    + "]\n"
                    + "\n".join(
                        "\t".join("" if c is None else str(c) for c in row)
                        for row in sheet.values
                    )
                )
            result["text"] = "\n".join(chunks)
            book.close()
        else:
            return result
        result["status"] = (
            "readable" if result["text"].strip() else "needs_ocr_or_review"
        )
    except Exception as error:
        result.update(status="unreadable", error=str(error)[:300])
    return result
