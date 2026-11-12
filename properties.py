# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (BoolProperty, FloatProperty, IntProperty, EnumProperty,
                       FloatVectorProperty, StringProperty, PointerProperty)


def linear(v):
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def rgb(hexcode):
    return tuple(linear(int(hexcode[i:i+2], 16) / 255) for i in (0, 2, 4))


# Original preset approximations; not extracted Minecraft textures or colormaps.
BIOMES = {
    'PLAINS': ('Plains', '91bd59', '77ab2f', '3f76e4'),
    'FOREST': ('Forest', '79c05a', '59ae30', '3f76e4'),
    'BIRCH_FOREST': ('Birch Forest', '88bb67', '6ba941', '3f76e4'),
    'DARK_FOREST': ('Dark Forest', '507a32', '507a32', '3f76e4'),
    'TAIGA': ('Taiga', '86b783', '68a464', '3f76e4'),
    'SNOWY': ('Snowy Plains', '80b497', '60a17b', '3938c9'),
    'DESERT': ('Desert', 'bfb755', 'aea42a', '3f76e4'),
    'SAVANNA': ('Savanna', 'bfb755', 'aea42a', '3f76e4'),
    'JUNGLE': ('Jungle', '59c93c', '30bb0b', '3f76e4'),
    'SWAMP': ('Swamp', '6a7039', '6a7039', '617b64'),
    'MANGROVE': ('Mangrove Swamp', '6a7039', '8db127', '3a7a6a'),
    'BADLANDS': ('Badlands', '90814d', '9e814d', '3f76e4'),
    'OCEAN': ('Ocean', '91bd59', '77ab2f', '3f76e4'),
    'CUSTOM': ('Custom', '91bd59', '77ab2f', '3f76e4'),
}


def update(self, context):
    from .engine import sync
    scene = self.id_data
    if isinstance(scene, bpy.types.Scene) and self.enabled:
        sync(scene)


def color(name, value):
    return FloatVectorProperty(name=name, subtype='COLOR', size=3,
                               min=0, max=1, default=rgb(value), update=update)


