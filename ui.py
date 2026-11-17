# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from . import engine
from .operators import animatable_key, animation_icon


# Environment sections in the World Properties editor.
def section_fields(p, section):
    if section=='sun': return ['sun_angle','sun_strength','ambient_strength','night_strength']
    if section=='sky':
        if p.sky_mode=='CUSTOM':
            return ['sky_mode','background_image','background_type','background_stretch' if p.background_type=='IMAGE' else 'background_rotation']
        return ['sky_mode','sun_image','sun_tilt','sun_scale','moon_image','moon_phase','moon_tilt','moon_scale','stars_count','stars_size','stars_size_random','stars_strength']
    if section=='cloud': return ['cloud_mode','cloud_image','cloud_speed','cloud_offset','cloud_height','cloud_size','cloud_blocks','cloud_thickness','cloud_coverage','cloud_seed']
    if section=='fog':
        return ['fog_sky','fog_custom']+(['fog_color'] if p.fog_custom else [])+['fog_custom_object']+(['fog_object_color'] if p.fog_custom_object else [])+['fog_distance','fog_size','fog_height']
    if section=='wind': return ['wind_speed','wind_strength','wind_direction','wind_directional_speed','wind_directional_strength']
    return []


BIOME_FIELDS=['grass_color','foliage_color','water_color','oak_color','spruce_color','birch_color','jungle_color','acacia_color','dark_oak_color','mangrove_color']
SECTIONS=[('sun','Sunlight',None),('sky','Sky background',None),('cloud','Clouds','clouds'),('ground','Biomes','ground')]


def field(layout,p,key):
    prop=p.bl_rna.properties[key]
    if prop.type=='POINTER':
        col=layout.column(align=True); col.label(text=prop.name)
        row=col.row(align=True); row.template_ID(p,key)
        op=row.operator('mcenv.load_image',text='',icon='FILE_FOLDER'); op.property_name=key
    else: layout.prop(p,key)


def toggle_row(layout,p,key):
    # The on/off switch draws as a plain left-aligned checkbox ("[] Label")
    # with a bare animate dot after it: no split column, no embossed square.
    row=layout.row(align=True)
    row.use_property_split=False
    row.use_property_decorate=False
    row.prop(p,key)
    op=row.operator('mcenv.animate_property',text='',icon=animation_icon(p.id_data,key),emboss=False)
    op.property_name=key


def section(layout,p,key,title,toggle=None):
    row=layout.row(align=True)
    row.use_property_split=False
    row.prop(p,'fold_'+key,text=title,icon='TRIA_DOWN' if getattr(p,'fold_'+key) else 'TRIA_RIGHT',emboss=False)
    if toggle:
        # A bare keyframe dot like the other parameters: no embossed square
        # button around it, nothing that invites Add to Quick Favorites.
        op=row.operator('mcenv.animate_property',text='',icon=animation_icon(p.id_data,toggle),emboss=False)
        op.property_name=toggle
    if getattr(p,'fold_'+key):
        col=layout.column(align=True)
        if toggle: toggle_row(col,p,toggle)   # checkbox on the left of its label
        body=layout.column(align=True)
        if toggle: body.enabled=getattr(p,toggle)
        if key=='ground':
            # Top texture takes the biome tint across its whole image; the
            # Side texture is tinted only on the bundled grass overlay strip.
            for name in ('ground_image','ground_side','ground_direction'): field(body,p,name)
            biome_col=layout.column(align=True)   # stays usable even with ground off
            field(biome_col,p,'biome')
            if p.biome=='CUSTOM': color_grid(biome_col,p,BIOME_FIELDS)
        else:
            for name in section_fields(p,key): field(body,p,name)


def color_grid(layout,p,keys):
    grid=layout.grid_flow(columns=2,row_major=True,even_columns=True,align=True)
    for key in keys:
        col=grid.column(align=True)
        col.label(text=p.bl_rna.properties[key].name)
        col.prop(p,key,text='')


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
        layout.separator()
        row=layout.row(align=True)
        row.use_property_split=False
        row.prop(p,'fold_scene',text='Scene Colors',icon='TRIA_DOWN' if p.fold_scene else 'TRIA_RIGHT',emboss=False)
        if p.fold_scene:
            toggle_row(layout,p,'twilight')   # Twilight lives inside Scene Colors now
            layout.label(text='Day')
            color_grid(layout,p,['day_sky','day_clouds','day_sunlight','day_ambient'])
            layout.label(text='Night')
            color_grid(layout,p,['night_sky','night_clouds','night_stars','night_ambient'])
        section(layout,p,'fog','Fog','fog'); section(layout,p,'wind','Wind','wind')
        layout.prop(p,'texture_fps',text='Texture animation speed')
        layout.separator()
        # Same header construction as the other fold rows so Blender tools
        # matches them exactly.
        row=layout.row(align=True)
        row.use_property_split=False
        row.prop(p,'fold_tools',text='Blender tools',icon='TRIA_DOWN' if p.fold_tools else 'TRIA_RIGHT',emboss=False)
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


def button_context_menu(self, context):
    p = context.scene.mc_env if context.scene and hasattr(context.scene,'mc_env') else None
    if not p:
        return
    key = None
    pointer = getattr(context,'button_pointer',None)
    prop = getattr(context,'button_prop',None)
    if pointer == p and prop:
        key = prop.identifier
    operator = getattr(context,'button_operator',None)
    if operator:
        identifier = operator.bl_rna.identifier
        if identifier == 'MCENV_OT_time_dial': key = 'time'
        elif identifier == 'MCENV_OT_rotation_dial': key = 'rotation'
    if key and animatable_key(p,key):
        self.layout.separator()
        op=self.layout.operator('mcenv.animate_property',text='Animate Property',icon='KEY_HLT')
        op.property_name=key


def register():
    bpy.utils.register_class(MCENV_PT_environment)
    bpy.types.UI_MT_button_context_menu.append(button_context_menu)


def unregister():
    bpy.types.UI_MT_button_context_menu.remove(button_context_menu)
    bpy.utils.unregister_class(MCENV_PT_environment)
