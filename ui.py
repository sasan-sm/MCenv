# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from . import engine


# Shared section definitions keep custom and Blender-native editors in sync.
def section_fields(p, section):
    if section=='sun': return ['sun_angle','sun_strength','ambient_strength','night_strength']
    if section=='sky':
        if p.sky_mode=='CUSTOM':
            return ['sky_mode','background_image','background_type','background_stretch' if p.background_type=='IMAGE' else 'background_rotation']
        return ['sky_mode','sun_image','sun_tilt','sun_scale','moon_image','moon_phase','moon_tilt','moon_scale','stars_size','stars_strength']
    if section=='cloud': return ['cloud_mode','cloud_image','cloud_speed','cloud_offset','cloud_height','cloud_size','cloud_thickness','cloud_coverage','cloud_seed']
    if section=='ground': return ['ground_type','ground_image','ground_normal','ground_material','ground_size','ground_height','ground_tile']
    if section=='fog':
        return ['fog_sky','fog_custom']+(['fog_color'] if p.fog_custom else [])+['fog_custom_object']+(['fog_object_color'] if p.fog_custom_object else [])+['fog_distance','fog_size','fog_height']
    if section=='wind': return ['wind_speed','wind_strength','wind_direction','wind_directional_speed','wind_directional_strength']
    return []


BIOME_FIELDS=['grass_color','foliage_color','water_color','oak_color','spruce_color','birch_color','jungle_color','acacia_color','dark_oak_color','mangrove_color']
SECTIONS=[('sun','Sunlight',None),('sky','Sky background',None),('cloud','Clouds','clouds'),('ground','Ground','ground')]


def field(layout,p,key):
    prop=p.bl_rna.properties[key]
    if prop.type=='POINTER':
        col=layout.column(align=True); col.label(text=prop.name)
        row=col.row(align=True); row.template_ID(p,key)
        op=row.operator('mcenv.load_image',text='',icon='FILE_FOLDER'); op.property_name=key
    else: layout.prop(p,key)


def section(layout,p,key,title,toggle=None):
    row=layout.row(align=True)
    row.prop(p,'fold_'+key,text=title,icon='TRIA_DOWN' if getattr(p,'fold_'+key) else 'TRIA_RIGHT',emboss=False)
    if toggle: row.prop(p,toggle,text='')
    if getattr(p,'fold_'+key):
        col=layout.column(align=True)
        if toggle: col.enabled=getattr(p,toggle)
        for name in section_fields(p,key): field(col,p,name)


def color_grid(layout,p,keys):
    grid=layout.grid_flow(columns=2,even_columns=True,align=True)
    for key in keys:
        col=grid.column(align=True)
        col.label(text=p.bl_rna.properties[key].name)
        col.prop(p,key,text='')


class MCENV_PT_environment(bpy.types.Panel):
    bl_label='ENVIRONMENT'
    bl_idname='MCENV_PT_environment'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='mc-env'

    def draw_header(self,context): self.layout.label(text='',icon='WORLD')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=False; layout.use_property_decorate=True
        if not p.enabled:
            layout.label(text='Minecraft-inspired environment')
            layout.operator('mcenv.create',icon='WORLD')
            return
        row=layout.row(align=True)
        row.operator('mcenv.overlay',text='Reference UI',icon='WINDOW')
        row.operator('mcenv.preview',text='',icon='SHADING_RENDERED')
        err=engine._ERRORS.get(context.scene.as_pointer())
        if err:
            box=layout.box(); box.alert=True; box.label(text=err,icon='ERROR')
        row=layout.row(align=True); row.prop(p,'time'); row.prop(p,'rotation')
        for key,title,toggle in SECTIONS: section(layout,p,key,title,toggle)
        layout.label(text='Biome'); layout.prop(p,'biome',text='')
        if p.biome=='CUSTOM': color_grid(layout,p,BIOME_FIELDS)
        layout.separator(); layout.label(text='Day scene colors:')
        color_grid(layout,p,['day_sky','day_clouds','day_sunlight','day_ambient'])
        layout.separator(); layout.label(text='Night scene colors:')
        color_grid(layout,p,['night_sky','night_clouds','night_stars','night_ambient'])
        layout.prop(p,'twilight')
        section(layout,p,'fog','Fog','fog'); section(layout,p,'wind','Wind','wind')
        layout.prop(p,'texture_fps',text='Texture animation speed')
        layout.separator()
        row=layout.row(); row.prop(p,'fold_tools',text='Blender tools',icon='TRIA_DOWN' if p.fold_tools else 'TRIA_RIGHT',emboss=False)
        if p.fold_tools:
            layout.prop(p,'preview_day_cycle')
            if p.preview_day_cycle: layout.prop(p,'cycle_frames')
            layout.operator('mcenv.bind_wind',icon='MOD_WAVE'); layout.operator('mcenv.remove_wind')
            layout.prop(p,'tint_kind'); layout.operator('mcenv.bind_tint',icon='COLOR'); layout.operator('mcenv.remove_tint')
            layout.operator('mcenv.bind_atlas',icon='TEXTURE')
            row=layout.row(align=True); row.operator('mcenv.import_preset',text='Import preset'); row.operator('mcenv.export_preset',text='Export preset')
            layout.label(text='Image files are saved with .blend, not presets.',icon='INFO')
            layout.operator('mcenv.reset',icon='LOOP_BACK')
            layout.operator('mcenv.remove',icon='TRASH')


def register(): bpy.utils.register_class(MCENV_PT_environment)


def unregister(): bpy.utils.unregister_class(MCENV_PT_environment)
