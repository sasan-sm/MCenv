# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from . import engine


# Environment sections in the World Properties editor.
def section_fields(p, section):
    if section=='sun': return ['sun_angle','sun_strength','ambient_strength','night_strength']
    if section=='sky':
        if p.sky_mode=='CUSTOM':
            return ['sky_mode','background_image','background_type','background_stretch' if p.background_type=='IMAGE' else 'background_rotation','twilight']
        return ['sky_mode','sun_texture_set','sun_image','sun_tilt','sun_scale','moon_texture_set','moon_image','moon_phase','moon_tilt','moon_scale','stars_count','stars_size','stars_size_random','stars_strength','twilight']
    if section=='cloud': return ['cloud_mode','cloud_image','cloud_speed','cloud_offset','cloud_height','cloud_size','cloud_blocks','cloud_thickness','cloud_coverage','cloud_seed']
    if section=='ground': return ['ground_follow_biome','ground_image']
    if section=='fog':
        return ['fog_sky','fog_custom']+(['fog_color'] if p.fog_custom else [])+['fog_custom_object']+(['fog_object_color'] if p.fog_custom_object else [])+['fog_distance','fog_size','fog_height']
    if section=='wind': return ['wind_speed','wind_strength','wind_direction','wind_directional_speed','wind_directional_strength']
    return []


BIOME_FIELDS=['grass_color','foliage_color','dry_foliage_color','water_color','oak_color','spruce_color','birch_color','jungle_color','acacia_color','dark_oak_color','mangrove_color']
SECTIONS=[('sun','Sunlight',None),('sky','Sky Background',None),('colors','Scene Colors',None),('cloud','Clouds','clouds'),('ground','Ground','ground'),('fog','Fog','fog')]


def field(layout,p,key):
    prop=p.bl_rna.properties[key]
    if prop.type=='POINTER':
        col=layout.column(align=True); col.label(text=prop.name)
        row=col.row(align=True); row.template_ID(p,key)
        op=row.operator('mcenv.load_image',text='',icon='FILE_FOLDER'); op.property_name=key
        if not getattr(p,key):
            if key=='sun_image': col.label(text='Default: '+p.sun_texture_set.replace('_',' ')+' sun.png',icon='TEXTURE')
            elif key=='moon_image': col.label(text='Default: '+p.moon_texture_set+' moon phase',icon='TEXTURE')
            elif key=='ground_image': col.label(text='Default: main/grass_block_top.png',icon='TEXTURE')
    elif key in {'ground_follow_biome', 'twilight', 'biome_atmosphere'}:
        row=layout.row(align=True)
        row.use_property_split=False
        row.alignment='LEFT'
        row.prop(p,key)
    else: layout.prop(p,key)


def section(layout,p,key,title,toggle=None):
    row=layout.row(align=True)
    row.use_property_split=False
    row.use_property_decorate=False
    row.prop(p,'fold_'+key,text=title,icon='TRIA_DOWN' if getattr(p,'fold_'+key) else 'TRIA_RIGHT',emboss=False)
    if toggle:
        row.prop(p,toggle,text='')
        row.prop_decorator(p,toggle)
    if getattr(p,'fold_'+key):
        col=layout.column(align=True)
        if toggle: col.enabled=getattr(p,toggle)
        for name in section_fields(p,key): field(col,p,name)
        if key=='colors':
            col.label(text='Day scene colors:')
            color_grid(col,p,['day_sky','day_clouds','day_sunlight','day_ambient'])
            col.separator(); col.label(text='Night scene colors:')
            color_grid(col,p,['night_sky','night_clouds','night_stars','night_ambient'])


def color_grid(layout,p,keys):
    grid=layout.grid_flow(columns=2,row_major=True,even_columns=True,align=True)
    for key in keys:
        col=grid.column(align=True)
        col.label(text=p.bl_rna.properties[key].name)
        col.prop(p,key,text='')


