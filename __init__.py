# SPDX-License-Identifier: GPL-3.0-or-later
bl_info = {
    "name": "MCenv", "author": "MCenv contributors <sasan.sm23@gmail.com>", "version": (0, 6, 0),
    "blender": (4, 2, 0), "location": "Properties > World > MCenv",
    "description": "Minecraft-inspired environment, sky, clouds, biomes, fog and wind",
    "category": "Lighting",
}

from . import properties, engine, operators, ui, overlay, preferences


def register():
    properties.register()
    operators.register()
    ui.register()
    overlay.register()
    preferences.register()
    engine.register()


def unregister():
    engine.unregister()
    preferences.unregister()
    overlay.unregister()
    ui.unregister()
    operators.unregister()
    properties.unregister()
