{
  # Optional: everything here also runs with uv, just and Hugo installed any
  # other way (CI does exactly that). `nix develop`, or direnv with `use flake`.
  description = "swarmbox SDK and docs dev environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            uv
            python312
            just
            hugo # docs site (site/)
          ];
        };
      });
}
