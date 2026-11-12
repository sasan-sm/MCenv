# SPDX-License-Identifier: GPL-3.0-or-later
"""mc-env panel inside World Properties, using native Blender styling."""
import bpy
from . import engine


# Shared section definitions keep custom and Blender-native editors in sync.
def section_fields(p, section):
    if section=='sun': return ['sun_angle','sun_strength','ambient_strength','night_strength']
    if section=='sky':
        if p.sky_mode=='CUSTOM':
            return ['sky_mode','background_image','background_type','background_stretch' if p.background_type=='IMAGE' else 'background_rotation']
        return ['sky_mode','sun_image','sun_tilt','sun_scale','moon_image','moon_phase','moon_tilt','moon_scale','stars_size','stars_random_size','stars_count','stars_strength']
    if section=='cloud': return ['cloud_mode','cloud_image','cloud_speed','cloud_offset','cloud_height','cloud_size','cloud_thickness','cloud_coverage','cloud_seed']
    if section=='ground': return ['ground_type','ground_image','ground_normal','ground_material','ground_size','ground_height','ground_tile']
    if section=='fog':
        return ['fog_sky','fog_custom']+(['fog_color'] if p.fog_custom else [])+['fog_custom_object']+(['fog_object_color'] if p.fog_custom_object else [])+['fog_distance','fog_size','fog_height']
    if section=='wind': return ['wind_speed','wind_strength','wind_direction','wind_directional_speed','wind_directional_strength']
    return []


BIOME_FIELDS=['grass_color','foliage_color','water_color','oak_color','spruce_color','birch_color','jungle_color','acacia_color','dark_oak_color','mangrove_color']


def field(layout,p,key):
    prop=p.bl_rna.properties[key]
    if prop.type=='POINTER':
        col=layout.column(align=True); col.label(text=prop.name)
        row=col.row(align=True); row.template_ID(p,key)
        op=row.operator('mcenv.load_image',text='',icon='FILE_FOLDER'); op.property_name=key
    else: layout.prop(p,key)


def color_grid(layout,p,keys):
    grid=layout.grid_flow(columns=2,even_columns=True,align=True)
    for key in keys:
        col=grid.column(align=True)
        col.label(text=p.bl_rna.properties[key].name)
        col.prop(p,key,text='')


class _McenvWorldPanel:
    """Shared registration info for every mc-env panel in the Properties editor."""
    bl_space_type='PROPERTIES'
    bl_region_type='WINDOW'
    bl_context='world'

    @classmethod
    def poll(cls,context): return context.scene is not None


class MCENV_PT_world(_McenvWorldPanel,bpy.types.Panel):
    bl_label='mc-env'
    bl_idname='MCENV_PT_world'

    def draw_header(self,context): self.layout.label(text='',icon='WORLD')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        if not p.enabled:
            layout.label(text='Minecraft-inspired environment')
            layout.operator('mcenv.create',icon='WORLD')
            return
        # Native draggable sliders with the keyframe (Animate Property) column.
        layout.use_property_split=True; layout.use_property_decorate=True
        col=layout.column(align=True)
        col.prop(p,'time'); col.prop(p,'rotation')
        err=engine._ERRORS.get(context.scene.as_pointer())
        if err:
            split=layout.column(); split.use_property_split=False
            box=split.box(); box.alert=True; box.label(text=err,icon='ERROR')
        layout.prop(p,'texture_fps')


