"""Vendor the pinned wingsearch card data into data/raw/.

Usage: python -m wingsim.data.fetch
"""
import pathlib
import urllib.request

COMMIT = "43e5036de9e68fa9c4fabaf4c760412a887adf05"
FILES = ("master.json", "bonus.json", "goals.json")
BASE = "https://raw.githubusercontent.com/navarog/wingsearch/{commit}/src/assets/data/{name}"
RAW = pathlib.Path(__file__).parent / "raw"


def main():
    RAW.mkdir(exist_ok=True)
    for name in FILES:
        url = BASE.format(commit=COMMIT, name=name)
        with urllib.request.urlopen(url, timeout=60) as r:
            data = r.read()
        (RAW / name).write_bytes(data)
        print(f"{name}: {len(data)} bytes")
    (RAW / "SOURCE.md").write_text(
        "Card data vendored from https://github.com/navarog/wingsearch\n"
        f"Commit: {COMMIT} (31 Aug 2026), path src/assets/data/\n\n"
        "wingsearch is GPL-3.0 and the card text belongs to Stonemaier Games.\n"
        "This is a private research copy. If the simulator is ever published,\n"
        "fetch the data at build time (python -m wingsim.data.fetch) instead of\n"
        "redistributing these files.\n"
    )


if __name__ == "__main__":
    main()
