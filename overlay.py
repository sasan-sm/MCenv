# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent translucent Time and Rotation dials, invoked as native operators."""
import math
import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

_INSTANCES = []
_SPACES = {'VIEW_3D': bpy.types.SpaceView3D, 'PROPERTIES': bpy.types.SpaceProperties,
           'NODE_EDITOR': bpy.types.SpaceNodeEditor, 'DOPESHEET_EDITOR': bpy.types.SpaceDopeSheetEditor,
           'GRAPH_EDITOR': bpy.types.SpaceGraphEditor}


def shape(shader, mode, vertices, color):
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, mode, {'pos': vertices}).draw(shader)


def label(x, y, text, size=13, color=(.92, .92, .92, 1)):
    blf.size(0, size)
    blf.color(0, *color)
    width = blf.dimensions(0, text)[0]
    blf.position(0, x-width/2, y, 0)
    blf.draw(0, text)


class DialMixin:
    property_name = ''

    @classmethod
    def poll(cls, context):
        return bool(context.scene and context.scene.mc_env.enabled and context.area
                    and context.area.type in _SPACES and context.region and context.region.type == 'WINDOW')

    def invoke(self, context, event):
        for old in list(_INSTANCES):
            old.finish()
        self.scene = context.scene
        self.area = context.area
        self.region = context.region
        self.window = context.window
        self.space_class = _SPACES[self.area.type]
        self.initial = getattr(self.scene.mc_env, self.property_name)
        self.closed = False
        self.dragging = False
        self.entry = ''
        self.scale = max(.75, min(1.75, context.preferences.system.ui_scale))
        self.radius = min(76*self.scale, max(40, self.region.width/2-24))
        margin = self.radius+28
        self.center = (max(margin, min(self.region.width-margin, event.mouse_x-self.region.x)),
                       max(margin+30, min(self.region.height-margin-30, event.mouse_y-self.region.y)))
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self.handle = self.space_class.draw_handler_add(self.draw_dial, (), 'WINDOW', 'POST_PIXEL')
        self.timer = context.window_manager.event_timer_add(.1, window=context.window)
        self.wm = context.window_manager
        _INSTANCES.append(self)
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def finish(self):
        if self.closed:
            return
        self.closed = True
        if self.handle:
            self.space_class.draw_handler_remove(self.handle, 'WINDOW')
            self.handle = None
        if self.timer:
            self.wm.event_timer_remove(self.timer)
            self.timer = None
        if self in _INSTANCES:
            _INSTANCES.remove(self)
        try:
            self.area.tag_redraw()
        except ReferenceError:
            pass

    def cancel(self, context):
        if not self.closed:
            setattr(self.scene.mc_env, self.property_name, self.initial)
            self.finish()

    def set_value(self, value):
        setattr(self.scene.mc_env, self.property_name, value % (24 if self.property_name == 'time' else 360))
        self.area.tag_redraw()

    def draw_dial(self):
        if self.closed or bpy.context.area != self.area or bpy.context.region != self.region:
            return
        cx, cy = self.center
        r = self.radius
        s = self.shader
        value = getattr(self.scene.mc_env, self.property_name)
        angle = value/24*math.tau-math.pi/2 if self.property_name == 'time' else math.radians(value)+math.pi/2
        points = [(cx+math.cos(i*math.tau/96)*r, cy+math.sin(i*math.tau/96)*r) for i in range(97)]
        gpu.state.blend_set('ALPHA')
        try:
            # Only a faint disc is painted: the editor/scene stays visible through it.
            vertices = []
            for a,b in zip(points, points[1:]):
                vertices.extend([(cx,cy), a, b])
            shape(s, 'TRIS', vertices, (.015,.018,.025,.20))
            shape(s, 'LINE_STRIP', points, (.8,.82,.85,.9))
            for i in range(24 if self.property_name == 'time' else 12):
                a=i*math.tau/(24 if self.property_name == 'time' else 12)
                shape(s,'LINES',[(cx+math.cos(a)*(r-5),cy+math.sin(a)*(r-5)),
                                 (cx+math.cos(a)*r,cy+math.sin(a)*r)],(.7,.72,.76,.7))
            hx=cx+math.cos(angle)*r; hy=cy+math.sin(angle)*r
            handle=[(hx+math.cos(i*math.tau/24)*6,hy+math.sin(i*math.tau/24)*6) for i in range(25)]
            shape(s,'LINE_STRIP',handle,(1,.18,.36,1))
            shape(s,'LINES',[(cx,cy-4),(hx,hy)],(1,.18,.36,.45))
            title='Time' if self.property_name=='time' else 'Rotation'
            label(cx,cy+r+17,'MCenv · '+title,round(13*self.scale))
            if self.entry:
                text=self.entry+'|'
            elif self.property_name=='time':
                minutes=round(value*60)%1440
                text=f'{minutes//60}:{minutes%60:02d}'
            else:
                text=f'{value:.1f}°'
            label(cx,cy-7,text,round(21*self.scale))
            label(cx,cy-r-24,'Drag ring · Type value · Enter / Esc',round(10*self.scale))
            label(cx,cy-r-40,'I: Animate Property',round(10*self.scale))
        finally:
            gpu.state.blend_set('NONE')

    def pointer_value(self, event):
        cx,cy=self.center
        x=event.mouse_x-self.region.x-cx; y=event.mouse_y-self.region.y-cy
        angle=math.atan2(y,x)
        if self.property_name=='time':
            return ((angle+math.pi/2)/math.tau*24)%24
        return math.degrees(angle-math.pi/2)%360

    def apply_entry(self):
        if not self.entry:
            return True
        try:
            if ':' in self.entry and self.property_name=='time':
                hours,minutes=self.entry.split(':')
                if not 0<=float(minutes)<60:
                    raise ValueError('Minutes must be between 0 and 59')
                value=float(hours)+float(minutes)/60
            else:
                value=float(self.entry)
            self.set_value(value)
            self.entry=''
            return True
        except (ValueError,TypeError):
            self.report({'WARNING'}, 'Enter hours (9.5 or 9:30) or degrees (45)')
            return False

    def modal(self, context, event):
        if self.closed:
            return {'CANCELLED'}
        try:
            valid=self.area in list(self.window.screen.areas) and self.scene==self.window.scene and self.scene.mc_env.enabled
        except (ReferenceError,AttributeError):
            valid=False
        if not valid:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type=='TIMER':
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS':
            if self.apply_entry():
                self.finish()
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if event.type=='I' and event.value=='PRESS':
            if self.apply_entry():
                bpy.ops.mcenv.animate_property(property_name=self.property_name)
                self.initial=getattr(self.scene.mc_env,self.property_name)
            return {'RUNNING_MODAL'}
        if event.type=='BACK_SPACE' and event.value=='PRESS':
            self.entry=self.entry[:-1]
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.value=='PRESS' and event.ascii and event.ascii in '0123456789.:-+':
            self.entry+=event.ascii
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            step=(1/60 if self.property_name=='time' else 1)*(.1 if event.shift else 1)
            self.set_value(getattr(self.scene.mc_env,self.property_name)+step*(1 if event.type=='WHEELUPMOUSE' else -1))
            return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            cx,cy=self.center
            distance=math.hypot(event.mouse_x-self.region.x-cx,event.mouse_y-self.region.y-cy)
            if distance>self.radius+20:
                if self.apply_entry():
                    self.finish()
                    return {'FINISHED'}
            else:
                self.dragging=True
                self.set_value(self.pointer_value(event))
            return {'RUNNING_MODAL'}
        if event.type=='MOUSEMOVE' and self.dragging:
            self.set_value(self.pointer_value(event))
            return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='RELEASE' and self.dragging:
            self.dragging=False
            self.finish()
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class MCENV_OT_time_dial(DialMixin, bpy.types.Operator):
    bl_idname='mcenv.time_dial'
    bl_label='MCenv Time'
    bl_description='Open the translucent Time dial; right-click this button to add it to Quick Favorites'
    bl_options={'REGISTER','UNDO'}
    property_name='time'


class MCENV_OT_rotation_dial(DialMixin, bpy.types.Operator):
    bl_idname='mcenv.rotation_dial'
    bl_label='MCenv Rotation'
    bl_description='Open the translucent Rotation dial; right-click this button to add it to Quick Favorites'
    bl_options={'REGISTER','UNDO'}
    property_name='rotation'


CLASSES=(MCENV_OT_time_dial,MCENV_OT_rotation_dial)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for instance in list(_INSTANCES):
        instance.finish()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
