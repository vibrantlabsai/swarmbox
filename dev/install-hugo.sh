#!/usr/bin/env bash
# Install Hugo extended on a Linux CI runner, at the version the flake's
# nixpkgs pins (keep the two in step: `nix develop -c hugo version`).
set -euo pipefail
version=0.167.0
tmp=$(mktemp -d)
curl -fsSL -o "$tmp/hugo.tgz" \
  "https://github.com/gohugoio/hugo/releases/download/v${version}/hugo_extended_${version}_linux-amd64.tar.gz"
tar -C "$tmp" -xzf "$tmp/hugo.tgz" hugo
sudo install "$tmp/hugo" /usr/local/bin/hugo
hugo version