class MCENV_Settings(bpy.types.PropertyGroup):
    enabled: BoolProperty(default=False)
    owner_id: StringProperty(options={'HIDDEN'})
    previous_world: PointerProperty(type=bpy.types.World)
    previous_world_empty: BoolProperty(default=False)
    time: FloatProperty(name='Time', description='Hours, 0 = midnight, 6 = sunrise, 12 = noon', default=9, min=0, max=24, update=update)
    rotation: FloatProperty(name='Rotation', description='World heading in degrees', default=0, soft_min=-180, soft_max=180, update=update)
    sun_angle: FloatProperty(name='Sunlight angle', description='Angular size in degrees; controls soft shadows', default=.526, min=0, max=180, update=update)
    sun_strength: FloatProperty(name='Strength', default=3, min=0, soft_max=10, update=update)
    ambient_strength: FloatProperty(name='Ambient strength', default=.5, min=0, soft_max=3, update=update)
    night_strength: FloatProperty(name='Moonlight strength', default=.12, min=0, soft_max=2, update=update)
    sky_mode: EnumProperty(name='Sky background', items=[('MINECRAFT','Minecraft','Original procedural block-style sky'),('CUSTOM','Custom','Use your own background image')], default='MINECRAFT', update=update)
    background_image: PointerProperty(name='Background image', type=bpy.types.Image, update=update)
    background_type: EnumProperty(name='Image type', items=[('EQUIRECTANGULAR','Equirectangular','Panoramic image / HDRI'),('IMAGE','Image','Camera-facing background'),('BOX','Box','Box-projected repeating background')], update=update)
    background_stretch: BoolProperty(name='Stretch', default=True, update=update)
    background_rotation: FloatProperty(name='Image rotation', default=0, update=update)
    sun_image: PointerProperty(name='Sun texture', type=bpy.types.Image, update=update)
    sun_tilt: FloatProperty(name='Sun angle', default=0, update=update)
    sun_scale: FloatProperty(name='Sun scale', default=1, min=0, soft_max=5, update=update)
    moon_image: PointerProperty(name='Moon texture', type=bpy.types.Image, update=update)
    moon_phase: EnumProperty(name='Moon phase', items=[(str(i), n, '') for i,n in enumerate(['Full Moon','Waning Gibbous','Last Quarter','Waning Crescent','New Moon','Waxing Crescent','First Quarter','Waxing Gibbous'])], update=update)
    moon_tilt: FloatProperty(name='Moon angle', default=0, update=update)
    moon_scale: FloatProperty(name='Moon scale', default=1, min=0, soft_max=5, update=update)
    stars_size: FloatProperty(name='Star size', default=.045, min=.005, max=.15, update=update)
    stars_random_size: FloatProperty(name='Star size randomness', description='0 keeps every star the same size; higher values give stars randomly different sizes', default=0, min=0, soft_max=2, update=update)
    stars_count: IntProperty(name='Star count', description='Number of stars in the sky', default=420, min=0, soft_max=2000, update=update)
    stars_strength: FloatProperty(name='Star brightness', default=1, min=0, soft_max=10, update=update)
    clouds: BoolProperty(name='Clouds', default=True, update=update)
    cloud_mode: EnumProperty(name='Mode', items=[('NORMAL','Normal','Solid block clouds'),('FADED','Faded','Semi-transparent block clouds'),('FLAT','Flat','Flat square cloud tiles')], update=update)
    cloud_image: PointerProperty(name='Cloud texture', type=bpy.types.Image, description='Mask: bright pixels become clouds; use alpha for transparency', update=update)
    cloud_speed: FloatProperty(name='Speed', default=1, soft_min=-10, soft_max=10, update=update)
    cloud_offset: FloatProperty(name='Offset', default=0, update=update)
    cloud_height: FloatProperty(name='Height', default=128, min=1, soft_max=300, update=update)
    cloud_size: FloatProperty(name='Size', default=384, min=16, soft_max=2048, update=update)
    cloud_thickness: FloatProperty(name='Thickness', default=4, min=0, soft_max=20, update=update)
    cloud_coverage: FloatProperty(name='Coverage', default=.42, min=0, max=1, update=update)
    cloud_seed: IntProperty(name='Seed', default=17, min=0, update=update)
    ground: BoolProperty(name='Ground', default=True, update=update)
    ground_type: EnumProperty(name='Ground block', items=[('GRASS','Grass','Biome-tinted grass'),('DIRT','Dirt','Brown dirt'),('SAND','Sand','Warm sand'),('STONE','Stone','Grey stone'),('SNOW','Snow','Snow'),('WATER','Water','Biome water')], update=update)
    ground_size: FloatProperty(name='Size', default=1024, min=1, soft_max=4096, update=update)
    ground_height: FloatProperty(name='Height', default=-.02, update=update)
    ground_tile: FloatProperty(name='Texture tile size', default=1, min=.01, soft_max=16, update=update)
    ground_image: PointerProperty(name='Ground texture', type=bpy.types.Image, update=update)
    ground_normal: PointerProperty(name='Normal map', type=bpy.types.Image, update=update)
    ground_material: PointerProperty(name='Roughness map', type=bpy.types.Image, update=update)
    biome: EnumProperty(name='Biome', items=[(k,v[0],'') for k,v in BIOMES.items()], default='PLAINS', update=update)
    grass_color: color('Grass', '91bd59')
    foliage_color: color('Foliage', '77ab2f')
    water_color: color('Water', '3f76e4')
    oak_color: color('Oak leaves', '77ab2f')
    spruce_color: color('Spruce leaves', '619961')
    birch_color: color('Birch leaves', '80a755')
    jungle_color: color('Jungle leaves', '77ab2f')
    acacia_color: color('Acacia leaves', '77ab2f')
    dark_oak_color: color('Dark oak leaves', '77ab2f')
    mangrove_color: color('Mangrove leaves', '8db127')
    day_sky: color('Sky', '78a7ff')
    day_clouds: color('Clouds', 'ffffff')
    day_sunlight: color('Sunlight', 'fff7e2')
    day_ambient: color('Ambient', '666f8e')
    night_sky: color('Sky', '020204')
    night_clouds: color('Clouds', '191925')
    night_stars: color('Stars', '3f3f3f')
    night_ambient: color('Ambient', '0e0e18')
    twilight: BoolProperty(name='Twilight', description='Blend warm sunrise/sunset colors near the horizon', default=True, update=update)
    fog: BoolProperty(name='Fog', default=True, update=update)
    fog_sky: BoolProperty(name='Affect sky', default=True, update=update)
    fog_custom: BoolProperty(name='Custom sky color', default=False, update=update)
    fog_color: color('Sky fog color', 'a6bfff')
    fog_custom_object: BoolProperty(name='Custom object color', default=False, update=update)
    fog_object_color: color('Object fog color', 'a6bfff')
    fog_distance: FloatProperty(name='Distance', description='Distance before atmospheric volume starts, relative to active camera', default=80, min=0, soft_max=1000, update=update)
    fog_size: FloatProperty(name='Size', description='Distance over which fog becomes dense', default=160, min=1, soft_max=2000, update=update)
    fog_height: FloatProperty(name='Height', default=100, min=1, soft_max=1000, update=update)
    wind: BoolProperty(name='Wind', default=True, update=update)
    wind_speed: FloatProperty(name='Speed', default=1, min=0, soft_max=10, update=update)
    wind_strength: FloatProperty(name='Strength', default=.15, min=0, soft_max=2, update=update)
    wind_direction: FloatProperty(name='Direction', default=45, update=update)
    wind_directional_speed: FloatProperty(name='Directional speed', default=.2, min=0, soft_max=5, update=update)
    wind_directional_strength: FloatProperty(name='Directional strength', default=.5, min=0, soft_max=3, update=update)
    texture_fps: FloatProperty(name='Texture animation speed', description='FPS for opted-in vertical-strip image textures; does not change scene FPS', default=20, min=0, soft_max=60, update=update)
    preview_day_cycle: BoolProperty(name='Animate day cycle', default=False, update=update)
    cycle_frames: IntProperty(name='Frames per day', default=2400, min=24, update=update)
    tint_kind: EnumProperty(name='Tint kind', items=[(x,x.replace('_',' ').title(),'') for x in ['GRASS','FOLIAGE','WATER','OAK','SPRUCE','BIRCH','JUNGLE','ACACIA','DARK_OAK','MANGROVE']])


def register():
    bpy.utils.register_class(MCENV_Settings)
    bpy.types.Scene.mc_env = PointerProperty(type=MCENV_Settings)


def unregister():
    del bpy.types.Scene.mc_env
    bpy.utils.unregister_class(MCENV_Settings)
