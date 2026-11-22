# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (BoolProperty, FloatProperty, IntProperty, EnumProperty,
                       FloatVectorProperty, StringProperty, PointerProperty, CollectionProperty)


def linear(v):
    return v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4


def rgb(hexcode):
    return tuple(linear(int(hexcode[i:i+2], 16) / 255) for i in (0, 2, 4))


# Java-style fallback tint values; the supplied side overlay is bundled separately.
BIOMES = {
    'PLAINS': ('Plains', '91bd59', '77ab2f', '3f76e4'),
    'FOREST': ('Forest', '79c05a', '59ae30', '3f76e4'),
    'BIRCH_FOREST': ('Birch Forest', '88bb67', '6ba941', '3f76e4'),
    'DARK_FOREST': ('Dark Forest', '507a32', '59ae30', '3f76e4'),
    'TAIGA': ('Taiga', '86b783', '68a464', '3f76e4'),
    'SNOWY': ('Snowy Plains', '80b497', '60a17b', '3938c9'),
    'DESERT': ('Desert', 'bfb755', 'aea42a', '3f76e4'),
    'SAVANNA': ('Savanna', 'bfb755', 'aea42a', '3f76e4'),
    'JUNGLE': ('Jungle', '59c93c', '30bb0b', '3f76e4'),
    'SWAMP': ('Swamp', '6a7039', '6a7039', '617b64'),
    'MANGROVE': ('Mangrove Swamp', '6a7039', '8db127', '3a7a6a'),
    'FLOWER_FOREST': ('Flower Forest', '79c05a', '59ae30', '3f76e4'),
    'OLD_GROWTH_BIRCH': ('Old Growth Birch Forest', '88bb67', '6ba941', '3f76e4'),
    'OLD_GROWTH_PINE': ('Old Growth Pine Taiga', '86b87f', '68a55f', '3f76e4'),
    'OLD_GROWTH_SPRUCE': ('Old Growth Spruce Taiga', '86b783', '68a464', '3f76e4'),
    'SNOWY_TAIGA': ('Snowy Taiga', '80b497', '60a17b', '3d57d6'),
    'WINDSWEPT_HILLS': ('Windswept Hills', '8ab689', '6da36b', '3f76e4'),
    'MEADOW': ('Meadow', '83bb6d', '63a948', '0e4ecf'),
    'GROVE': ('Grove', '80b497', '60a17b', '3f76e4'),
    'SNOWY_SLOPES': ('Snowy Slopes', '80b497', '60a17b', '3f76e4'),
    'FROZEN_PEAKS': ('Frozen Peaks', '80b497', '60a17b', '3f76e4'),
    'JAGGED_PEAKS': ('Jagged Peaks', '80b497', '60a17b', '3f76e4'),
    'STONY_PEAKS': ('Stony Peaks', '9abe4b', '82ac1e', '3f76e4'),
    'SPARSE_JUNGLE': ('Sparse Jungle', '64c73f', '3eb80f', '3f76e4'),
    'BAMBOO_JUNGLE': ('Bamboo Jungle', '59c93c', '30bb0b', '3f76e4'),
    'CHERRY_GROVE': ('Cherry Grove', 'b6db61', 'b6db61', '5db7ef'),
    'MUSHROOM_FIELDS': ('Mushroom Fields', '55c93f', '2bbb0f', '3f76e4'),
    'RIVER': ('River', '8eb971', '71a74d', '3f76e4'),
    'FROZEN_RIVER': ('Frozen River', '80b497', '60a17b', '3938c9'),
    'BEACH': ('Beach', '91bd59', '77ab2f', '3f76e4'),
    'SNOWY_BEACH': ('Snowy Beach', '83b593', '64a278', '3d57d6'),
    'STONY_SHORE': ('Stony Shore', '8ab689', '6da36b', '3f76e4'),
    'WARM_OCEAN': ('Warm Ocean', '8eb971', '71a74d', '43d5ee'),
    'LUKEWARM_OCEAN': ('Lukewarm Ocean', '8eb971', '71a74d', '45adf2'),
    'COLD_OCEAN': ('Cold Ocean', '8eb971', '71a74d', '3d57d6'),
    'FROZEN_OCEAN': ('Frozen Ocean', '80b497', '60a17b', '3938c9'),
    'BADLANDS': ('Badlands', '90814d', '9e814d', '3f76e4'),
    'OCEAN': ('Ocean', '8eb971', '71a74d', '3f76e4'),
    'PALE_GARDEN': ('Pale Garden', '778272', '878d76', '3f76e4'),
    # Append presets to keep numeric enum IDs stable.
    'DAPPLED_FOREST': ('Dappled Forest', 'df6827', 'e68e30', '375154'),
    'CUSTOM': ('Custom', '91bd59', '77ab2f', '3f76e4'),
    'NETHER_WASTES': ('Nether Wastes', 'bfb755', 'aea42a', '3f76e4'),
    'SOUL_SAND_VALLEY': ('Soul Sand Valley', 'bfb755', 'aea42a', '3f76e4'),
    'CRIMSON_FOREST': ('Crimson Forest', 'bfb755', 'aea42a', '3f76e4'),
    'WARPED_FOREST': ('Warped Forest', 'bfb755', 'aea42a', '3f76e4'),
    'BASALT_DELTAS': ('Basalt Deltas', 'bfb755', 'aea42a', '3f76e4'),
    'THE_END': ('The End', '8eb971', '71a74d', '3f76e4'),
    'SMALL_END_ISLANDS': ('Small End Islands', '8eb971', '71a74d', '3f76e4'),
    'END_MIDLANDS': ('End Midlands', '8eb971', '71a74d', '3f76e4'),
    'END_HIGHLANDS': ('End Highlands', '8eb971', '71a74d', '3f76e4'),
    'END_BARRENS': ('End Barrens', '8eb971', '71a74d', '3f76e4'),
    'THE_VOID': ('The Void', '8eb971', '71a74d', '3f76e4'),
}

