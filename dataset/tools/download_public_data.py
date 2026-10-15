"""Resume and verify the preserved public university-notice archive."""
from pathlib import Path
import hashlib
import json
import time
import requests

ROOT = Path(__file__).resolve().parents[1] / "public"
DEST = ROOT / "quarantine" / "durg_university" / "archive"
URL = "https://huggingface.co/datasets/sameerbanchhor/durg-university-notices/resolve/main/notices_dataset.tar.gz"
EXPECTED_SIZE = 2794910093
EXPECTED_SHA256 = "62bc93a6c0271f6d41d3e624b79df3526a43a1f92ffa7fd65cb6635389338270"


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    target = DEST / "notices_dataset.tar.gz"
    partial = target.with_suffix(target.suffix + ".part")
    if not target.exists():
        offset = partial.stat().st_size if partial.exists() else 0
        if offset < EXPECTED_SIZE:
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            response = requests.get(URL, headers=headers, stream=True, timeout=(30, 90))
            response.raise_for_status()
            if offset and response.status_code != 206:
                offset = 0  # Server ignored Range; restart instead of appending corruption.
            if offset and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                raise RuntimeError("Unexpected range response; partial file preserved")
            last = time.monotonic()
            with response, partial.open("ab" if offset else "wb") as output:
                for chunk in response.iter_content(chunk_size=4 * 1024 * 1024):
                    if not chunk:
                        continue
                    output.write(chunk)
                    offset += len(chunk)
                    if time.monotonic() - last >= 10:
                        print(f"Downloaded {offset / 1e6:.0f} / {EXPECTED_SIZE / 1e6:.0f} MB ({offset / EXPECTED_SIZE:.1%})", flush=True)
                        last = time.monotonic()
        if partial.stat().st_size != EXPECTED_SIZE:
            raise RuntimeError("Size mismatch; partial file retained for recovery")
        candidate = partial
    else:
        candidate = target
    print("Verifying archive SHA-256", flush=True)
    digest = hashlib.sha256()
    with candidate.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("Checksum mismatch; file not promoted to complete")
    if candidate != target:
        candidate.rename(target)
    record = {
        "source_url": URL,
        "relative_path": str(target.relative_to(ROOT)),
        "bytes": target.stat().st_size,
        "sha256": digest.hexdigest(),
        "status": "downloaded_verified",
        "license_status": "unspecified_in_inspected_source",
        "training_status": "quarantined_pending_provenance_and_license_review",
        "contains_project_labels": False,
    }
    (DEST.parent / "archive_manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
