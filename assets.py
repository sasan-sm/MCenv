# SPDX-License-Identifier: GPL-3.0-or-later
"""Packed, path-keyed bundled textures; no external dependencies at runtime."""
from pathlib import Path
import bpy

MOON_PHASES = ('full_moon', 'waning_gibbous', 'third_quarter',
               'waning_crescent', 'new_moon', 'waxing_crescent',
               'first_quarter', 'waxing_gibbous')


def bundled_image(relative_path):
    # Use a relative asset tag, not a basename: main/bb and all eight lunar
    # phases must remain distinct, including after saving/reopening a blend.
    for image in bpy.data.images:
        if image.get('mcenv_asset') == relative_path:
            return image
    path = Path(__file__).parent / 'textures' / relative_path
    image = bpy.data.images.load(str(path), check_existing=False)
    image.name = 'MCenv ' + relative_path
    image['mcenv_asset'] = relative_path
    image.alpha_mode = 'STRAIGHT'
    if relative_path.startswith('environment/'):
        # Vanilla sky sprites have black RGB backgrounds, not alpha. Record
        # this once so their material can blend additively, without black cards.
        pixels = list(image.pixels)
        image['mcenv_additive'] = all(a >= .999 for a in pixels[3::4])
    image.pack()
    return image


def block_image(settings, filename):
    return bundled_image('block/' + settings.block_texture_set.lower() + '/' + filename)


def sun_image(settings):
    variant = settings.sun_texture_set
    path = ('bb/sun.png' if variant == 'BB' else
            'bb/celestial/sun.png' if variant == 'BB_CELESTIAL' else
            'main/celestial/sun.png')
    return settings.sun_image or bundled_image('environment/' + path)


def moon_image(settings):
    phase = MOON_PHASES[int(settings.moon_phase)]
    return settings.moon_image or bundled_image(
        'environment/' + settings.moon_texture_set.lower() + '/celestial/moon/' + phase + '.png')