# Java biome membership: The Void is a superflat Overworld biome, not an End biome.
NETHER_BIOMES = ('NETHER_WASTES', 'SOUL_SAND_VALLEY', 'CRIMSON_FOREST', 'WARPED_FOREST', 'BASALT_DELTAS')
END_BIOMES = ('THE_END', 'SMALL_END_ISLANDS', 'END_MIDLANDS', 'END_HIGHLANDS', 'END_BARRENS')
DIMENSION_ITEMS = [('OVERWORLD', 'Over world', 'Overworld and The Void superflat biome'),
                   ('NETHER', 'Nether', 'Constant dim atmosphere; no sun, moon, stars or clouds'),
                   ('END', 'The End', 'Static textured sky and constant dim illumination')]
DIMENSION_DEFAULTS = {'OVERWORLD': 'PLAINS', 'NETHER': 'NETHER_WASTES', 'END': 'THE_END'}
NETHER_FOG = {'NETHER_WASTES': '330808', 'SOUL_SAND_VALLEY': '1b4745',
              'CRIMSON_FOREST': '330303', 'WARPED_FOREST': '1a051a', 'BASALT_DELTAS': '685f70'}


def biome_dimension(key):
    return 'NETHER' if key in NETHER_BIOMES else 'END' if key in END_BIOMES else 'OVERWORLD'



# Temperature drives the Overworld's Java-style sky hue.
CLIMATE = {
    'PLAINS': (.8,.4), 'FOREST': (.7,.8), 'BIRCH_FOREST': (.6,.6),
    'DARK_FOREST': (.7,.8), 'DAPPLED_FOREST': (.6,.6),
    'TAIGA': (.25,.8), 'SNOWY': (0,.5),
    'DESERT': (2,0), 'SAVANNA': (2,0), 'JUNGLE': (.95,.9),
    'SWAMP': (.8,.9), 'MANGROVE': (.8,.9), 'BADLANDS': (2,0),
    'FLOWER_FOREST': (.7,.8), 'OLD_GROWTH_BIRCH': (.6,.6),
    'OLD_GROWTH_PINE': (.3,.8), 'OLD_GROWTH_SPRUCE': (.25,.8),
    'SNOWY_TAIGA': (-.5,.4), 'WINDSWEPT_HILLS': (.2,.3),
    'MEADOW': (.5,.8), 'GROVE': (-.2,.8), 'SNOWY_SLOPES': (-.3,.9),
    'FROZEN_PEAKS': (-.7,.9), 'JAGGED_PEAKS': (-.7,.9), 'STONY_PEAKS': (1,.3),
    'SPARSE_JUNGLE': (.95,.8), 'BAMBOO_JUNGLE': (.95,.9),
    'CHERRY_GROVE': (.5,.8), 'MUSHROOM_FIELDS': (.9,1),
    'RIVER': (.5,.5), 'FROZEN_RIVER': (0,.5), 'BEACH': (.8,.4),
    'SNOWY_BEACH': (.05,.3), 'STONY_SHORE': (.2,.3),
    'OCEAN': (.5,.5), 'WARM_OCEAN': (.5,.5), 'LUKEWARM_OCEAN': (.5,.5),
    'COLD_OCEAN': (.5,.5), 'FROZEN_OCEAN': (0,.5), 'PALE_GARDEN': (.7,.8),
}


