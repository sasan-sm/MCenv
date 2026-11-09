# SPDX-License-Identifier: GPL-3.0-or-later
"""Circular Time/Rotation dial for the World Properties panel.

Blender's Python UI API cannot draw custom widgets inside a Properties panel,
so the dials live on a POST_PIXEL overlay of the Properties editor, spawned
right at the mouse when the Time or Rotation button is clicked. The visual
language (ring, gear knob, crescent marker, clock caption) matches the
floating reference UI in overlay.py.
"""
import math
import bpy
import blf
import gpu
from bpy.props import StringProperty
from gpu_extras.batch import batch_for_shader

TEXT=(.78,.78,.78,1)
BRIGHT=(.92,.92,.92,1)
MUTED=(.44,.44,.44,1)
BG=(.08,.08,.08,.93)
RING=(.42,.42,.42,1)
KNOB=(.62,.62,.62,1)

VALID=('time','rotation')
CENTER_PICK_RADIUS=20.0


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


class MCENV_OT_dial(bpy.types.Operator):
    bl_idname='mcenv.dial'
    bl_label='Adjust With Circular Dial'
    bl_description='Move the mouse around the dial to adjust, click to confirm, click the dial center to type a value, scroll for fine steps, Esc cancels'
    bl_options={'INTERNAL'}

    property_name: StringProperty()

    @classmethod
    def poll(cls,context):
        p=getattr(context.scene,'mc_env',None) if context.scene else None
        return p is not None and p.enabled and context.area is not None and context.window is not None

    def invoke(self,context,event):
        if self.property_name not in VALID: return {'CANCELLED'}
        self.scene=context.scene; self.window=context.window; self.area=context.area
        self.region=context.region if context.region and context.region.type=='WINDOW' else next((r for r in self.area.regions if r.type=='WINDOW'),None)
        if self.region is None: return {'CANCELLED'}
        p=self.scene.mc_env
        self.initial=getattr(p,self.property_name)
        self.moved=False; self.seen_press=False
        self.radius=54.0
        self.center=(min(max(event.mouse_x-self.region.x,self.radius+10),self.region.width-self.radius-10),
                     min(max(event.mouse_y-self.region.y,self.radius+34),self.region.height-self.radius-46))
        self.shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        try:
            self.handle=bpy.types.SpaceProperties.draw_handler_add(self.draw_dial,(),'WINDOW','POST_PIXEL')
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
            try: bpy.types.SpaceProperties.draw_handler_remove(handle,'WINDOW')
            except Exception: pass
        try: self.area.tag_redraw()
        except Exception: pass

    def apply(self,value):
        p=self.scene.mc_env
        if self.property_name=='time': p.time=round((value%24)*60)/60
        else: p.rotation=round(((value+180)%360)-180)

    def value_at(self,angle_deg):
        # Matches the reference UI mapping: time 0h at the bottom, rotation 0° at the top.
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
            rect(s,hx-10,hy-10,20,20,(*BG[:3],1))
            for j in range(8):
                aa=j*math.tau/8
                shape(s,'LINES',[(hx+math.cos(aa)*6,hy+math.sin(aa)*6),(hx+math.cos(aa)*9,hy+math.sin(aa)*9)],KNOB)
            ring=[(hx+math.cos(i*math.tau/20)*3,hy+math.sin(i*math.tau/20)*3) for i in range(21)]
            shape(s,'LINE_STRIP',ring,KNOB)
            text(cx,cy+20,'Time' if self.property_name=='time' else 'Rotation',size=10,color=MUTED,center=True)
            text(cx,cy-24,caption(p,self.property_name),size=17,color=BRIGHT,center=True)
            mx=cx-math.cos(a)*R; my=cy-math.sin(a)*R
            rect(s,mx-10,my-10,20,20,(*BG[:3],1))
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
                # Tail release of the button click that started the dial; keep it open.
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


CLASSES=(MCENV_OT_dial,)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
