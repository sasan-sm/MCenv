# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional GPU reference-style panel. Does not change the Blender theme."""
import math
import bpy
import blf
import gpu
from bpy.props import StringProperty
from gpu_extras.batch import batch_for_shader
from .ui import SECTIONS, BIOME_FIELDS, section_fields, field

_INSTANCES=[]
ACCENT=(.98,.13,.30,1)
TEXT=(.65,.65,.65,1)
MUTED=(.37,.37,.37,1)
BG=(.065,.065,.065,.98)


def srgb(v): return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055


def shape(shader, mode, vertices, color):
    shader.bind(); shader.uniform_float('color',color)
    batch_for_shader(shader,mode,{'pos':vertices}).draw(shader)


def rect(shader,x,y,w,h,c):
    shape(shader,'TRIS',[(x,y),(x+w,y),(x+w,y+h),(x,y),(x+w,y+h),(x,y+h)],c)


def text(x,y,value,size=12,color=TEXT):
    blf.size(0,size); blf.color(0,*color); blf.position(0,x,y,0); blf.draw(0,str(value))


def display(p,key):
    prop=p.bl_rna.properties[key]; val=getattr(p,key)
    if prop.type=='ENUM': return prop.enum_items[val].name
    if prop.type=='POINTER': return val.name if val else 'Default / None'
    if prop.type=='INT': return str(val)
    if key=='texture_fps': return f'{val:g} fps'
    if isinstance(val,float): return f'{val:.3g}'
    return str(val)


class MCENV_OT_edit(bpy.types.Operator):
    bl_idname='mcenv.edit_field'
    bl_label='Environment Setting'
    bl_options={'INTERNAL','UNDO'}
    property_name: StringProperty()

    def draw(self,context):
        if self.property_name in context.scene.mc_env.bl_rna.properties:
            field(self.layout,context.scene.mc_env,self.property_name)
            self.layout.label(text='Right-click the field for keyframes.',icon='KEY_HLT')

    def invoke(self,context,event):
        for instance in _INSTANCES: instance.suspended=True
        return context.window_manager.invoke_props_dialog(self,width=320)

    def execute(self,context):
        for instance in _INSTANCES: instance.suspended=False
        return {'FINISHED'}

    def cancel(self,context):
        for instance in _INSTANCES: instance.suspended=False


