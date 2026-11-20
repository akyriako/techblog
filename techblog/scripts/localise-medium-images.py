
#!/usr/bin/env python3
"""
The Backyard Rack — Medium Image Localiser

Convention:
    The first Medium image is the article cover.
    It becomes thumbnail.<format> and is removed from the body.

Usage:
    python3 scripts/localise-medium-images.py ARTICLE.md --dry-run
    python3 scripts/localise-medium-images.py ARTICLE.md

Only requires Python's standard library.
"""

import argparse
import hashlib
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


CDN = "https://miro.medium.com/v2/resize:fit:20000/"

IMAGE_RE = re.compile(
    r'!\[([^\]\n]*)\]\('
    r'(https://(?:cdn-images-\d+\.medium\.com|miro\.medium\.com)'
    r'/[^\s)]+)'
    r'\)'
)

MEDIUM_URL_RE = re.compile(
    r'https://(?:cdn-images-\d+\.medium\.com|miro\.medium\.com)'
    r'/[^\s)>\'"]+'
)

# IMAGE_ID_RE = re.compile(
#     r'^[01]\*[A-Za-z0-9_-]+\.(?:png|jpe?g|webp|gif)$',
#     re.IGNORECASE,
# )

IMAGE_ID_RE = re.compile(
    r'^[01]\*[A-Za-z0-9_-]+(?:\.(?:png|jpe?g|webp|gif))?$',
    re.IGNORECASE,
)

FORMATS = (".png", ".jpg", ".webp", ".gif")

# Marker prevents subsequent runs from treating the next
# article image as a new cover.
COVER_MARKER = "<!-- backyard-rack:medium-cover-migrated -->"


