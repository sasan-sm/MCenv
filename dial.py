# SPDX-License-Identifier: GPL-3.0-or-later
"""Circular Time/Rotation dial, available from the Quick Favorites (Q) menu.

Blender's Python UI API cannot draw custom widgets inside a Properties panel,
so the dial lives on a POST_PIXEL overlay of whichever editor it was invoked
from (normally the 3D Viewport via the Q menu). The backdrop is translucent so
the scene stays visible behind it. The visual language (ring, gear knob,
crescent marker, clock caption) keeps the original mc-env dial look.
"""
import math
import bpy
import blf
import gpu
from bpy.props import StringProperty, BoolProperty
from gpu_extras.batch import batch_for_shader
from .ui import field
from .properties import MCENV_Settings

TEXT=(.78,.78,.78,1)
BRIGHT=(.92,.92,.92,1)
MUTED=(.50,.50,.50,1)
BG=(.08,.08,.08,.30)      # translucent, so the scene is visible behind the dial
SOLID=(.08,.08,.08,.85)   # small backdrops for knob and marker, kept readable
RING=(.45,.45,.45,1)
KNOB=(.65,.65,.65,1)

VALID=('time','rotation')
CENTER_PICK_RADIUS=20.0

# Editors the dial can be drawn over, resolved lazily at invoke time.
_SPACE_CLASSES=(('VIEW_3D','SpaceView3D'),('PROPERTIES','SpaceProperties'),
                ('NODE_EDITOR','SpaceNodeEditor'),('IMAGE_EDITOR','SpaceImageEditor'),
                ('SEQUENCE_EDITOR','SpaceSequenceEditor'),('GRAPH_EDITOR','SpaceGraphEditor'),
                ('CLIP_EDITOR','SpaceClipEditor'),('OUTLINER','SpaceOutliner'),
                ('TOPBAR','SpaceTopbar'),('INFO','SpaceInfo'),('TEXT_EDITOR','SpaceTextEditor'),
                ('SPREADSHEET','SpaceSpreadsheet'),('FILE_BROWSER','SpaceFileBrowser'))


def shape(shader,mode,vertices,color):
    shader.bind(); shader.uniform_float('color',color)
    batch_for_shader(shader,mode,{'pos':vertices}).draw(shader)


def rect(shader,x,y,w,h,c):
    shape(shader,'TRIS',[(x,y),(x+w,y),(x+w,y+h),(x,y),(x+w,y+h),(x,y+h)],c)


def text(x,y,value,size=12,color=TEXT,center=False):
    blf.size(0,size); blf.color(0,*color)
    w=blf.dimensions(0,str(value))[0]
    blf.position(0,x-(w/2 if center else 0),y,0); blf.draw(0,str(value))


def caption(p,key):
    if key=='time':
        minutes=round(p.time*60)%1440
        return f'{minutes//60}:{minutes%60:02d}'
    return f'{p.rotation:.0f}°'


def _space_class(area):
    for kind,name in _SPACE_CLASSES:
        if area.type==kind: return getattr(bpy.types,name,None)
    return None


class MCENV_OT_edit(bpy.types.Operator):
    bl_idname='mcenv.edit_field'
    bl_label='Environment Setting'
    bl_options={'INTERNAL','UNDO'}
    property_name: StringProperty()

    def draw(self,context):
        if self.property_name in context.scene.mc_env.bl_rna.properties:
            field(self.layout,context.scene.mc_env,self.property_name)
            self.layout.label(text='Right-click the field for keyframes.',icon='KEY_HLT')

    def execute(self,context): return {'FINISHED'}


