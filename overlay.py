# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent Time/Rotation dials, invoked by panel buttons, F3 or user favorites.

Only the current editor/region receives the modal drawing. Blender's native
property fields/decorators handle keyframes; this module owns no animation UI.
"""
import math
import bpy
import blf
import gpu
from bpy.props import StringProperty
from gpu_extras.batch import batch_for_shader
from .ui import field

TEXT = (.91, .94, .95, 1)
MUTED = (.65, .73, .76, 1)
BACKDROP = (.025, .035, .045, .46)
BADGE = (.035, .048, .06, 1)
OUTLINE = (.008, .012, .018, 1)
RING = (.72, .81, .83, 1)
ACCENT = (.62, .87, .70, 1)
SUN = (1, .78, .30, 1)
MOON = (.78, .88, 1, 1)
VALID = ('time', 'rotation')
CENTER_PICK_RADIUS = 30.0
_ACTIVE_DIALS = set()

_SPACE_CLASSES = (('VIEW_3D','SpaceView3D'), ('PROPERTIES','SpaceProperties'),
                  ('NODE_EDITOR','SpaceNodeEditor'), ('IMAGE_EDITOR','SpaceImageEditor'),
                  ('SEQUENCE_EDITOR','SpaceSequenceEditor'), ('GRAPH_EDITOR','SpaceGraphEditor'),
                  ('CLIP_EDITOR','SpaceClipEditor'), ('OUTLINER','SpaceOutliner'),
                  ('TOPBAR','SpaceTopbar'), ('INFO','SpaceInfo'), ('TEXT_EDITOR','SpaceTextEditor'),
                  ('SPREADSHEET','SpaceSpreadsheet'), ('FILE_BROWSER','SpaceFileBrowser'))


def shape(shader, mode, vertices, color):
    if not vertices: return
    shader.bind()
    shader.uniform_float('color', color)
    batch_for_shader(shader, mode, {'pos': vertices}).draw(shader)


def rect(shader, x, y, w, h, color):
    shape(shader, 'TRIS', [(x,y),(x+w,y),(x+w,y+h),(x,y),(x+w,y+h),(x,y+h)], color)


def disc(shader, x, y, radius, color):
    vertices = []
    for i in range(64):
        a = i*math.tau/64; b = (i+1)*math.tau/64
        vertices.extend(((x,y), (x+math.cos(a)*radius,y+math.sin(a)*radius),
                         (x+math.cos(b)*radius,y+math.sin(b)*radius)))
    shape(shader, 'TRIS', vertices, color)


def text(x, y, value, size=12, color=TEXT, center=False, bold=False):
    value = str(value)
    blf.size(0, size)
    width = blf.dimensions(0, value)[0]
    left = x-width/2 if center else x
    # A dark keyline remains readable over white snow and a light foreground
    # remains readable over black. Slight overstrike gives the system font weight.
    for dx, dy in ((-1,-1),(-1,1),(1,-1),(1,1),(0,-2)):
        blf.color(0, *OUTLINE)
        blf.position(0, left+dx, y+dy, 0); blf.draw(0, value)
    blf.color(0, *color)
    for dx in ((0,.65) if bold else (0,)):
        blf.position(0, left+dx, y, 0); blf.draw(0, value)


def caption(p, key):
    if key == 'time':
        minutes = round(p.time*60) % 1440
        return f'{minutes//60}:{minutes%60:02d}'
    return f'{p.rotation:.0f}°'


def pixel_icon(shader, x, y, scale, moon=False):
    # Original pixel-art glyphs; only the glyph is square, never its backdrop.
    pattern = ('  XXX  ', ' XX    ', 'XX     ', 'XX     ', 'XX   X ', ' XXXXX ', '  XXX  ') if moon else (
              '   X   ', ' X   X ', '  XXX  ', 'X XXX X', '  XXX  ', ' X   X ', '   X   ')
    unit = 2*scale
    for row, line in enumerate(pattern):
        for column, pixel in enumerate(line):
            if pixel == 'X':
                rect(shader, x+(column-3.5)*unit, y+(2.5-row)*unit, unit, unit, MOON if moon else SUN)


def _space_class(area):
    return next((getattr(bpy.types, name, None) for kind,name in _SPACE_CLASSES if area.type == kind), None)


class MCENV_OT_edit(bpy.types.Operator):
    bl_idname = 'mcenv.edit_field'
    bl_label = 'Environment Setting'
    bl_options = {'INTERNAL', 'UNDO'}
    property_name: StringProperty()

    def invoke(self, context, event):
        if self.property_name not in VALID: return {'CANCELLED'}
        self.initial = getattr(context.scene.mc_env, self.property_name)
        return context.window_manager.invoke_props_dialog(self, width=280)

    def draw(self, context):
        if self.property_name in VALID:
            field(self.layout, context.scene.mc_env, self.property_name)

    def execute(self, context): return {'FINISHED'}

    def cancel(self, context):
        setattr(context.scene.mc_env, self.property_name, self.initial)


class DialMixin:
    property_name = ''

    @classmethod
    def poll(cls, context):
        p = getattr(context.scene, 'mc_env', None) if context.scene else None
        return p is not None and p.enabled and context.area is not None and context.window is not None

    def invoke(self, context, event):
        if self.property_name not in VALID: return {'CANCELLED'}
        self.scene = context.scene; self.window = context.window; self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == 'WINDOW'), None)
        if self.region is None: return {'CANCELLED'}
        self.space_cls = _space_class(self.area)
        if self.space_cls is None:
            bpy.ops.mcenv.edit_field('INVOKE_DEFAULT', property_name=self.property_name)
            return {'CANCELLED'}
        self.initial = getattr(self.scene.mc_env, self.property_name)
        self.moved = False; self.seen_press = False
        self.scale = max(.75, min(1.75, context.preferences.system.ui_scale))
        self.radius = min(104*self.scale, max(24, (self.region.width-44*self.scale)/2),
                          max(24, (self.region.height-112*self.scale)/2))
        margin = self.radius+19*self.scale
        def clamp_center(value, extent, lower, upper):
            return max(0, min(extent, extent/2 if lower > upper else min(max(value,lower),upper)))
        self.center = (clamp_center(event.mouse_x-self.region.x, self.region.width, margin, self.region.width-margin),
                       clamp_center(event.mouse_y-self.region.y, self.region.height, margin+34*self.scale,
                                    self.region.height-margin-34*self.scale))
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        try:
            self.handle = self.space_cls.draw_handler_add(self.draw_dial, (), 'WINDOW', 'POST_PIXEL')
        except (AttributeError, RuntimeError):
            self.handle = None
        if self.handle is None:
            bpy.ops.mcenv.edit_field('INVOKE_DEFAULT', property_name=self.property_name)
            return {'CANCELLED'}
        _ACTIVE_DIALS.add(self)
        context.window_manager.modal_handler_add(self)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def finish(self):
        handle = getattr(self, 'handle', None)
        self.handle = None
        _ACTIVE_DIALS.discard(self)
        if handle:
            try: self.space_cls.draw_handler_remove(handle, 'WINDOW')
            except (ReferenceError, RuntimeError, ValueError): pass
        try: self.area.tag_redraw()
        except ReferenceError: pass

    def cancel(self, context):
        try: setattr(self.scene.mc_env, self.property_name, self.initial)
        except ReferenceError: pass
        self.finish()

    def apply(self, value):
        if self.property_name == 'time': value = (round((value % 24)*60)/60) % 24
        else: value = (round(value)+180) % 360-180
        setattr(self.scene.mc_env, self.property_name, value)

    def value_at(self, angle_deg):
        return ((angle_deg+90) % 360)/15 if self.property_name == 'time' else angle_deg-90

    def draw_dial(self):
        if getattr(self, 'handle', None) is None: return
        try:
            if bpy.context.area != self.area or bpy.context.region != self.region: return
            p = self.scene.mc_env
        except ReferenceError: return
        s = self.shader; cx,cy = self.center; radius = self.radius; scale = self.scale
        value = getattr(p, self.property_name)
        angle = value/24*math.tau-math.pi/2 if self.property_name == 'time' else math.radians(value)+math.pi/2
        badge_radius = 15*scale
        gap = math.asin(min(.9, (badge_radius+2*scale)/radius))
        old_width = gpu.state.line_width_get()
        old_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')
        try:
            disc(s, cx, cy, radius+3*scale, BACKDROP)
            # Real gaps around both badges: no ring or tick is drawn underneath.
            def visible(a):
                return all(abs((a-marker+math.pi) % math.tau-math.pi) > gap
                           for marker in (angle, angle+math.pi))
            ring = []
            for i in range(192):
                a = i*math.tau/192; b = (i+1)*math.tau/192
                if visible(a) and visible(b):
                    ring.extend(((cx+math.cos(a)*radius,cy+math.sin(a)*radius),
                                 (cx+math.cos(b)*radius,cy+math.sin(b)*radius)))
            gpu.state.line_width_set(4*scale); shape(s, 'LINES', ring, OUTLINE)
            gpu.state.line_width_set(1.4*scale); shape(s, 'LINES', ring, RING)
            count = 24 if self.property_name == 'time' else 12
            for i in range(count):
                a = i*math.tau/count
                if not visible(a): continue
                length = (9 if i % (count//4) == 0 else 4)*scale
                points = [(cx+math.cos(a)*(radius-length),cy+math.sin(a)*(radius-length)),
                          (cx+math.cos(a)*radius,cy+math.sin(a)*radius)]
                gpu.state.line_width_set(3*scale); shape(s, 'LINES', points, OUTLINE)
                gpu.state.line_width_set(1*scale); shape(s, 'LINES', points, ACCENT if length > 5*scale else MUTED)
            for opposite in (False, True):
                a = angle+(math.pi if opposite else 0)
                x = cx+math.cos(a)*radius; y = cy+math.sin(a)*radius
                disc(s, x, y, badge_radius+2*scale, OUTLINE)
                disc(s, x, y, badge_radius+scale, MOON if opposite else SUN)
                disc(s, x, y, badge_radius, BADGE)
                pixel_icon(s, x, y, scale, moon=opposite)
            text(cx, cy+radius+28*scale, 'MCENV / '+self.property_name.upper(),
                 size=round(12*scale), color=ACCENT, center=True, bold=True)
            text(cx, cy+12*scale, self.property_name.title(), size=round(18*scale), center=True, bold=True)
            text(cx, cy-26*scale, caption(p, self.property_name), size=round(29*scale), center=True, bold=True)
            text(cx, cy-radius-31*scale, 'Click: confirm   /   Center: type', size=round(10*scale), center=True)
            text(cx, cy-radius-47*scale, 'Scroll: fine   /   Esc: cancel', size=round(10*scale), color=MUTED, center=True)
        finally:
            gpu.state.line_width_set(old_width)
            gpu.state.blend_set(old_blend)

    def modal(self, context, event):
        if getattr(self, 'handle', None) is None: return {'CANCELLED'}
        try:
            valid = self.area in list(context.screen.areas) and self.window == context.window
        except ReferenceError:
            self.cancel(context); return {'CANCELLED'}
        if not valid:
            self.cancel(context); return {'CANCELLED'}
        dx = event.mouse_x-self.region.x-self.center[0]
        dy = event.mouse_y-self.region.y-self.center[1]
        center_hit = math.hypot(dx,dy) < CENTER_PICK_RADIUS*self.scale
        if event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE'}:
            if not center_hit:
                self.apply(self.value_at(math.degrees(math.atan2(dy,dx))))
                self.moved = True
            self.area.tag_redraw(); return {'RUNNING_MODAL'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            step = 1/60 if self.property_name == 'time' else 1
            self.apply(getattr(self.scene.mc_env,self.property_name)+(step if event.type == 'WHEELUPMOUSE' else -step))
            self.moved = True; self.area.tag_redraw(); return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.seen_press = True; return {'RUNNING_MODAL'}
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if not self.seen_press: return {'RUNNING_MODAL'}
            self.finish()
            if self.moved: bpy.ops.ed.undo_push(message='MCenv '+self.property_name)
            if center_hit: bpy.ops.mcenv.edit_field('INVOKE_DEFAULT', property_name=self.property_name)
            return {'FINISHED'}
        if event.type in {'RET','NUMPAD_ENTER'} and event.value == 'PRESS':
            self.finish()
            if self.moved: bpy.ops.ed.undo_push(message='MCenv '+self.property_name)
            return {'FINISHED'}
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.cancel(context); return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class MCENV_OT_time_dial(DialMixin, bpy.types.Operator):
    bl_idname = 'mcenv.time_dial'
    bl_label = 'MCenv Time'
    bl_description = 'Open the Time dial; right-click this button to add it to Quick Favorites'
    bl_options = {'REGISTER'}
    property_name = 'time'


class MCENV_OT_rotation_dial(DialMixin, bpy.types.Operator):
    bl_idname = 'mcenv.rotation_dial'
    bl_label = 'MCenv Rotation'
    bl_description = 'Open the Rotation dial; right-click this button to add it to Quick Favorites'
    bl_options = {'REGISTER'}
    property_name = 'rotation'


CLASSES = (MCENV_OT_edit, MCENV_OT_time_dial, MCENV_OT_rotation_dial)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    for dial in tuple(_ACTIVE_DIALS): dial.cancel(bpy.context)
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
