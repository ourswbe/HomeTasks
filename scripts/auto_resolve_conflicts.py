#!/usr/bin/env python3
import argparse
from pathlib import Path


def resolve_file(path: Path) -> tuple[bool, int, int]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    out = []
    i = 0
    blocks = 0
    resolved = 0

    while i < len(lines):
        line = lines[i]
        if not line.startswith("<<<<<<< "):
            out.append(line)
            i += 1
            continue

        blocks += 1
        i += 1
        current = []
        while i < len(lines) and not lines[i].startswith("======="):
            current.append(lines[i])
            i += 1

        if i >= len(lines):
            out.append("<<<<<<< BROKEN_CONFLICT\n")
            out.extend(current)
            break

        i += 1
        incoming = []
        while i < len(lines) and not lines[i].startswith(">>>>>>> "):
            incoming.append(lines[i])
            i += 1

        if i >= len(lines):
            out.append("<<<<<<< BROKEN_CONFLICT\n")
            out.extend(current)
            out.append("=======\n")
            out.extend(incoming)
            break

        i += 1

        if "".join(current).strip() == "".join(incoming).strip():
            out.extend(current)
            resolved += 1
        else:
            out.append("<<<<<<< CURRENT\n")
            out.extend(current)
            out.append("=======\n")
            out.extend(incoming)
            out.append(">>>>>>> INCOMING\n")

    new_text = "".join(out)
    changed = new_text != text
    if changed:
        path.write_text(new_text, encoding="utf-8")

    return changed, blocks, resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["."])
    args = parser.parse_args()

    files = []
    for p in args.paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        else:
            for file in path.rglob("*"):
                if file.is_file() and ".git" not in file.parts:
                    files.append(file)

    total_blocks = 0
    total_resolved = 0
    touched = 0

    for file in files:
        try:
            text = file.read_text(encoding="utf-8")
        except Exception:
            continue
        if "<<<<<<< " not in text:
            continue

        changed, blocks, resolved = resolve_file(file)
        total_blocks += blocks
        total_resolved += resolved
        if changed:
            touched += 1

    print(f"conflict_blocks={total_blocks}")
    print(f"auto_resolved={total_resolved}")
    print(f"files_touched={touched}")
    print("run `rg \"^(<<<<<<<|=======|>>>>>>>)\" .` to verify remaining conflicts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