class MCENV_OT_dial(bpy.types.Operator):
    bl_idname='mcenv.dial'
    bl_label='mc-env Circular Dial'
    bl_description='Move the mouse around the translucent dial to adjust, click to confirm, click the dial center to type a value, scroll for fine steps, Esc cancels'
    bl_options={'INTERNAL'}

    property_name: StringProperty()

    @classmethod
    def poll(cls,context):
        p=getattr(context.scene,'mc_env',None) if context.scene else None
        return p is not None and p.enabled and context.area is not None and context.window is not None

    def invoke(self,context,event):
        if self.property_name not in VALID: return {'CANCELLED'}
        self.scene=context.scene; self.window=context.window; self.area=context.area
        # Always draw relative to the editor's own WINDOW region, even when the
        # operator is invoked from a popup menu (Quick Favorites) with a temp region.
        self.region=next((r for r in self.area.regions if r.type=='WINDOW'),None)
        if self.region is None and context.region and context.region.type=='WINDOW':
            self.region=context.region
        if self.region is None: return {'CANCELLED'}
        space_cls=_space_class(self.area)
        if space_cls is None:
            self.report({'INFO'},'The circular dial is not available in this editor; edit the value directly.')
            bpy.ops.mcenv.edit_field('INVOKE_DEFAULT',property_name=self.property_name)
            return {'CANCELLED'}
        self.space_cls=space_cls
        p=self.scene.mc_env
        self.initial=getattr(p,self.property_name)
        self.moved=False; self.seen_press=False
        self.radius=54.0
        self.center=(min(max(event.mouse_x-self.region.x,self.radius+10),self.region.width-self.radius-10),
                     min(max(event.mouse_y-self.region.y,self.radius+34),self.region.height-self.radius-46))
        self.shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        try:
            self.handle=space_cls.draw_handler_add(self.draw_dial,(),'WINDOW','POST_PIXEL')
        except (AttributeError,RuntimeError):
            self.handle=None
        if self.handle is None:
            self.report({'INFO'},'Circular dial unavailable in this Blender build; edit the value directly.')
            bpy.ops.mcenv.edit_field('INVOKE_DEFAULT',property_name=self.property_name)
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def finish(self,context=None):
        handle=getattr(self,'handle',None)
        self.handle=None
        if handle:
            try: getattr(self,'space_cls',bpy.types.SpaceView3D).draw_handler_remove(handle,'WINDOW')
            except Exception: pass
        try: self.area.tag_redraw()
        except Exception: pass

    def apply(self,value):
        p=self.scene.mc_env
        if self.property_name=='time': p.time=round((value%24)*60)/60
        else: p.rotation=round(((value+180)%360)-180)

    def value_at(self,angle_deg):
        # Matches the classic mc-env dial mapping: time 0h at the bottom, rotation 0° at the top.
        if self.property_name=='time': return ((angle_deg+90)%360)/15
        return angle_deg-90

    def draw_dial(self):
        if self.handle is None: return
        try:
            if bpy.context.area!=self.area: return
        except ReferenceError: return
        try:
            p=self.scene.mc_env
        except ReferenceError:
            return
        s=self.shader; cx,cy=self.center; R=self.radius
        gpu.state.blend_set('ALPHA')
        try:
            circle=[(cx+math.cos(i*math.tau/72)*R,cy+math.sin(i*math.tau/72)*R) for i in range(73)]
            shape(s,'TRI_FAN',[(cx,cy)]+circle,BG)
            shape(s,'LINE_STRIP',circle,RING)
            value=p.time if self.property_name=='time' else p.rotation
            a=(value/24*math.tau-math.pi/2) if self.property_name=='time' else math.radians(value)+math.pi/2
            hx=cx+math.cos(a)*R; hy=cy+math.sin(a)*R
            rect(s,hx-10,hy-10,20,20,SOLID)
            for j in range(8):
                aa=j*math.tau/8
                shape(s,'LINES',[(hx+math.cos(aa)*6,hy+math.sin(aa)*6),(hx+math.cos(aa)*9,hy+math.sin(aa)*9)],KNOB)
            ring=[(hx+math.cos(i*math.tau/20)*3,hy+math.sin(i*math.tau/20)*3) for i in range(21)]
            shape(s,'LINE_STRIP',ring,KNOB)
            text(cx,cy+20,'Time' if self.property_name=='time' else 'Rotation',size=10,color=MUTED,center=True)
            text(cx,cy-24,caption(p,self.property_name),size=17,color=BRIGHT,center=True)
            mx=cx-math.cos(a)*R; my=cy-math.sin(a)*R
            rect(s,mx-10,my-10,20,20,SOLID)
            crescent=[(mx+math.cos(i*math.pi/20-math.pi/2)*7,my+math.sin(i*math.pi/20-math.pi/2)*7) for i in range(21)]
            shape(s,'LINE_STRIP',crescent,MUTED)
            inner=[(mx+math.cos(i*math.pi/20-math.pi/2)*4,my+math.sin(i*math.pi/20-math.pi/2)*5) for i in range(21)]
            shape(s,'LINE_STRIP',inner,MUTED)
            text(cx,cy-R-18,'Click: confirm  •  Center: type value  •  Scroll: fine  •  Esc: cancel',size=10,color=MUTED,center=True)
        finally: gpu.state.blend_set('NONE')

    def modal(self,context,event):
        if getattr(self,'handle',None) is None: return {'CANCELLED'}
        try:
            valid=self.area in list(context.screen.areas) and self.window==context.window
        except ReferenceError:
            self.finish(context); return {'CANCELLED'}
        if not valid:
            self.finish(context); return {'CANCELLED'}
        r=self.region
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE'}:
            dx=event.mouse_x-r.x-self.center[0]; dy=event.mouse_y-r.y-self.center[1]
            if math.hypot(dx,dy)>4: self.moved=True
            if self.moved:
                try: self.apply(self.value_at(math.degrees(math.atan2(dy,dx))))
                except ReferenceError: self.finish(context); return {'CANCELLED'}
            self.area.tag_redraw(); return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            try:
                p=self.scene.mc_env
                step=.25 if self.property_name=='time' else 1
                self.apply(getattr(p,self.property_name)+(step if event.type=='WHEELUPMOUSE' else -step))
            except ReferenceError:
                self.finish(context); return {'CANCELLED'}
            self.moved=True; self.area.tag_redraw(); return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            self.seen_press=True; return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':
            if not self.seen_press:
                # Tail release of the click that opened the dial; keep it open.
                return {'RUNNING_MODAL'}
            self.finish(context)
            mx=event.mouse_x-r.x; my=event.mouse_y-r.y
            if not self.moved and math.hypot(mx-self.center[0],my-self.center[1])<CENTER_PICK_RADIUS:
                bpy.ops.mcenv.edit_field('INVOKE_DEFAULT',property_name=self.property_name)
            elif self.moved:
                bpy.ops.ed.undo_push(message='mc-env '+self.property_name)
            return {'FINISHED'}
        if event.type in {'ESC','RIGHTMOUSE'}:
            if self.moved:
                self.apply(self.initial)
                bpy.ops.ed.undo_push(message='mc-env dial cancel')
            self.finish(context); return {'FINISHED'}
        return {'PASS_THROUGH'}


