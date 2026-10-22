#!/usr/bin/env python3
"""Compare protected native part PDFs visually, ignoring PDF metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageChops


def compare(before, after, output):
    report = {"before": str(before), "after": str(after), "dpi": 120, "pages": []}
    for name, path in (("before", before), ("after", after)):
        report[name + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="protected-pdf-") as temp:
        folders = []
        for name, path in (("before", before), ("after", after)):
            folder = Path(temp) / name
            folder.mkdir()
            subprocess.run(["pdftoppm", "-r", "120", "-png", str(path), str(folder / "page")],
                           check=True, capture_output=True)
            folders.append(sorted(folder.glob("page-*.png"),
                                  key=lambda p: int(p.stem.rsplit("-", 1)[1])))
        report["page_counts"] = [len(files) for files in folders]
        report["identical"] = len(folders[0]) == len(folders[1]) and bool(folders[0])
        for number, (a, b) in enumerate(zip(*folders), 1):
            with Image.open(a) as ia, Image.open(b) as ib:
                ia, ib = ia.convert("RGB"), ib.convert("RGB")
                same = ia.size == ib.size and ia.tobytes() == ib.tobytes()
                bbox = ImageChops.difference(ia, ib).getbbox() if ia.size == ib.size else None
                report["pages"].append({"page": number, "identical": same, "difference_bbox": bbox})
                report["identical"] = report["identical"] and same
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.before, args.after, args.output)
    print(json.dumps({k: result[k] for k in ("identical", "page_counts")}, indent=2))
    raise SystemExit(0 if result["identical"] else 1)
