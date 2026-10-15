"""Inventory the archive and extract a bounded PDF sample without extractall.

Run with a Python interpreter containing pypdf. No source category is guessed.
"""
from pathlib import Path
from io import BytesIO
import hashlib
import json
import logging
import tarfile
import time
from collections import Counter
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1] / "public" / "quarantine" / "durg_university"
SAMPLE_LIMIT = 120
FILE_LIMIT = 20 * 1024 * 1024
PAGE_LIMIT = 20
logging.getLogger("pypdf").setLevel(logging.ERROR)


def main():
    archive = ROOT / "archive" / "notices_dataset.tar.gz"
    sample = ROOT / "sample_pdfs"
    sample.mkdir(parents=True, exist_ok=True)
    documents, statuses = [], Counter()
    sampled = 0
    last = time.monotonic()
    inventory_path = ROOT / "archive_inventory.jsonl"
    with inventory_path.open("w", encoding="utf-8") as inventory:
        with tarfile.open(archive, "r|gz") as source:
            for member in source:
                if not member.isfile():
                    continue
                row = {"archive_member": member.name, "bytes": member.size, "sampled": False}
                if member.name.lower().endswith(".pdf") and sampled < SAMPLE_LIMIT and 0 < member.size <= FILE_LIMIT:
                    file = source.extractfile(member)
                    if file is None:
                        row["status"] = "member_unreadable"
                    else:
                        with file:
                            data = file.read(FILE_LIMIT + 1)
                        digest = hashlib.sha256(data).hexdigest()
                        document_id = "durg_" + hashlib.sha256(member.name.encode()).hexdigest()[:16]
                        path = sample / (document_id + ".pdf")
                        path.write_bytes(data)
                        sampled += 1
                        row.update(sampled=True, sha256=digest, relative_path=path.relative_to(ROOT).as_posix())
                        doc = {
                            "schema_version": "1.0",
                            "document_id": document_id,
                            "source_type": "public_notice_pdf",
                            "source_dataset": "sameerbanchhor/durg-university-notices",
                            "source_url": "https://huggingface.co/datasets/sameerbanchhor/durg-university-notices",
                            "archive_member": member.name,
                            "resource_path": row["relative_path"],
                            "sha256": digest,
                            "primary_category": None,
                            "label_provenance": "unlabeled",
                            "human_reviewed": False,
                            "needs_review": True,
                            "training_status": "quarantined_pending_license_and_annotation",
                            "text": "",
                            "page_spans": [],
                        }
                        try:
                            if not data.startswith(b"%PDF-"):
                                raise ValueError("File does not start with a PDF header")
                            reader = PdfReader(BytesIO(data), strict=False)
                            if reader.is_encrypted and not reader.decrypt(""):
                                raise ValueError("Password-protected PDF")
                            doc["page_count"] = len(reader.pages)
                            doc["extraction_truncated"] = len(reader.pages) > PAGE_LIMIT
                            pieces, offset = [], 0
                            for n, page in enumerate(reader.pages[:PAGE_LIMIT], 1):
                                text = page.extract_text() or ""
                                pieces.append(text)
                                doc["page_spans"].append({"page": n, "start": offset, "end": offset + len(text)})
                                offset += len(text) + 1
                            doc["text"] = "\n".join(pieces)
                            letters = [c for c in doc["text"] if c.isalpha()]
                            ratio = sum(c.isascii() for c in letters) / len(letters) if letters else 0
                            doc["latin_letter_ratio"] = round(ratio, 3)
                            # A script heuristic is not a verified language label.
                            doc["language_hint"] = "mostly_latin_script" if ratio > .9 and len(letters) >= 30 else "mixed_or_nonlatin_or_insufficient"
                            doc["extraction_status"] = "text_extracted" if len(doc["text"].strip()) >= 30 else "no_useful_text_without_ocr"
                        except Exception as error:
                            doc["extraction_status"] = "extraction_failed"
                            doc["error"] = str(error)[:250]
                        row["status"] = doc["extraction_status"]
                        statuses[doc["extraction_status"]] += 1
                        documents.append(doc)
                inventory.write(json.dumps(row, ensure_ascii=False) + "\n")
                if time.monotonic() - last > 15:
                    print(f"Inventoring archive; sampled {sampled} PDFs", flush=True)
                    last = time.monotonic()
    (ROOT / "sample_documents.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in documents), encoding="utf-8")
    total_members = sum(1 for _ in inventory_path.open(encoding="utf-8"))
    summary = {"archive_files": total_members, "sampled_pdfs": sampled, "statuses": dict(statuses),
               "mostly_latin_script_samples": sum(d.get("language_hint") == "mostly_latin_script" for d in documents),
               "truncated_samples": sum(d.get("extraction_truncated", False) for d in documents),
               "selection": "First 120 size-eligible PDFs in archive order; not a random or balanced sample",
               "page_limit": PAGE_LIMIT, "training_ready": False}
    (ROOT / "sample_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
