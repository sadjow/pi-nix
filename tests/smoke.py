import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import time


def smoke(binary, version):
    with tempfile.TemporaryDirectory(prefix="pi-nix-smoke-") as temporary:
        directory = Path(temporary)
        session = directory / "session.jsonl"
        timestamp = "2026-01-01T00:00:00.000Z"
        entries = [
            {"type": "session", "version": 3, "id": "00000000-0000-4000-8000-000000000001",
             "timestamp": timestamp, "cwd": str(directory)},
            {"type": "message", "id": "00000001", "parentId": None, "timestamp": timestamp,
             "message": {"role": "user", "content": "Synthetic package smoke test", "timestamp": 1767225600000}},
        ]
        session.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
        environment = {
            "PATH": os.environ["PATH"],
            "PI_CODING_AGENT_DIR": str(directory / "agent"),
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            "TERM": "dumb",
        }
        result = subprocess.run(
            [binary, "--version"], env=environment, cwd=directory,
            text=True, capture_output=True, timeout=30, check=True,
        )
        assert result.stdout.strip() == version, result.stdout
        subprocess.run(
            [binary, "--help"], env=environment, cwd=directory,
            capture_output=True, timeout=30, check=True,
        )
        extension = directory / "smoke.ts"
        extension.write_text('''
import { getPackageDir } from "@earendil-works/pi-coding-agent";
import { Type } from "@sinclair/typebox";
import { readFileSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { join } from "node:path";
export default function (pi) {
  for (const theme of ["dark", "light"]) {
    JSON.parse(readFileSync(join(getPackageDir(), "theme", `${theme}.json`), "utf8"));
  }
  const nativeDir = join(getPackageDir(), "native");
  const helpers = readdirSync(nativeDir, { recursive: true }).filter(path => path.endsWith(".node"));
  if (helpers.length === 0) throw new Error("Missing native platform helpers");
  const require = createRequire(join(getPackageDir(), "package.json"));
  for (const helper of helpers) require(join(nativeDir, helper));
  if (Type.String().type !== "string") throw new Error("Extension dependency resolution failed");
  pi.registerCommand("nix-smoke", {
    description: "Nix package smoke check",
    handler: async () => {},
  });
}
''')
        process = subprocess.Popen(
            [binary, "--mode", "rpc", "--session", str(session), "--no-extensions",
             "--no-skills", "--no-prompt-templates", "--no-themes", "-e", str(extension)],
            env=environment, cwd=directory, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                buffer = b""

                def request(command):
                    nonlocal buffer
                    process.stdin.write(json.dumps(command).encode() + b"\n")
                    process.stdin.flush()
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            event = json.loads(line)
                            assert event.get("type") != "extension_error", event
                            if event.get("id") == command["id"] and event.get("type") == "response":
                                assert event["success"], event
                                return event.get("data", {})
                        if selector.select(timeout=1):
                            chunk = os.read(process.stdout.fileno(), 65536)
                            if not chunk:
                                raise AssertionError("Pi exited before its RPC response")
                            buffer += chunk
                    raise AssertionError(f"Timed out waiting for {command['type']}")

                commands = request({"id": "commands", "type": "get_commands"})
                assert any(command["name"] == "nix-smoke" for command in commands["commands"]), commands
                state = request({"id": "state", "type": "get_state"})
                assert state["isStreaming"] is False, state
                result = request({"id": "bash", "type": "bash", "command": "rg --version && fd --version"})
                assert result["exitCode"] == 0, result
                exported = directory / "session.html"
                request({"id": "export", "type": "export_html", "outputPath": str(exported)})
                assert "<html" in exported.read_text().lower(), "Missing HTML export assets"
        finally:
            process.terminate()
            try:
                _, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate()
            if stderr:
                print(stderr.decode(), file=sys.stderr)
        print(f"Pi {version}: version, startup, extensions, native helpers, themes, RPC, HTML export, and tools passed")


if __name__ == "__main__":
    smoke(str(Path(sys.argv[1]).resolve()), sys.argv[2])
