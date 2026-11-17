# opendsec is now swarmbox-sdk

This project was renamed. Install `swarmbox-sdk` and `import swarmbox_sdk`.

This package installs `swarmbox-sdk` and keeps `import opendsec` working, with a warning. 0.4.x is the last series under this name: it stays installable and keeps working with the 0.4 series of the new package, and gets no new features. With 0.5 of the new package installed, importing this one raises an `ImportError` that says so. If your CI turns warnings into errors, allow this one with `-W "ignore:opendsec is renamed:FutureWarning"`. Documentation: https://swarmbox.vibrantlabs.com