def detect_format(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"

    raise ValueError("Downloaded content is not a supported image")


def medium_id(url):
    filename = unquote(urlsplit(url).path).rsplit("/", 1)[-1]
    return filename if IMAGE_ID_RE.fullmatch(filename) else None


def local_name(image_id, extension):
    digest = hashlib.sha256(
        image_id.encode("utf-8")
    ).hexdigest()[:12]

    return f"medium-{digest}{extension}"


def find_existing(folder, image_id):
    for extension in FORMATS:
        candidate = folder / local_name(image_id, extension)

        if candidate.is_file():
            try:
                if detect_format(candidate.read_bytes()) == extension:
                    return candidate
            except OSError:
                pass

    return None


def download(image_id, timeout):
    url = CDN + image_id

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/*",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        data = response.read()

    return data, detect_format(data)


def save_atomic(path, data):
    temporary = path.with_name(path.name + ".tmp")

    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def frontmatter_bounds(content):
    match = re.match(r"\A---\r?\n", content)

    if not match:
        raise ValueError("Article has no YAML frontmatter")

    closing = re.search(
        r"(?m)^---\s*$",
        content[match.end():],
    )

    if not closing:
        raise ValueError("Frontmatter has no closing ---")

    end = match.end() + closing.start()
    closing_end = match.end() + closing.end()

    return end, closing_end


def yaml_quote(value):
    # JSON double-quoted strings are valid YAML scalars.
    import json
    return json.dumps(value, ensure_ascii=False)


def set_hero(content, filename, alt):
    front_end, closing_end = frontmatter_bounds(content)
    front = content[:front_end]
    rest = content[front_end:]

    src = f"./{filename}"

    # Support the Astro Theme Pure inline heroImage format.
    inline = re.search(
        r"(?m)^heroImage:\s*\{[^\n]*\}\s*$",
        front,
    )

    if inline:
        old = inline.group(0)

        color_match = re.search(
            r"""color:\s*(['"])(.*?)\1""",
            old,
        )

        properties = [f"src: {yaml_quote(src)}"]

        if alt:
            properties.append(
                f"alt: {yaml_quote(alt)}"
            )

        if color_match:
            properties.append(
                f"color: {yaml_quote(color_match.group(2))}"
            )

        replacement = (
            "heroImage: { "
            + ", ".join(properties)
            + " }"
        )

        front = front[:inline.start()] + replacement + front[inline.end():]

    else:
        # Handle existing block-style heroImage, or add one.
        block = re.search(
            r"(?m)^heroImage:\s*\n(?:^[ \t]+[^\n]*\n?)*",
            front,
        )

        lines = [
            "heroImage:",
            f"  src: {yaml_quote(src)}",
        ]

        if alt:
            lines.append(
                f"  alt: {yaml_quote(alt)}"
            )

        replacement = "\n".join(lines) + "\n"

        if block:
            old = block.group(0)
            color = re.search(
                r"""(?m)^\s+color:\s*(['"]?)(#[A-Fa-f0-9]+)\1\s*$""",
                old,
            )

            if color:
                replacement += (
                    f"  color: {yaml_quote(color.group(2))}\n"
                )

            front = (
                front[:block.start()]
                + replacement
                + front[block.end():]
            )
        else:
            front = front.rstrip("\n") + "\n" + replacement

    return front + rest


def remove_cover_image(content, image_match):
    # Remove only the image syntax. If it occupies a whole
    # line, remove that line too.
    start, end = image_match.span()

    line_start = content.rfind("\n", 0, start) + 1
    line_end = content.find("\n", end)

    if line_end == -1:
        line_end = len(content)

    line = content[line_start:line_end]

    if line.strip() == image_match.group(0):
        remove_end = min(line_end + 1, len(content))
        return content[:line_start] + content[remove_end:]

    return content[:start] + content[end:]


def main():
    parser = argparse.ArgumentParser(
        description="Localise Medium images for Astro articles"
    )

    parser.add_argument("article", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=60)

    args = parser.parse_args()

    article = args.article.resolve()

    if not article.is_file():
        parser.error(f"Article not found: {article}")

    folder = article.parent
    original = article.read_text(encoding="utf-8")

    try:
        front_end, closing_end = frontmatter_bounds(original)
    except ValueError as exc:
        parser.error(str(exc))

    # Only inspect the article body for Medium images.
    body = original[closing_end:]
    already_migrated = COVER_MARKER in body

    markdown_images = list(IMAGE_RE.finditer(body))

    cover_match = None
    cover_id = None

    if not already_migrated:
        for match in markdown_images:
            candidate = medium_id(match.group(2))

            if candidate:
                cover_match = match
                cover_id = candidate
                break

    # Collect all remote Medium URLs in the body, including
    # repeated references to the same image.
    images = {}

    for match in MEDIUM_URL_RE.finditer(body):
        url = match.group(0)
        image_id = medium_id(url)

        if image_id:
            images.setdefault(image_id, set()).add(url)

    if not images:
        print("No remote Medium images found.")
        return 0

    print("\nTHE BACKYARD RACK — MEDIUM IMAGE LOCALISER")
    print("=" * 54)
    print(f"Article: {article}")
    print(f"Images:  {len(images)}")
    print(f"Cover:   {'Already migrated' if already_migrated else (cover_id or 'Not found')}")
    print(f"Mode:    {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 54)

    if args.dry_run:
        for number, image_id in enumerate(images, 1):
            role = "COVER" if image_id == cover_id else "BODY"
            existing = find_existing(folder, image_id)
            action = "REUSE" if existing else "DOWNLOAD"

            print(
                f"[{number}/{len(images)}] "
                f"{role:5} {action:8} {image_id}"
            )

        print("\nDry run complete. No files changed.")
        return 0

    backup = article.with_name(
        article.name + ".before-medium-images.bak"
    )

    if not backup.exists():
        shutil.copy2(article, backup)

    print(f"\nBackup: {backup.name}\n")

    replacements = {}
    cover_path = None
    succeeded = 0
    failed = 0

    for number, (image_id, urls) in enumerate(images.items(), 1):
        is_cover = image_id == cover_id

        print(
            f"[{number}/{len(images)}] "
            f"{'COVER' if is_cover else 'BODY '} {image_id}"
        )

        try:
            existing = find_existing(folder, image_id)

            if existing:
                source = existing
                print(f"  REUSED: {source.name}")

            else:
                data, extension = download(
                    image_id,
                    args.timeout,
                )

                source = folder / local_name(
                    image_id,
                    extension,
                )

                save_atomic(source, data)
                print(
                    f"  DOWNLOADED: {source.name} "
                    f"({len(data):,} bytes)"
                )

                time.sleep(max(0, args.delay))

            if is_cover:
                thumbnail = folder / (
                    "thumbnail" + source.suffix
                )

                if thumbnail != source:
                    shutil.copy2(source, thumbnail)

                cover_path = thumbnail
                print(f"  HERO: {thumbnail.name}")

            for url in urls:
                replacements[url] = f"./{source.name}"

            succeeded += 1

        except Exception as exc:
            failed += 1
            print(f"  FAILED: {exc}")
            time.sleep(max(0, args.delay))

    updated_body = body

    # Remove cover before replacing other remote URLs.
    if cover_match and cover_path:
        updated_body = remove_cover_image(
            updated_body,
            cover_match,
        )

        updated_body = (
            "\n" + COVER_MARKER + "\n" + updated_body
        )

    # Replace all successfully localised image URLs.
    updated_body = MEDIUM_URL_RE.sub(
        lambda match: replacements.get(
            match.group(0),
            match.group(0),
        ),
        updated_body,
    )

    updated = original[:closing_end] + updated_body

    if cover_match and cover_path:
        updated = set_hero(
            updated,
            cover_path.name,
            cover_match.group(1),
        )

    if updated != original:
        save_atomic(
            article,
            updated.encode("utf-8"),
        )

    print("\n" + "=" * 54)
    print("MIGRATION SUMMARY")
    print("=" * 54)
    print(f"Images found:       {len(images)}")
    print(f"Images localised:   {succeeded}")
    print(f"Failed downloads:   {failed}")
    print(f"Cover migrated:     {'YES' if cover_path else 'NO / ALREADY DONE'}")
    print(f"Backup:             {backup.name}")
    print("=" * 54)

    if failed:
        print("\nSome Medium URLs remain unchanged for retry.")
        return 1

    print("\nBonza! Images localised, cover sorted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