class MCENV_OT_quick_favorite(bpy.types.Operator):
    bl_idname='mcenv.quick_favorite'
    bl_label='Quick Favorites: mc-env Field'
    bl_description='Show or hide this mc-env field in the Quick Favorites (Q) menu; the choice is stored in the add-on preferences'
    bl_options={'REGISTER','INTERNAL'}

    property_name: StringProperty()

    @classmethod
    def poll(cls,context):
        return context.scene is not None and hasattr(context.scene,'mc_env')

    def execute(self,context):
        if self.property_name not in VALID: return {'CANCELLED'}
        prefs=_prefs(context)
        if prefs is None:
            self.report({'ERROR'},'mc-env preferences are unavailable'); return {'CANCELLED'}
        key='quick_fav_'+self.property_name
        added=not getattr(prefs,key)
        setattr(prefs,key,added)
        try: context.preferences.is_dirty=True
        except Exception: pass
        name=context.scene.mc_env.bl_rna.properties[self.property_name].name
        self.report({'INFO'},(name+' added to Quick Favorites') if added else (name+' removed from Quick Favorites'))
        return {'FINISHED'}


class MCENV_Preferences(bpy.types.AddonPreferences):
    bl_idname=__package__
    quick_fav_time: BoolProperty(name='Time in Quick Favorites', description='Show a Time entry in the Quick Favorites (Q) menu', default=False)
    quick_fav_rotation: BoolProperty(name='Rotation in Quick Favorites', description='Show a Rotation entry in the Quick Favorites (Q) menu', default=False)

    def draw(self,context):
        layout=self.layout
        layout.label(text='Right-click the mc-env Time or Rotation fields to add or remove them here.',icon='BOOKMARKS')


