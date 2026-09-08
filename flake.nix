{
  description = "Pi coding agent packaged from official releases, with hourly update checks";

  # The 26.05 release still provides the Intel macOS dependencies Pi needs.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      inherit (nixpkgs) lib;
      platforms = builtins.fromJSON (builtins.readFile ./platforms.json);
      forAllSystems = lib.genAttrs (builtins.attrNames platforms);
      pkgsFor = forAllSystems (system: import nixpkgs { inherit system; });
      packageFor = system: pkgsFor.${system}.callPackage ./package.nix { };
    in
    {
      packages = forAllSystems (system: rec {
        pi = packageFor system;
        default = pi;
      });

      apps = forAllSystems (system: rec {
        pi = {
          type = "app";
          program = lib.getExe self.packages.${system}.pi;
          meta.description = "Pi coding agent";
        };
        default = pi;
      });

      overlays.default = final: prev: {
        pi-coding-agent = final.callPackage ./package.nix { };
      };

      checks = forAllSystems (system:
        let pkgs = pkgsFor.${system}; in
        {
          package = self.packages.${system}.pi;
          updater = pkgs.runCommand "pi-updater-tests"
            {
              nativeBuildInputs = [ pkgs.python3 ];
            } ''
            cp -R ${self} source
            chmod -R u+w source
            cd source
            python3 -m unittest discover -s tests -p 'test_*.py' -v
            touch "$out"
          '';
          workflows = pkgs.runCommand "pi-workflow-check"
            {
              nativeBuildInputs = [ pkgs.actionlint pkgs.shellcheck ];
            } ''
            cd ${self}
            actionlint .github/workflows/*.yml
            touch "$out"
          '';
        });

      devShells = forAllSystems (system:
        let pkgs = pkgsFor.${system}; in
        {
          default = pkgs.mkShell {
            packages = [ pkgs.python3 pkgs.actionlint pkgs.shellcheck pkgs.nixpkgs-fmt ];
          };
        });

      formatter = forAllSystems (system: pkgsFor.${system}.nixpkgs-fmt);
    };
}
