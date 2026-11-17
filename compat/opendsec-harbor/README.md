# opendsec-harbor is now swarmbox-sdk[harbor]

This project was renamed, and the Harbor provider is now part of the SDK. Install `swarmbox-sdk[harbor]` and pass Harbor `--environment-import-path swarmbox_sdk.harbor:SwarmboxEnvironment`.

This package installs `swarmbox-sdk[harbor]` and keeps `opendsec_harbor:OpenDSecEnvironment` working, with a warning. 0.4.x is the last series under this name: it stays installable and keeps working with the 0.4 series of the new package, and gets no new features. With 0.5 of the new package installed, importing this one raises an `ImportError` that says so. If your CI turns warnings into errors, allow this one with `-W "ignore:opendsec-harbor is renamed:FutureWarning"`. Documentation: https://swarmbox.vibrantlabs.com