def _prefs(context):
    try: return context.preferences.addons[__package__].preferences
    except Exception: return None


def _button_context_draw(menu,context):
    """Shown when right-clicking an mc-env Time/Rotation field in any editor.

    Blender's own 'Add to Quick Favorites' entry only appears for boolean
    properties, so these float fields provide their own equivalent here.
    """
    ptr=getattr(context,'button_pointer',None)
    prop=getattr(context,'button_prop',None)
    if ptr is None or prop is None or not isinstance(ptr,MCENV_Settings): return
    ident=getattr(prop,'identifier','')
    if ident not in VALID: return
    prefs=_prefs(context)
    if prefs is None: return
    added=getattr(prefs,'quick_fav_'+ident,False)
    op=menu.layout.operator('mcenv.quick_favorite',icon='MENU_PANEL',
                            text='Remove from Quick Favorites' if added else 'Add to Quick Favorites')
    op.property_name=ident


def _quick_favorites_draw(menu,context):
    p=getattr(context.scene,'mc_env',None) if context.scene else None
    prefs=_prefs(context)
    show_dials=p is not None and p.enabled
    show_fields=prefs is not None and (prefs.quick_fav_time or prefs.quick_fav_rotation)
    if not show_dials and not show_fields: return
    col=menu.layout.column(align=True)
    col.label(text='mc-env',icon='WORLD')
    if show_fields:
        if prefs.quick_fav_time:
            op=col.operator('mcenv.edit_field',text='Time',icon='TIME'); op.property_name='time'
        if prefs.quick_fav_rotation:
            op=col.operator('mcenv.edit_field',text='Rotation',icon='DRIVER_ROTATIONAL_DIFFERENCE'); op.property_name='rotation'
    if show_dials:
        op=col.operator('mcenv.dial',text='Time (circular dial)',icon='TIME'); op.property_name='time'
        op=col.operator('mcenv.dial',text='Rotation (circular dial)',icon='DRIVER_ROTATIONAL_DIFFERENCE'); op.property_name='rotation'


CLASSES=(MCENV_OT_edit,MCENV_OT_dial,MCENV_OT_quick_favorite,MCENV_Preferences)


def _context_menu():
    # UI_MT_button_context_menu is the right-click menu for UI buttons (3.x+).
    return getattr(bpy.types,'UI_MT_button_context_menu',None) or getattr(bpy.types,'WM_MT_button_context',None)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)
    try: bpy.types.SCREEN_MT_user_menu.append(_quick_favorites_draw)
    except Exception: pass
    menu=_context_menu()
    if menu:
        try: menu.append(_button_context_draw)
        except Exception: pass


def unregister():
    menu=_context_menu()
    if menu:
        try: menu.remove(_button_context_draw)
        except Exception: pass
    try: bpy.types.SCREEN_MT_user_menu.remove(_quick_favorites_draw)
    except Exception: pass
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