# Explicit numeric values keep biome selections stable in saved .blend files.
_LEGACY_BIOMES = ['PLAINS','FOREST','BIRCH_FOREST','DARK_FOREST','TAIGA','SNOWY',
                  'DESERT','SAVANNA','JUNGLE','SWAMP','MANGROVE','BADLANDS','OCEAN','CUSTOM']
_BIOME_IDS = {key:index for index,key in enumerate(_LEGACY_BIOMES)}
for _key in BIOMES:
    if _key not in _BIOME_IDS: _BIOME_IDS[_key] = len(_BIOME_IDS)
BIOME_ITEMS = [(key,value[0],'',0,_BIOME_IDS[key]) for key,value in BIOMES.items()]
# Keep callback strings and lists alive: Blender retains pointers to enum strings.
DIMENSION_BIOME_ITEMS = {dim: [item for item in BIOME_ITEMS
    if item[0] == 'CUSTOM' or biome_dimension(item[0]) == dim]
    for dim, _, _ in DIMENSION_ITEMS}


def biome_items(self, context):
    return DIMENSION_BIOME_ITEMS[self.dimension]


def update_dimension(self, context):
    from . import engine
    scene = self.id_data
    ptr = scene.as_pointer()
    if ptr in engine._BUSY: return
    old = self.get('_active_dimension', 'OVERWORLD')
    number = self.get('biome', _BIOME_IDS['PLAINS'])
    old_key = next((key for key, value in _BIOME_IDS.items() if value == number), 'PLAINS')
    self['_biome_' + old] = old_key
    self['_fog_' + old] = [self.fog_distance, self.fog_size]
    choice = self.get('_biome_' + self.dimension, DIMENSION_DEFAULTS[self.dimension])
    if choice not in {item[0] for item in DIMENSION_BIOME_ITEMS[self.dimension]}:
        choice = DIMENSION_DEFAULTS[self.dimension]
    engine._BUSY.add(ptr)
    try:
        self.biome = choice
        distances = self.get('_fog_' + self.dimension, (10., 86.) if self.dimension=='NETHER' else (80., 160.))
        self.fog_distance, self.fog_size = distances
        self['_active_dimension'] = self.dimension
    finally:
        engine._BUSY.discard(ptr)
    update(self, context)


# Java dry_foliage.png samples / explicit overrides from Minecraft Wiki > Biome.
# Keep separate from green foliage: leaf litter must not turn grass-green.
DRY_FOLIAGE = {
    'PLAINS':'a37546', 'FOREST':'a36d46', 'BIRCH_FOREST':'a37246',
    'DARK_FOREST':'7b5334', 'TAIGA':'9a764f', 'SNOWY':'8f7a5a',
    'DESERT':'a38046', 'SAVANNA':'a38046', 'JUNGLE':'a36346',
    'SWAMP':'7b5334', 'MANGROVE':'7b5334', 'FLOWER_FOREST':'a36d46',
    'OLD_GROWTH_BIRCH':'a37246', 'OLD_GROWTH_PINE':'9c754d',
    'OLD_GROWTH_SPRUCE':'9a764f', 'SNOWY_TAIGA':'8f7a5a',
    'WINDSWEPT_HILLS':'977752', 'MEADOW':'a17148', 'GROVE':'8f7a5a',
    'SNOWY_SLOPES':'8f7a5a', 'FROZEN_PEAKS':'8f7a5a', 'JAGGED_PEAKS':'8f7a5a',
    'STONY_PEAKS':'927957', 'SPARSE_JUNGLE':'a36346', 'BAMBOO_JUNGLE':'a36346',
    'CHERRY_GROVE':'a17148', 'MUSHROOM_FIELDS':'a36246', 'RIVER':'a17448',
    'FROZEN_RIVER':'8f7a5a', 'BEACH':'a37546', 'SNOWY_BEACH':'917958',
    'STONY_SHORE':'977752', 'WARM_OCEAN':'a17448', 'LUKEWARM_OCEAN':'a17448',
    'COLD_OCEAN':'a17448', 'FROZEN_OCEAN':'8f7a5a', 'BADLANDS':'9e814d',
    'OCEAN':'a17448', 'PALE_GARDEN':'a0a69c', 'DAPPLED_FOREST':'8c3a04',
}
TEXTURE_SETS = [('MAIN','Main','Bundled main textures (default)'),
                ('BB','BB','Bundled alternative textures')]


