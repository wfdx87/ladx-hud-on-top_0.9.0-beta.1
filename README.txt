HUD ON TOP — 0.9.0-beta.1

First public beta.
Supports English Link's Awakening DX Rev2 and toruzz VWF(ladxvwf10) engine layout. 

The VWF patch is external and is not included.
https://www.romhacking.net/hacks/2414/


PYTHON PATCHER (recommended)
Requires Python 3. Run patch_hud.py to choose a ROM, or:
    python patch_hud.py your-rom.gbc
    python patch_hud.py your-rom.gbc --output your-new-rom.gbc
One self-contained script detects native/VWF code and checks hook/free-space
signatures before writing. It creates a new ROM plus an IPS for that input.
It preserves the source and ROM size (1 MiB or 2 MiB).
Use the Python patcher for compatible modified ROMs, rather than applying
an IPS designed for a clean source. Existing HUD installations are
rejected; use a clean pre-HUD backup instead of stacking or upgrading patches.
Other hacks may change hooks, reserved ROM space, interrupt handling, window
rendering or sprite storage and can be incompatible. Recognition of WFHUDTOP
identifies the patch; validation still checks the surrounding engine layout.

IPS FILES
hud_on_top_0.9.0-beta.1_Native_Rev2.ips: apply only to the clean 1 MiB English Rev2 ROM.
hud_on_top_0.9.0-beta.1_Original_VWF.ips: apply only to the exact 1 MiB original VWF ROM
made by applying ladxvwf10.ips to that same clean Rev2 ROM.
These are separate because the original VWF changes code addresses. An IPS
cannot auto-detect the source.

SOURCE IDENTITIES
Link's Awakening DX Rev2 source SHA-256: 5dee5816ed9b46cfc4a2d94f275e555dd3c5080eca00ded975a41a881a6d4c06
ladxvwf10 source SHA-256: 5d56ba64325fc164648571883afe91e551b9367879faeb405aa304b47f2c2063

VERSION INFORMATION
Version: 0.9.0-beta.1. Both IPS variants have the same version.
The ROM header contains numeric version 0.9.0 plus the beta.1 prerelease label.

TESTING
Full playthrough needed.
Start with a new game or an ordinary in-game save. Do not reuse emulator states
created with older code. Keep your original ROM and saves backed up.

PERMISSION / DISCLAIMER
You may use, modify and redistribute this HUD patch in your own hacks.
This permission covers the custom HUD patch code only, not Nintendo material
or third-party dependencies. No game ROM or original VWF patch is supplied.
This unofficial project is not affiliated with Nintendo. Supplied as-is,
without warranty; use legally obtained source material and comply with local
law.
