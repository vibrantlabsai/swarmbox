# The old package names

Before 0.4.0 this project was called opendsec, and its packages were `opendsec`
and `opendsec-harbor`. PyPI projects cannot be renamed, so these two packages
keep those names working: each installs the new package and is that package
under its old import name. The Harbor provider is part of `swarmbox-sdk` from
0.4.0, installed with its `harbor` extra.

| Old | New |
|---|---|
| `pip install opendsec` | `pip install swarmbox-sdk` |
| `import opendsec` | `import swarmbox_sdk` |
| `pip install opendsec-harbor` | `pip install 'swarmbox-sdk[harbor]'` |
| `opendsec_harbor:OpenDSecEnvironment` | `swarmbox_sdk.harbor:SwarmboxEnvironment` |
| `opendsec.OpendsecError` | `swarmbox_sdk.SwarmboxError` |
| `OPENDSEC_URL`, `OPENDSEC_TOKEN`, … | `SWARMBOX_URL`, `SWARMBOX_TOKEN`, … |

Importing either old package warns (`FutureWarning`).

0.4.x is their last series: they pin the new packages below 0.5, so an
install of `opendsec` that names no version keeps working after 0.5.0 removes
the old names from the new packages. Nothing is released under the old names
after that.