def update(self, context):
    from .engine import sync
    scene = self.id_data
    if isinstance(scene, bpy.types.Scene) and self.enabled:
        sync(scene)


def update_time(self, context):
    # The day loops while dragging: past 24 keeps counting from 0 and below 0
    # wraps back to the evening hours, instead of sticking at the limits.
    t = self.time % 24
    if t != self.time:
        self.time = t
    update(self, context)


def update_rotation(self, context):
    # Full turns wrap into the -180..180 heading range, matching the dial.
    r = (self.rotation + 180) % 360 - 180
    if r != self.rotation:
        self.rotation = r
    update(self, context)


def color(name, value):
    return FloatVectorProperty(name=name, subtype='COLOR', size=3,
                               min=0, max=1, default=rgb(value), update=update)


class MCENV_MaterialBinding(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)
    slot_index: IntProperty()
    original: PointerProperty(type=bpy.types.Material)
    bound: PointerProperty(type=bpy.types.Material)
    original_link: StringProperty(default='DATA')


def animation_update(self, context):
    from . import engine
    scene=self.id_data
    if isinstance(scene,bpy.types.Scene): engine.sync(scene)


def animation_mode_update(self, context):
    from . import engine
    if self.object: engine.animation_weights(self.object,self.mode)
    animation_update(self,context)


class MCENV_AnimationObject(bpy.types.PropertyGroup):
    object: PointerProperty(type=bpy.types.Object)
    enabled: BoolProperty(name='Animate object', default=True, update=animation_update)
    mode: EnumProperty(name='Motion', items=[('AUTO','Auto','Leaves use flutter; other meshes use root-pinned sway'),('GRASS','Grass / plant','Pin the base of each disconnected mesh island'),('LEAVES','Leaves','Full-weight spatial flutter for leaf blocks'),('CUSTOM','Custom weights','Keep or paint MCENV_Wind weights')], default='AUTO', update=animation_mode_update)
    influence: FloatProperty(name='Influence', default=1, min=0, soft_max=3, update=animation_update)


