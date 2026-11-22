# MCenv 1.0.0

A Minecraft-inspired environment add-on for **Blender 4.2+**. Open **Properties > World > MCenv > Create Environment**. The add-on and manifest remain version **1.0.0**; JSON environment presets use schema **1**.

![MCenv environment rendered in Blender — sun, moon, square stars, block clouds and fog](docs/images/Preview.png)

## Included features

- Direction-based sun, eight selectable moon phases and seeded square stars, plus custom image backgrounds.
- Separate directional light and ambient controls, day/night scene colors and optional twilight.
- Block clouds, optional textured ground and physical fog.
- Overworld, Nether and End atmospheres, filtered biome choices and Main/BB texture alternatives.
- Reversible tint binding for supported imported-world materials, including MCprep-compatible tint stages and RGBA grass-side overlays.
- Managed plant/leaf wind motion, custom vertex weights, texture-strip animation and a day-cycle option.
- Consistently aligned Animate, Wind and Blender tools foldouts; selected-object wind, JSON presets, reset and environment removal actions.

The shipped defaults use Java celestial-card proportions for the light angles and a documented **Vibrant Visuals moon/sun intensity ratio of 0.4/100**. Blender sunlight defaults to 3, moonlight to 0.012, sprite scales to 2.3 and 2.0, and independent light angles to about 8.578307 and 5.724810 degrees. These are Blender mappings, not a claim that Minecraft light levels are physical light units. Existing saved values are not overwritten automatically.

## Installation and use

Install `MCenv-1.0.0.zip` using Blender's Install from Disk action, then enable it. Back up scenes before replacing an installed copy; restart Blender when replacing the same version. Use Rendered View, or Scene World/Scene Lights in Material Preview. Read [USER_GUIDE.md](docs/USER_GUIDE.md) for the complete workflows, numeric defaults, derivations, references and limitations.

## Files and data

- `__init__.py`, `blender_manifest.toml`: metadata and registration.
- `properties.py`: scene settings, biome tables, lighting defaults and update callbacks.
- `engine.py`: owned environment data, shader layers, clouds, fog, ground and wind/animation nodes.
- `ui.py`, `overlay.py`: World panel and modal Time/Rotation dials.
- `operators.py`: creation/removal, image loading, material/animation actions and JSON presets.
- `biome_materials.py`: supported material detection, reversible copies and tint/overlay processing.
- `assets.py`, `textures/`: local bundled image loading and packing.
- `preferences.py`: preferences and Blender-managed uninstall.
- `LICENSE`: GPL-3.0-or-later for the code; supplied texture rights remain separate.

Settings, images, object references, bindings and node groups live in the `.blend`. Presets contain non-image environment values, not object lists, weights, keyframes or image files. No database, hosted service, API key or network connection is needed. There are no web routes or production deployment URLs: this is a locally installed Blender add-on, not a website.

## Scope and next checks

No terrain import/generation, weather simulation, automatic lunar calendar, End-flash animation, arbitrary-atlas playback or full Minecraft renderer is implemented. BB selects images rather than a complete Bedrock rendering mode. Later Blender releases, interactive UI appearance on the target GPU and large imported scenes should be checked in the user's installation. Recommended first checks: create an environment in a backed-up scene, reset or individually restore the new lighting defaults, verify night exposure, and apply biome/animation tools to a small selection.

Official Blender 4.2.0 headless validation covers registration, numeric defaults, shared header layout calls, lights, dimensions, presets/reset, animation/wind, material binding and save/reload. It is not an interactive GPU validation or a guarantee of pixel-identical Minecraft lighting.