class MCENV_PT_world_sun(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Sunlight'
    bl_idname='MCENV_PT_world_sun'
    bl_order=0
    bl_options={'DEFAULT_CLOSED'}

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        for key in section_fields(p,'sun'): field(layout,p,key)


class MCENV_PT_world_sky(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Sky background'
    bl_idname='MCENV_PT_world_sky'
    bl_order=1
    bl_options={'DEFAULT_CLOSED'}

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        for key in section_fields(p,'sky'): field(layout,p,key)


class MCENV_PT_world_cloud(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Clouds'
    bl_idname='MCENV_PT_world_cloud'
    bl_order=2
    bl_options={'DEFAULT_CLOSED'}

    def draw_header(self,context): self.layout.prop(context.scene.mc_env,'clouds',text='')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        col=layout.column(); col.enabled=p.clouds
        for key in section_fields(p,'cloud'): field(col,p,key)


class MCENV_PT_world_ground(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Ground'
    bl_idname='MCENV_PT_world_ground'
    bl_order=3
    bl_options={'DEFAULT_CLOSED'}

    def draw_header(self,context): self.layout.prop(context.scene.mc_env,'ground',text='')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        col=layout.column(); col.enabled=p.ground
        for key in section_fields(p,'ground'): field(col,p,key)


class MCENV_PT_world_biome(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Biome'
    bl_idname='MCENV_PT_world_biome'
    bl_order=4

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        layout.prop(p,'biome')
        if p.biome=='CUSTOM':
            split=layout.column(); split.use_property_split=False
            color_grid(split,p,BIOME_FIELDS)


class MCENV_PT_world_colors(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Scene colors'
    bl_idname='MCENV_PT_world_colors'
    bl_order=5
    bl_options={'DEFAULT_CLOSED'}

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        layout.label(text='Day scene colors:')
        col=layout.column(align=True)
        for key in ['day_sky','day_clouds','day_sunlight','day_ambient']: col.prop(p,key)
        layout.label(text='Night scene colors:')
        col=layout.column(align=True)
        for key in ['night_sky','night_clouds','night_stars','night_ambient']: col.prop(p,key)
        layout.prop(p,'twilight')


class MCENV_PT_world_fog(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Fog'
    bl_idname='MCENV_PT_world_fog'
    bl_order=6
    bl_options={'DEFAULT_CLOSED'}

    def draw_header(self,context): self.layout.prop(context.scene.mc_env,'fog',text='')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        col=layout.column(); col.enabled=p.fog
        for key in section_fields(p,'fog'): field(col,p,key)


class MCENV_PT_world_wind(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Wind'
    bl_idname='MCENV_PT_world_wind'
    bl_order=7
    bl_options={'DEFAULT_CLOSED'}

    def draw_header(self,context): self.layout.prop(context.scene.mc_env,'wind',text='')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        col=layout.column(); col.enabled=p.wind
        for key in section_fields(p,'wind'): field(col,p,key)


class MCENV_PT_world_tools(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Blender tools'
    bl_idname='MCENV_PT_world_tools'
    bl_order=8
    bl_options={'DEFAULT_CLOSED'}

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=False; layout.use_property_decorate=False
        layout.prop(p,'preview_day_cycle')
        if p.preview_day_cycle: layout.prop(p,'cycle_frames')
        col=layout.column(align=True)
        col.operator('mcenv.bind_wind',icon='MOD_WAVE'); col.operator('mcenv.remove_wind')
        layout.prop(p,'tint_kind')
        col=layout.column(align=True)
        col.operator('mcenv.bind_tint',icon='COLOR'); col.operator('mcenv.remove_tint')
        layout.operator('mcenv.bind_atlas',icon='TEXTURE')
        row=layout.row(align=True); row.operator('mcenv.import_preset',text='Import preset'); row.operator('mcenv.export_preset',text='Export preset')
        layout.label(text='Image files are saved with .blend, not presets.',icon='INFO')
        row=layout.row(align=True)
        row.operator('mcenv.reset',icon='LOOP_BACK'); row.operator('mcenv.remove',icon='TRASH')


class MCENV_PT_world_uninstall(_McenvWorldPanel,bpy.types.Panel):
    bl_parent_id='MCENV_PT_world'
    bl_label='Uninstall mc-env'
    bl_idname='MCENV_PT_world_uninstall'
    bl_order=9
    bl_options={'DEFAULT_CLOSED'}

    def draw_header(self,context): self.layout.label(text='',icon='TRASH')

    def draw(self,context):
        layout=self.layout
        col=layout.column(align=True)
        col.label(text='Removes the environment from every scene,')
        col.label(text='restores previous worlds, then deletes')
        col.label(text='the add-on files from Blender.')
        layout.operator('mcenv.uninstall',icon='TRASH')


PANELS=(MCENV_PT_world,MCENV_PT_world_sun,MCENV_PT_world_sky,MCENV_PT_world_cloud,MCENV_PT_world_ground,
        MCENV_PT_world_biome,MCENV_PT_world_colors,MCENV_PT_world_fog,MCENV_PT_world_wind,MCENV_PT_world_tools,
        MCENV_PT_world_uninstall)


def register():
    for cls in PANELS: bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(PANELS): bpy.utils.unregister_class(cls)
