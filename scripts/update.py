#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "earendil-works/pi"
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def read_url(url):
    headers = {"User-Agent": "pi-nix-release-updater"}
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    with urlopen(Request(url, headers=headers), timeout=120) as response:
        return response.read()


def release_sources(release, platforms, fetch=read_url):
    tag = release["tag_name"]
    version = tag.removeprefix("v")
    if tag != f"v{version}" or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Expected a stable vMAJOR.MINOR.PATCH release tag")
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Expected a published stable release")
    assets = {asset["name"]: asset for asset in release["assets"]}
    base_url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
    required = ["SHA256SUMS", *(platform["asset"] for platform in platforms.values())]
    for name in required:
        if name not in assets or assets[name]["browser_download_url"] != base_url + name:
            raise ValueError(f"Missing or unexpected release asset: {name}")
    checksums = {}
    for line in fetch(base_url + "SHA256SUMS").decode().splitlines():
        checksum, name = line.split(maxsplit=1)
        name = name.lstrip("*")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", checksum) or name in checksums:
            raise ValueError("Invalid or duplicate release checksum")
        checksums[name] = checksum.lower()
    hashes = {}
    for system, platform in platforms.items():
        name = platform["asset"]
        digest = hashlib.sha256(fetch(base_url + name)).digest()
        if digest.hex() != checksums.get(name):
            raise ValueError(f"Checksum mismatch for {name}")
        github_digest = assets[name].get("digest")
        if github_digest and github_digest != f"sha256:{digest.hex()}":
            raise ValueError(f"GitHub asset digest mismatch for {name}")
        hashes[system] = "sha256-" + base64.b64encode(digest).decode()
    return {"version": version, "hashes": hashes}


def update(root=ROOT, version=None, fetch=read_url):
    if version and not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Version must be MAJOR.MINOR.PATCH")
    platforms = json.loads((root / "platforms.json").read_text())
    destination = root / "sources.json"
    current = json.loads(destination.read_text()) if destination.exists() else None
    endpoint = f"tags/v{version}" if version else "latest"
    release = json.loads(fetch(f"https://api.github.com/repos/{REPOSITORY}/releases/{endpoint}"))
    latest = release["tag_name"].removeprefix("v")
    if (not VERSION_PATTERN.fullmatch(latest) or release["tag_name"] != f"v{latest}"
            or release.get("draft") or release.get("prerelease")):
        raise ValueError("Expected a published stable release")
    if version and version != latest:
        raise ValueError("Release does not match the requested version")
    if current and not version:
        if tuple(map(int, latest.split("."))) < tuple(map(int, current["version"].split("."))):
            raise ValueError("Refusing an automatic downgrade")
        if current["version"] == latest and set(current["hashes"]) == set(platforms):
            if all(re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", h) for h in current["hashes"].values()):
                print(f"Pi {latest} is already packaged")
                return False
    sources = release_sources(release, platforms, fetch)
    if current == sources:
        print(f"Pi {latest} is already packaged")
        return False
    with tempfile.NamedTemporaryFile(mode="w", dir=root, delete=False) as temporary:
        temporary.write(json.dumps(sources, indent=2) + "\n")
        temporary_path = Path(temporary.name)
    temporary_path.replace(destination)
    print(f"Updated Pi to {sources['version']} with verified archives for {len(platforms)} platforms")
    return True


def main():
    parser = argparse.ArgumentParser(description="Pin a Pi release after verifying every platform archive")
    parser.add_argument("--version", help="Explicit stable version; defaults to the latest release")
    args = parser.parse_args()
    try:
        update(version=args.version)
    except Exception as error:
        print(f"Update failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
