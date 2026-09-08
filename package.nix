{ lib
, stdenv
, fetchurl
, makeBinaryWrapper
, autoPatchelfHook
, bash
, fd
, ripgrep
, python3
}:

let
  sources = builtins.fromJSON (builtins.readFile ./sources.json);
  platforms = builtins.fromJSON (builtins.readFile ./platforms.json);
  system = stdenv.hostPlatform.system;
in
stdenv.mkDerivation {
  pname = "pi-coding-agent";
  inherit (sources) version;

  src = fetchurl {
    url = "https://github.com/earendil-works/pi/releases/download/v${sources.version}/${platforms.${system}.asset}";
    hash = sources.hashes.${system};
  };

  sourceRoot = "pi";
  dontBuild = true;
  # Bun's embedded program and upstream macOS signatures must survive fixup.
  dontStrip = true;
  dontPatchShebangs = true;
  dontFixDarwinDylibNames = true;

  nativeBuildInputs = [ makeBinaryWrapper ]
    ++ lib.optionals stdenv.hostPlatform.isLinux [ autoPatchelfHook ];
  buildInputs = lib.optionals stdenv.hostPlatform.isLinux [ stdenv.cc.cc.lib ];

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/libexec/pi" "$out/bin"
    cp -R . "$out/libexec/pi/"
    makeBinaryWrapper "$out/libexec/pi/pi" "$out/bin/pi" \
      --set PI_PACKAGE_DIR "$out/libexec/pi" \
      --set-default PI_SKIP_VERSION_CHECK 1 \
      --set-default PI_TELEMETRY 0 \
      --prefix PATH : ${lib.makeBinPath [ bash fd ripgrep ]}
    runHook postInstall
  '';

  doInstallCheck = true;
  nativeInstallCheckInputs = [ python3 ];
  installCheckPhase = ''
    runHook preInstallCheck
    python3 ${./tests/smoke.py} "$out/bin/pi" "${sources.version}"
    runHook postInstallCheck
  '';

  meta = {
    description = "Extensible terminal coding agent with multi-provider support";
    homepage = "https://pi.dev";
    changelog = "https://github.com/earendil-works/pi/releases/tag/v${sources.version}";
    license = lib.licenses.mit;
    sourceProvenance = [ lib.sourceTypes.binaryNativeCode ];
    platforms = builtins.attrNames platforms;
    mainProgram = "pi";
  };
}