def animate_section(layout,scene):
    p=scene.mc_env
    section(layout,p,'animate','Animate','animate')
    if not p.fold_animate: return
    col=layout.column(align=True); col.enabled=p.animate
    # Native English labels and left-aligned checkbox before its text (LTR).
    for key in ('preview_day_cycle','texture_animate'):
        row=col.row(align=True); row.use_property_split=False; row.alignment='LEFT'
        row.prop(p,key)
        if key=='preview_day_cycle' and p.preview_day_cycle: col.prop(p,'cycle_frames')
        if key=='texture_animate':
            sub=col.column(align=True); sub.enabled=p.texture_animate
            sub.prop(p,'texture_fps')
            sub.operator('mcenv.bind_atlas',text='Add Selected Texture Strips',icon='TEXTURE')
    col.separator(); col.label(text='Objects',icon='OUTLINER_OB_MESH')
    col.prop_search(p,'animation_candidate',scene,'objects',text='Object')
    row=col.row(align=True)
    row.operator('mcenv.animation_add',text='Add',icon='ADD')
    row.operator('mcenv.animation_add',text='Add Selected').use_selected=True
    for index,item in enumerate(p.animation_objects):
        box=col.box(); box.use_property_split=False
        row=box.row(align=True); row.prop(item,'enabled',text='')
        row.label(text=item.object.name if item.object else 'Missing object',icon='MESH_DATA' if item.object else 'ERROR')
        row.operator('mcenv.animation_remove',text='',icon='X').index=index
        settings=box.column(align=True); settings.enabled=item.enabled and item.object is not None
        settings.prop(item,'mode',text='Motion'); settings.prop(item,'influence')
    col.label(text='Motion follows the Wind settings below.',icon='INFO')
    if not p.wind: col.label(text='Enable Wind to move listed objects.',icon='INFO')


class MCENV_PT_environment(bpy.types.Panel):
    bl_label='MCenv'
    bl_idname='MCENV_PT_environment'
    bl_space_type='PROPERTIES'
    bl_region_type='WINDOW'
    bl_context='world'
    bl_order=1001

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def draw_header(self,context): self.layout.label(text='',icon='WORLD')

    def draw(self,context):
        layout=self.layout; p=context.scene.mc_env
        layout.use_property_split=True; layout.use_property_decorate=True
        if not p.enabled:
            layout.label(text='Minecraft-inspired environment')
            layout.operator('mcenv.create',icon='WORLD')
            return
        err=engine._ERRORS.get(context.scene.as_pointer())
        if err:
            box=layout.box(); box.alert=True; box.label(text=err,icon='ERROR')
        # Icon opens the circular dial (right-click it for Add to Quick Favorites;
        # a static label keeps stored favorites from showing stale values) and the
        # native field beside it is drag-editable, wrapping around the day.
        for key, operator, icon in [('time','mcenv.time_dial','TIME'),
                                     ('rotation','mcenv.rotation_dial','DRIVER_ROTATIONAL_DIFFERENCE')]:
            row=layout.row(align=True)
            row.operator_context='INVOKE_DEFAULT'
            row.operator(operator,text=key.title(),icon=icon)
            row.prop(p,key,text='')
        for key,title,toggle in SECTIONS: section(layout,p,key,title,toggle)
        box=layout.box(); box.label(text='Biomes / Dimensions',icon='WORLD')
        box.prop(p,'dimension')
        box.prop(p,'biome',text='')
        if p.dimension=='END': box.prop(p,'end_texture_set')
        if p.biome=='CUSTOM': color_grid(box,p,BIOME_FIELDS)
        else: box.operator('mcenv.custom_biome',icon='COLOR')
        box.prop(p,'biome_scope'); box.prop(p,'biome_texture_mode')
        box.prop(p,'block_texture_set')
        field(box,p,'grass_side_overlay')
        if not p.grass_side_overlay:
            box.label(text='Default: bundled grass_block_side_overlay.png',icon='TEXTURE')
        elif not p.grass_side_overlay.size[0] or p.grass_side_overlay.channels != 4:
            warning=box.row(); warning.alert=True
            warning.label(text='Choose an RGBA image with transparency.',icon='ERROR')
        box.label(text='RGBA color overlay; dirt and normal maps stay unchanged.')
        box.operator('mcenv.detect_biome',icon='MATERIAL')
        box.operator('mcenv.restore_biome',icon='LOOP_BACK')
        box.label(text='Run after MCprep > Prep Materials.',icon='INFO')
        box.label(text='Bound materials follow biome changes automatically.')
        box.label(text='Reapply after importing or prepping again.')
        field(box,p,'biome_atmosphere')
        animate_section(layout,context.scene)
        section(layout,p,'wind','Wind','wind')
        section(layout,p,'tools','Blender tools')
        if p.fold_tools:
            layout.operator('mcenv.bind_wind',icon='MOD_WAVE'); layout.operator('mcenv.remove_wind')
            row=layout.row(align=True); row.operator('mcenv.import_preset',text='Import preset'); row.operator('mcenv.export_preset',text='Export preset')
            layout.label(text='Image files are saved with .blend, not presets.',icon='INFO')
            layout.operator('mcenv.reset',icon='LOOP_BACK')
            layout.operator('mcenv.remove',icon='TRASH')


def register():
    bpy.utils.register_class(MCENV_PT_environment)


def unregister():
    bpy.utils.unregister_class(MCENV_PT_environment)
