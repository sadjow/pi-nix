# pi-nix

[Pi](https://pi.dev) coding agent for Nix, packaged from its official standalone releases. Hourly GitHub Actions checks keep the package current after validation on macOS and Linux, on both ARM64 and x86-64.

## Run or install

```sh
nix run github:sadjow/pi-nix
nix run github:sadjow/pi-nix -- --version
nix profile install github:sadjow/pi-nix
```

The package provides the `pi` command and embeds its runtime. A global Node.js or Bun installation is not needed to launch Pi. Extensions that invoke external tools still need those tools; installing npm-based Pi packages requires npm in your environment.

## Home Manager

Add the input to your flake:

```nix
inputs.pi-nix.url = "github:sadjow/pi-nix";
```

Include its package in your Home Manager module:

```nix
home.packages = [ inputs.pi-nix.packages.${pkgs.system}.default ];
```

The module must receive `inputs` from your flake, for example through `extraSpecialArgs`. The flake also exposes `packages.<system>.pi`, `apps.<system>.pi`, and `overlays.default`. The overlay provides `pkgs.pi-coding-agent`.

Using the package output retains this repository's tested Nixpkgs pin. Using the overlay, or making `pi-nix.inputs.nixpkgs` follow your own input, builds against your Nixpkgs instead. Other revisions are permitted but are not covered by this repository's CI.

The default dependency input tracks Nixpkgs 26.05, which still provides Intel macOS packages. Pi's release pin advances independently of that dependency release line.

Update the installed version explicitly:

```sh
nix flake update pi-nix
home-manager build --flake .#your-configuration
home-manager switch --flake .#your-configuration
```

For a profile installation, use `nix profile upgrade pi-nix` (check `nix profile list` for the installed entry name). Pin a release with `github:sadjow/pi-nix/v<version>` or a Git commit when desired.

## Packaging

[`sources.json`](sources.json) records the version and SHA-256 hashes. [`platforms.json`](platforms.json) owns the mapping between Nix systems, upstream archives, and CI runners.

The package preserves the entire upstream archive under `libexec/pi`, including themes, native platform helpers, WebAssembly assets, documentation, examples, and HTML export templates. Its wrapper supplies Bash, ripgrep, and fd and sets `PI_PACKAGE_DIR` so assets resolve inside the Nix store.

Version notifications and telemetry default to disabled through `PI_SKIP_VERSION_CHECK=1` and `PI_TELEMETRY=0`; users can override these environment variables. The package leaves Pi's agent directory, credentials, sessions, settings, and extensions under Pi's control. Use Nix to upgrade the application.

Upstream release archives are downloaded directly and verified by Nix. This repository does not require a dedicated binary cache or a cache credential.

## Release updates

The **Update Pi** workflow runs hourly and can be dispatched manually. Scheduling and runner availability can delay execution, so hourly checks are not a one-hour delivery guarantee.

1. Fetch the latest stable release from `earendil-works/pi`.
2. Download every configured platform archive and verify its SHA-256 against `SHA256SUMS` and the GitHub asset digest when available.
3. Run the same Nix checks used for pull requests on every configured platform.
4. Commit only the tested `sources.json` and atomically push `main` and its version tag.

Network, checksum, or test failures leave the published pin unchanged. The final push also fails if `main` advanced during validation. The workflow needs only the repository's built-in `GITHUB_TOKEN`; write access is limited to the final publish job. Candidate checks run before publishing because pushes made with that token do not trigger another push workflow.

Changes to packaging and workflows use ordinary pull requests. GitHub Actions dependency pins receive weekly Dependabot updates. The Pi updater leaves `flake.lock` unchanged; update Nixpkgs separately and run the complete check matrix.

## Development

```sh
nix develop
python3 scripts/update.py
python3 scripts/update.py --version <version>
nix fmt .
nix flake check --all-systems --no-build
nix flake check --print-build-logs
nix build
```

`--version` explicitly selects a stable upstream release and allows intentional downgrades. The default updater refuses automatic downgrades. Before the first commit, stage new files or use `nix flake check 'path:.'` so Nix can see them.

Checks cover updater failure handling, workflow syntax, package startup, extension dependency imports, native platform helpers, built-in themes, RPC state, HTML export, and bundled command-line tools. Smoke checks use a temporary agent directory and make no model requests. They do not validate provider authentication or every third-party extension.

## License

The Nix packaging is MIT licensed. Pi and its bundled dependencies retain their upstream licenses. This is an independent packaging project, inspired by [claude-code-nix](https://github.com/sadjow/claude-code-nix); it is not an official Pi distribution.