class MCENV_OT_overlay(bpy.types.Operator):
    bl_idname='mcenv.overlay'
    bl_label='Open Reference UI'
    bl_description='Floating dark environment panel in the 3D Viewport; drag dials, click fields, scroll to expand. Esc closes; native panel remains available'
    bl_options={'INTERNAL'}

    @classmethod
    def poll(cls,context): return context.window is not None and context.scene is not None

    def invoke(self,context,event):
        # Invokable from any editor (e.g. World Properties); it always draws in a 3D Viewport.
        area=context.area
        if area is None or area.type!='VIEW_3D':
            area=next((a for a in context.window.screen.areas if a.type=='VIEW_3D'),None)
            if area is None:
                self.report({'WARNING'},'Open a 3D Viewport to show the reference UI'); return {'CANCELLED'}
        for old in list(_INSTANCES):
            if old.area==area:
                old.finish(context); return {'FINISHED'}
        if not context.scene.mc_env.enabled: bpy.ops.mcenv.create()
        self.area=area; self.region=next((r for r in area.regions if r.type=='WINDOW'),None)
        self.scene=context.scene; self.window=context.window
        self.scroll=0; self.total=700; self.targets=[]; self.drag=None
        self.suspended=False; self.closed=False
        self.left=16; self.top_offset=40
        self.shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        self.handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_overlay,(), 'WINDOW','POST_PIXEL')
        self.timer=context.window_manager.event_timer_add(.1,window=context.window)
        _INSTANCES.append(self); context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def finish(self,context=None):
        if self.closed: return
        self.closed=True
        if self.handle:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW'); self.handle=None
        if self.timer:
            bpy.context.window_manager.event_timer_remove(self.timer); self.timer=None
        if self in _INSTANCES: _INSTANCES.remove(self)
        try: self.area.tag_redraw()
        except ReferenceError: pass

    def target(self,x,y,w,h,kind,key):
        self.targets.append((x,y,w,h,kind,key))

    def switch(self,x,y,value):
        s=self.shader
        rect(s,x,y,20,14,ACCENT if value else (.19,.19,.19,1))
        rect(s,x+(11 if value else 2),y+2,7,10,(.98,.98,.98,1))

    def prop_row(self,p,key,y):
        x=self.left+9; w=276; prop=p.bl_rna.properties[key]
        if prop.type=='BOOLEAN':
            text(x,y+7,prop.name); self.switch(x+w-20,y+5,getattr(p,key))
            self.target(x,y,w,26,'toggle',key)
        elif getattr(prop,'is_array',False):
            text(x,y+23,prop.name)
            rect(self.shader,x,y+1,w,19,(.24,.24,.24,1))
            rect(self.shader,x+3,y+4,w-6,13,(*[srgb(v) for v in getattr(p,key)],1))
            self.target(x,y,w,40,'edit',key)
            return 42
        else:
            text(x,y+9,prop.name,size=11)
            rect(self.shader,x+142,y+3,134,22,(.105,.11,.115,1))
            value=display(p,key)
            text(x+147,y+9,value[:21],size=11,color=(.8,.8,.8,1))
            self.target(x,y,w,29,'edit',key)
        return 30

    def section(self,p,key,title,toggle,y):
        x=self.left+9
        if 25<y<self.region.height-self.top_offset-26:
            expanded=getattr(p,'fold_'+key)
            if expanded: pts=[(x,y+17),(x+7,y+17),(x+3.5,y+12)]
            else: pts=[(x+1,y+19),(x+1,y+11),(x+5,y+15)]
            shape(self.shader,'TRIS',pts,TEXT); text(x+16,y+10,title)
            self.target(x,y,246,30,'fold','fold_'+key)
            if toggle:
                self.switch(x+254,y+9,getattr(p,toggle)); self.target(x+250,y,28,30,'toggle',toggle)
        y-=32
        if getattr(p,'fold_'+key) and (not toggle or getattr(p,toggle)):
            for prop in section_fields(p,key):
                height=42 if getattr(p.bl_rna.properties[prop],'is_array',False) else 30
                if 25<y<self.region.height-self.top_offset-48: self.prop_row(p,prop,y)
                y-=height
        return y

    def colors(self,p,keys,y):
        x=self.left+9
        for row in range((len(keys)+1)//2):
            for col in range(2):
                i=row*2+col
                if i>=len(keys): continue
                key=keys[i]; px=x+142*col
                if 25<y<self.region.height-self.top_offset-48:
                    text(px,y+24,p.bl_rna.properties[key].name)
                    rect(self.shader,px,y+1,134,23,(.23,.24,.25,1))
                    rect(self.shader,px+2,y+3,130,19,(.08,.08,.08,1))
                    rect(self.shader,px+4,y+5,126,15,(*[srgb(v) for v in getattr(p,key)],1))
                    self.target(px,y,134,40,'edit',key)
            y-=50
        return y

    def draw_overlay(self):
        context=bpy.context
        if self.closed or context.area!=self.area or context.region!=self.region: return
        if not hasattr(self.scene,'mc_env') or not self.scene.mc_env.enabled: return
        p=self.scene.mc_env; self.targets=[]
        s=self.shader; x=self.left; top=self.region.height-self.top_offset
        gpu.state.blend_set('ALPHA')
        try:
            rect(s,x,20,296,max(60,top-20),BG)
            y=top-156+self.scroll
            if 25<y<top-60:
                for cx,key,label in [(x+78,'time','Time'),(x+216,'rotation','Rotation')]:
                    cy=y+60; radius=48
                    points=[(cx+math.cos(i*math.tau/80)*radius,cy+math.sin(i*math.tau/80)*radius) for i in range(81)]
                    shape(s,'LINE_STRIP',points,(.39,.39,.39,1))
                    value=p.time if key=='time' else p.rotation
                    a=(value/24*math.tau-math.pi/2) if key=='time' else math.radians(value)+math.pi/2
                    hx=cx+math.cos(a)*radius; hy=cy+math.sin(a)*radius
                    rect(s,hx-9,hy-9,18,18,BG)
                    for j in range(8):
                        aa=j*math.tau/8
                        shape(s,'LINES',[(hx+math.cos(aa)*6,hy+math.sin(aa)*6),(hx+math.cos(aa)*9,hy+math.sin(aa)*9)],TEXT)
                    ring=[(hx+math.cos(i*math.tau/20)*3,hy+math.sin(i*math.tau/20)*3) for i in range(21)]
                    shape(s,'LINE_STRIP',ring,TEXT)
                    text(cx-16 if key=='time' else cx-26,cy+10,label)
                    if key=='time':
                        minutes=round(value*60)%1440; caption=f'{minutes//60}:{minutes%60:02d}'
                    else: caption=f'{value:.0f}°'
                    text(cx-len(caption)*3,cy-16,caption,color=(.86,.86,.86,1))
                    mx=cx-math.cos(a)*radius; my=cy-math.sin(a)*radius
                    rect(s,mx-10,my-10,20,20,BG)
                    crescent=[(mx+math.cos(i*math.pi/20-math.pi/2)*7,my+math.sin(i*math.pi/20-math.pi/2)*7) for i in range(21)]
                    shape(s,'LINE_STRIP',crescent,TEXT)
                    inner=[(mx+math.cos(i*math.pi/20-math.pi/2)*4,my+math.sin(i*math.pi/20-math.pi/2)*5) for i in range(21)]
                    shape(s,'LINE_STRIP',inner,TEXT)
                    self.target(cx-radius-5,cy-radius-5,106,106,'dial',key)
            y-=34
            for key,title,toggle in SECTIONS: y=self.section(p,key,title,toggle,y)
            if 25<y<top-55:
                text(x+9,y+23,'Biome'); rect(s,x+9,y-6,276,24,(.1,.105,.11,1))
                text(x+16,y+1,display(p,'biome')); text(x+267,y+1,'▾')
                self.target(x+9,y-6,276,45,'edit','biome')
            y-=49
            if p.biome=='CUSTOM': y=self.colors(p,BIOME_FIELDS,y)
            for caption,keys in [('Day scene colors:',['day_sky','day_clouds','day_sunlight','day_ambient']),('Night scene colors:',['night_sky','night_clouds','night_stars','night_ambient'])]:
                if 25<y<top-30: text(x+9,y+15,caption,color=MUTED)
                y-=33; y=self.colors(p,keys,y)
            if 25<y<top-45:
                text(x+9,y+12,'Twilight'); text(x+70,y+12,'(?)',color=MUTED)
                self.switch(x+263,y+8,p.twilight); self.target(x+9,y,276,30,'toggle','twilight')
            y-=32
            for key,title,toggle in [('fog','Fog','fog'),('wind','Wind','wind')]: y=self.section(p,key,title,toggle,y)
            if 25<y<top-45:
                text(x+9,y+11,'Texture animation speed',size=11)
                rect(s,x+211,y+3,74,24,(.1,.105,.11,1)); text(x+219,y+11,f'{p.texture_fps:g} fps',size=11)
                self.target(x+9,y,276,30,'edit','texture_fps')
            y-=42
            if 25<y<top-45:
                text(x+9,y+10,'Blender tools → World Properties / mc-env',size=11,color=MUTED)
            self.total=top-y+self.scroll
            # Fixed header drawn last to conceal scrolled content.
            rect(s,x,top-25,296,25,BG)
            text(x+8,top-16,'◉  ENVIRONMENT',size=11,color=ACCENT)
            text(x+277,top-17,'×',size=16,color=ACCENT)
            self.target(x+268,top-25,28,25,'close','')
            if self.total>top-30:
                available=max(1,top-50); ratio=min(1,available/self.total)
                thumb=max(24,available*ratio)
                ty=top-27-(self.scroll/max(1,self.total-available))*(available-thumb)-thumb
                rect(s,x+292,ty,2,thumb,(.32,.32,.32,.7))
        finally: gpu.state.blend_set('NONE')

    def modal(self,context,event):
        if self.closed: return {'CANCELLED'}
        try:
            valid=self.area in list(context.screen.areas) and self.scene.mc_env.enabled
        except (ReferenceError,AttributeError): valid=False
        if not valid:
            self.finish(context); return {'CANCELLED'}
        if event.type=='TIMER':
            self.area.tag_redraw(); return {'PASS_THROUGH'}
        if self.suspended: return {'PASS_THROUGH'}
        if event.type=='ESC':
            self.finish(context); return {'FINISHED'}
        # Use absolute region origin; sidebar invocation has a different mouse_region_x.
        mx=event.mouse_x-self.region.x; my=event.mouse_y-self.region.y
        inside=self.left<=mx<=self.left+296 and 20<=my<=self.region.height-self.top_offset
        if self.drag:
            key,start,initial=self.drag
            if event.type=='MOUSEMOVE':
                delta=(event.mouse_x-start[0])-(event.mouse_y-start[1])
                setattr(self.scene.mc_env,key,(initial+delta*.06)%24 if key=='time' else (initial+delta*.6)%360)
                self.area.tag_redraw(); return {'RUNNING_MODAL'}
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                if abs(event.mouse_x-start[0])+abs(event.mouse_y-start[1])<3:
                    bpy.ops.mcenv.edit_field('INVOKE_DEFAULT',property_name=key)
                else: bpy.ops.ed.undo_push(message='mc-env '+key)
                self.drag=None; return {'RUNNING_MODAL'}
        if inside and event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            maximum=max(0,self.total-(self.region.height-self.top_offset-25))
            self.scroll=max(0,min(maximum,self.scroll+(42 if event.type=='WHEELDOWNMOUSE' else -42)))
            self.area.tag_redraw(); return {'RUNNING_MODAL'}
        if inside and event.type=='LEFTMOUSE' and event.value=='PRESS':
            for x,y,w,h,kind,key in reversed(self.targets):
                if x<=mx<=x+w and y<=my<=y+h:
                    if kind=='close': self.finish(context); return {'FINISHED'}
                    if kind in {'toggle','fold'}:
                        setattr(self.scene.mc_env,key,not getattr(self.scene.mc_env,key))
                        if kind=='toggle': bpy.ops.ed.undo_push(message='mc-env '+key)
                    elif kind=='dial': self.drag=(key,(event.mouse_x,event.mouse_y),getattr(self.scene.mc_env,key))
                    else: bpy.ops.mcenv.edit_field('INVOKE_DEFAULT',property_name=key)
                    self.area.tag_redraw(); return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


CLASSES=(MCENV_OT_edit,MCENV_OT_overlay)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    for instance in list(_INSTANCES): instance.finish()
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