class MCENV_Settings(bpy.types.PropertyGroup):
    animation_objects: CollectionProperty(type=MCENV_AnimationObject)
    animation_candidate: PointerProperty(name='Object', type=bpy.types.Object, description='Choose a mesh in this scene and press Add, or use Add Selected')
    animate: BoolProperty(name='Animate', description='Enable day-cycle, opted-in texture and listed-object animation', default=True, update=update)
    texture_animate: BoolProperty(name='Texture animate', description='Play opted-in vertical texture strips; add strips with the button below', default=True, update=update)
    fold_animate: BoolProperty(default=False, options={'SKIP_SAVE'})
    material_bindings: CollectionProperty(type=MCENV_MaterialBinding)
    biome_scope: EnumProperty(name='Apply to', items=[('SCENE','Entire imported scene','All editable meshes in this scene'),('SELECTED','Selected objects','Only selected editable meshes')], default='SCENE')
    biome_texture_mode: EnumProperty(name='Texture colors', items=[('AUTO','Auto','Reuse active MCprep tint; compensate baked colors when possible'),('GRAYSCALE','Grayscale','Multiply untinted grayscale textures'),('COLORED','Already colored','Compensate estimated baked texture color')], default='AUTO')
    block_texture_set: EnumProperty(name='Block textures', items=TEXTURE_SETS, default='MAIN', update=update)
    sun_texture_set: EnumProperty(name='Sun textures', items=TEXTURE_SETS + [('BB_CELESTIAL','BB Celestial','Alternative bb/celestial/sun.png')], default='MAIN', update=update)
    moon_texture_set: EnumProperty(name='Moon textures', items=TEXTURE_SETS, default='MAIN', update=update)
    grass_side_overlay: PointerProperty(name='Grass side overlay', type=bpy.types.Image, description='Optional RGBA grass_block_side_overlay.png; empty uses the bundled default. Uses the side diffuse UVs, not a normal map', update=update)
    biome_atmosphere: BoolProperty(name='Biome sky color', description='Use temperature-based Overworld sky color without overwriting manual day/night colors; Nether and End always use their dimension atmosphere', default=False, update=update)
    enabled: BoolProperty(default=False)
    owner_id: StringProperty(options={'HIDDEN'})
    previous_world: PointerProperty(type=bpy.types.World)
    previous_world_empty: BoolProperty(default=False)
    time: FloatProperty(name='Time', description='Hours, 0 = midnight, 6 = sunrise, 12 = noon; drag past either end to wrap around the day', default=9, update=update_time)
    rotation: FloatProperty(name='Rotation', description='World heading in degrees; drag across the ends to wrap around', default=0, update=update_rotation)
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
    stars_count: IntProperty(name='Star count', description='Number of stars in the night sky', default=420, min=0, soft_max=2000, max=10000, update=update)
    stars_size: FloatProperty(name='Star size', default=.045, min=.005, max=.15, update=update)
    stars_size_random: FloatProperty(name='Random star size', description='0 keeps every star the same size; higher values give the stars random sizes around Star size', default=0, min=0, max=1, subtype='FACTOR', update=update)
    stars_strength: FloatProperty(name='Star brightness', default=1, min=0, soft_max=10, update=update)
    clouds: BoolProperty(name='Clouds', default=True, update=update)
    cloud_mode: EnumProperty(name='Mode', items=[('NORMAL','Normal','Solid block clouds'),('FADED','Faded','Semi-transparent block clouds'),('FLAT','Flat','Flat square cloud tiles')], update=update)
    cloud_image: PointerProperty(name='Cloud texture', type=bpy.types.Image, description='Mask: bright pixels become clouds; use alpha for transparency', update=update)
    cloud_speed: FloatProperty(name='Speed', default=1, soft_min=-10, soft_max=10, update=update)
    cloud_offset: FloatProperty(name='Offset', default=0, update=update)
    cloud_height: FloatProperty(name='Height', default=128, min=1, soft_max=300, update=update)
    cloud_size: FloatProperty(name='Scale', description='Width of the base cloud field; cloud blocks keep this block size while Size grows the field', default=384, min=16, soft_max=2048, update=update)
    cloud_blocks: IntProperty(name='Size', description='Random cloud blocks added on every side; each step grows the field by one block per side', default=0, min=0, soft_max=64, max=128, update=update)
    cloud_thickness: FloatProperty(name='Thickness', default=4, min=0, soft_max=20, update=update)
    cloud_coverage: FloatProperty(name='Coverage', default=.42, min=0, max=1, update=update)
    cloud_seed: IntProperty(name='Seed', default=17, min=0, update=update)
    ground: BoolProperty(name='Ground', description='Optional background plane, independent of the imported Minecraft terrain', default=False, update=update)
    ground_follow_biome: BoolProperty(name='Surface follows biome', description='Follow the biome surface color and shading (grass, sand, snow, stone or water); keeps the selected texture and never changes imported blocks', default=False, update=update)
    ground_image: PointerProperty(name='Ground texture', type=bpy.types.Image, description='Optional ground image; empty uses textures/block/main/grass_block_top.png', update=update)
    dimension: EnumProperty(name='Dimension', items=DIMENSION_ITEMS, default='OVERWORLD', update=update_dimension)
    end_texture_set: EnumProperty(name='End sky textures', items=TEXTURE_SETS, default='MAIN', update=update)
    biome: EnumProperty(name='Biome', items=biome_items, default=0, update=update)
    grass_color: color('Grass', '91bd59')
    foliage_color: color('Foliage', '77ab2f')
    dry_foliage_color: color('Dry foliage / leaf litter', 'a37546')
    water_color: color('Water', '3f76e4')
    oak_color: color('Oak leaves', '77ab2f')
    spruce_color: color('Spruce leaves', '619961')
    birch_color: color('Birch leaves', '80a755')
    jungle_color: color('Jungle leaves', '77ab2f')
    acacia_color: color('Acacia leaves', '77ab2f')
    dark_oak_color: color('Dark oak leaves', '77ab2f')
    mangrove_color: color('Mangrove leaves', '92c648')
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
    fold_sun: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_sky: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_colors: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_cloud: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_ground: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_fog: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_wind: BoolProperty(default=False, options={'SKIP_SAVE'})
    fold_tools: BoolProperty(default=False, options={'SKIP_SAVE'})


def register():
    bpy.utils.register_class(MCENV_MaterialBinding)
    bpy.utils.register_class(MCENV_AnimationObject)
    bpy.utils.register_class(MCENV_Settings)
    bpy.types.Scene.mc_env = PointerProperty(type=MCENV_Settings)


def unregister():
    del bpy.types.Scene.mc_env
    bpy.utils.unregister_class(MCENV_Settings)
    bpy.utils.unregister_class(MCENV_AnimationObject)
    bpy.utils.unregister_class(MCENV_MaterialBinding)
