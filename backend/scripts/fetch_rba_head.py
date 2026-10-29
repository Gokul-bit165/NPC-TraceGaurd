"""Download the first N rows' worth of the RBA data set without fetching the whole 1.1 GB zip.

The release asset is a zip whose CSV is deflate-compressed, so the first bytes of the file decode to the first
rows of the CSV. This reads a byte range from the GitHub release and writes a CSV that ends on a complete line.

    python scripts/fetch_rba_head.py --bytes 60000000 --out data/rba_head.csv

Use it when Zenodo or Kaggle are blocked on your network. The full file is at https://zenodo.org/records/6782156
(CC BY 4.0, Wiefling, Jorgensen, Thunem, Lo Iacono).
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

import httpx

URL = "https://github.com/das-group/rba-dataset/releases/download/v1.0.0/rba-dataset.zip"


def fetch(nbytes: int) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=300) as c:
        r = c.get(URL, headers={"Range": f"bytes=0-{nbytes}"})
        if r.status_code not in (200, 206):
            sys.exit(f"download failed: HTTP {r.status_code}")
        return r.content


def extract_csv_head(blob: bytes) -> bytes:
    pos = 0
    while pos + 30 < len(blob):
        if struct.unpack("<I", blob[pos:pos + 4])[0] != 0x04034B50:
            break
        _v, flag, _method, _t, _d, _crc, csize, _usize, nlen, elen = struct.unpack("<HHHHHIIIHH", blob[pos + 4:pos + 30])
        name = blob[pos + 30:pos + 30 + nlen].decode()
        start = pos + 30 + nlen + elen
        if name.endswith(".csv"):
            data = zlib.decompressobj(-15).decompress(blob[start:])
            cut = data.rfind(b"\n")
            return data[:cut + 1]
        pos = start + (0 if name.endswith("/") else csize)
    sys.exit("no CSV entry found in the downloaded range; try a larger --bytes value")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bytes", type=int, default=60_000_000)
    ap.add_argument("--out", default="data/rba_head.csv")
    a = ap.parse_args()
    csv_bytes = extract_csv_head(fetch(a.bytes))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(csv_bytes)
    print(f"wrote {out} ({len(csv_bytes) / 1e6:.1f} MB, {csv_bytes.count(b'\n') - 1:,} rows)")


if __name__ == "__main__":
    main()
