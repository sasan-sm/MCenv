# SPDX-License-Identifier: GPL-3.0-or-later
import json
import math
import os
import shutil
import bpy
from bpy.props import StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from . import engine


class MCENV_OT_create(bpy.types.Operator):
    bl_idname='mcenv.create'
    bl_label='Create Environment'
    bl_description='Create a separate mc-env collection; preserve the current world for removal'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        p=context.scene.mc_env
        if not p.enabled:
            p.previous_world=context.scene.world
            p.previous_world_empty=context.scene.world is None
            p.enabled=True
        engine.sync(context.scene)
        error=engine._ERRORS.get(context.scene.as_pointer())
        if error:
            self.report({'ERROR'},error); return {'CANCELLED'}
        self.report({'INFO'},'Environment ready. Use Rendered view with Scene World and Scene Lights.')
        return {'FINISHED'}


class MCENV_OT_remove(bpy.types.Operator):
    bl_idname='mcenv.remove'
    bl_label='Remove Environment'
    bl_description='Remove only this scene\'s environment rig and restore its previous world; keep selected-object tools'
    bl_options={'REGISTER','UNDO'}

    def invoke(self,context,event): return context.window_manager.invoke_confirm(self,event)

    def execute(self,context):
        scene=context.scene; p=scene.mc_env; p.enabled=False
        world=scene.world
        if world and world.name.startswith('mc-env '+p.owner_id):
            scene.world=None if p.previous_world_empty else p.previous_world
        for col in list(scene.collection.children):
            if col.get('mcenv_owner')==p.owner_id:
                for obj in list(col.objects):
                    data=obj.data
                    bpy.data.objects.remove(obj,do_unlink=True)
                    if data and data.users==0:
                        if isinstance(data,bpy.types.Mesh): bpy.data.meshes.remove(data)
                        elif isinstance(data,bpy.types.Light): bpy.data.lights.remove(data)
                bpy.data.collections.remove(col)
        # Remove unused rig data only; never purge a user's data or bound material.
        for data in list(bpy.data.materials):
            if data.name.startswith('mc-env '+p.owner_id+' ') and data.users==0: bpy.data.materials.remove(data)
        if world and world.name.startswith('mc-env '+p.owner_id) and world.users==0: bpy.data.worlds.remove(world)
        return {'FINISHED'}


class MCENV_OT_image(bpy.types.Operator,ImportHelper):
    bl_idname='mcenv.load_image'
    bl_label='Load Environment Image'
    bl_options={'REGISTER','UNDO'}
    filter_glob: StringProperty(default='*.png;*.jpg;*.jpeg;*.exr;*.hdr;*.tga;*.webp;*.tif',options={'HIDDEN'})
    property_name: StringProperty()

    def execute(self,context):
        allowed={p.identifier for p in context.scene.mc_env.bl_rna.properties if p.type=='POINTER' and p.fixed_type.identifier=='Image'}
        if self.property_name not in allowed: return {'CANCELLED'}
        try:
            image=bpy.data.images.load(self.filepath,check_existing=True)
            setattr(context.scene.mc_env,self.property_name,image)
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MCENV_OT_wind(bpy.types.Operator):
    bl_idname='mcenv.bind_wind'
    bl_label='Add Wind to Selected'
    bl_description='Add non-destructive sway and automatic height weights to selected meshes; edit MCENV_Wind weights to pin roots'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        meshes=[o for o in context.selected_objects if o.type=='MESH' and not o.get('mcenv_owner') and o.library is None]
        if not meshes:
            self.report({'WARNING'},'Select editable mesh objects first'); return {'CANCELLED'}
        for obj in meshes: engine.build_wind(obj)
        engine.sync(context.scene)
        self.report({'INFO'},f'Wind added to {len(meshes)} meshes. Paint MCENV_Wind weights as needed.')
        return {'FINISHED'}


class MCENV_OT_unwind(bpy.types.Operator):
    bl_idname='mcenv.remove_wind'
    bl_label='Remove Wind from Selected'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        for obj in context.selected_objects:
            for mod in list(obj.modifiers):
                if mod.get('mcenv_wind'):
                    group=mod.node_group; obj.modifiers.remove(mod)
                    if group and group.users==0: bpy.data.node_groups.remove(group)
        return {'FINISHED'}


class MCENV_OT_tint(bpy.types.Operator):
    bl_idname='mcenv.bind_tint'
    bl_label='Apply Biome Tint to Selected'
    bl_description='Make local material copies and multiply Base Color by the selected biome tint; does not classify imported blocks automatically'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        kind=context.scene.mc_env.tint_kind; count=0
        for obj in context.selected_objects:
            if obj.type!='MESH' or obj.get('mcenv_owner') or obj.library: continue
            for slot in obj.material_slots:
                old=slot.material
                if not old or not old.use_nodes: continue
                # Copy first, so unselected objects sharing the original stay untouched.
                m=old.copy(); m.name=old.name+' • mc-env '+kind; slot.link='OBJECT'; slot.material=m
                t=m.node_tree
                for bs in [n for n in t.nodes if n.type=='BSDF_PRINCIPLED']:
                    socket=bs.inputs['Base Color']
                    if socket.links and socket.links[0].from_node.get('mcenv_tint'):
                        tint=socket.links[0].from_node
                    else:
                        tint=engine.node(t,'ShaderNodeMixRGB','mc-env Biome tint',blend_type='MULTIPLY')
                        tint.inputs[0].default_value=1
                        if socket.links:
                            source=socket.links[0].from_socket; t.links.new(source,tint.inputs[1])
                        else: tint.inputs[1].default_value=socket.default_value[:]
                        t.links.new(tint.outputs[0],socket)
                    tint['mcenv_tint']=kind; tint.inputs[2].default_value=engine.rgba(engine.biome_color(context.scene.mc_env,kind)); count+=1
        if not count:
            self.report({'WARNING'},'Select meshes with Principled BSDF materials'); return {'CANCELLED'}
        return {'FINISHED'}


class MCENV_OT_untint(bpy.types.Operator):
    bl_idname='mcenv.remove_tint'
    bl_label='Remove Biome Tint from Selected'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        for obj in context.selected_objects:
            for slot in obj.material_slots:
                m=slot.material
                if not m or not m.use_nodes: continue
                t=m.node_tree
                for n in list(t.nodes):
                    if not n.get('mcenv_tint'): continue
                    source=n.inputs[1].links[0].from_socket if n.inputs[1].links else None
                    for l in list(n.outputs[0].links):
                        dest=l.to_socket
                        if source: t.links.new(source,dest)
                        else: dest.default_value=n.inputs[1].default_value[:]
                    t.nodes.remove(n)
        return {'FINISHED'}


class MCENV_OT_atlas(bpy.types.Operator):
    bl_idname='mcenv.bind_atlas'
    bl_label='Animate Selected Texture Strips'
    bl_description='Treat tall images as vertical stacks of square frames; duplicates materials before editing. Use only on animated textures'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        count=0
        for obj in context.selected_objects:
            if obj.type!='MESH' or obj.get('mcenv_owner'): continue
            for slot in obj.material_slots:
                old=slot.material
                if not old or not old.use_nodes: continue
                candidates=[n for n in old.node_tree.nodes if n.type=='TEX_IMAGE' and n.image and n.image.size[0]>0 and n.image.size[1]>n.image.size[0] and n.image.size[1]%n.image.size[0]==0 and not (n.inputs[0].links and n.inputs[0].links[0].from_node.get('mcenv_atlas'))]
                if not candidates: continue
                names=[n.name for n in candidates]; m=old.copy(); slot.link='OBJECT'; slot.material=m; t=m.node_tree
                for name in names:
                    tex=t.nodes[name]; rows=tex.image.size[1]//tex.image.size[0]
                    mul=engine.node(t,'ShaderNodeVectorMath','mc-env Atlas scale',operation='MULTIPLY'); mul.inputs[1].default_value=(1,1/rows,1)
                    if tex.inputs[0].links: t.links.new(tex.inputs[0].links[0].from_socket,mul.inputs[0])
                    else:
                        uv=engine.node(t,'ShaderNodeTexCoord','mc-env UV'); t.links.new(uv.outputs['UV'],mul.inputs[0])
                    add=engine.node(t,'ShaderNodeVectorMath','mc-env Atlas frame',operation='ADD'); add['mcenv_atlas']=rows
                    t.links.new(mul.outputs[0],add.inputs[0]); t.links.new(add.outputs[0],tex.inputs[0]); tex.interpolation='Closest'; count+=1
        engine.sync(context.scene)
        if count==0:
            self.report({'WARNING'},'No unbound vertical-strip images found on selected meshes'); return {'CANCELLED'}
        self.report({'INFO'},f'Animated {count} texture strips')
        return {'FINISHED'}


class MCENV_OT_uninstall(bpy.types.Operator):
    bl_idname='mcenv.uninstall'
    bl_label='Uninstall mc-env'
    bl_description='Remove the mc-env environment from every scene, restore previous worlds, and delete the add-on from Blender. Save your .blend first'
    bl_options={'REGISTER'}

    def invoke(self,context,event): return context.window_manager.invoke_confirm(self,event)

    def execute(self,context):
        for scene in list(bpy.data.scenes):
            if scene.library: continue
            try:
                with context.temp_override(scene=scene):
                    bpy.ops.mcenv.remove('EXEC_DEFAULT')
            except Exception: pass
        pkg=__package__; pkg_dir=os.path.dirname(__file__)

        def finish():
            # Official Blender removal (same operator the Preferences view uses),
            # which disables the add-on, deletes its files and refreshes the list.
            try:
                bpy.ops.preferences.addon_remove('EXEC_DEFAULT',module=pkg)
            except Exception: pass
            try:
                if os.path.isdir(pkg_dir):
                    import addon_utils
                    addon_utils.disable(pkg,default_set=True)
            except Exception: pass
            try:
                import sys
                for name in [m for m in list(sys.modules) if m==pkg or m.startswith(pkg+'.')]:
                    del sys.modules[name]
            except Exception: pass
            try: shutil.rmtree(pkg_dir,ignore_errors=True)
            except Exception: pass
            try: bpy.ops.wm.save_userpref()
            except Exception: pass
            return None

        bpy.app.timers.register(finish,first_interval=.3)
        self.report({'INFO'},'mc-env removed from all scenes; the add-on is being uninstalled')
        return {'FINISHED'}


SKIP={'rna_type','name','enabled','owner_id','previous_world','previous_world_empty','tint_kind'}


def preset_data(p):
    data={}
    for prop in p.bl_rna.properties:
        key=prop.identifier
        if key in SKIP or key.startswith('fold_') or prop.type=='POINTER': continue
        value=getattr(p,key)
        data[key]=list(value) if getattr(prop,'is_array',False) else value
    return {'format':'mc-env','version':1,'settings':data}


class MCENV_OT_export(bpy.types.Operator,ExportHelper):
    bl_idname='mcenv.export_preset'
    bl_label='Export Environment Preset'
    filename_ext='.json'
    filter_glob: StringProperty(default='*.json',options={'HIDDEN'})

    def execute(self,context):
        try:
            with open(self.filepath,'w',encoding='utf8') as f: json.dump(preset_data(context.scene.mc_env),f,indent=2)
        except OSError as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MCENV_OT_import(bpy.types.Operator,ImportHelper):
    bl_idname='mcenv.import_preset'
    bl_label='Import Environment Preset'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.json'
    filter_glob: StringProperty(default='*.json',options={'HIDDEN'})

    def execute(self,context):
        p=context.scene.mc_env
        try:
            with open(self.filepath,encoding='utf8') as f: data=json.load(f)
            if data.get('format')!='mc-env' or data.get('version')!=1 or not isinstance(data.get('settings'),dict): raise ValueError('Not a mc-env v1 preset')
            valid=preset_data(p)['settings']; settings=data['settings']
            # Validate the entire document before making any scene changes.
            for k,v in settings.items():
                if k not in valid: raise ValueError('Unknown property: '+k)
                prop=p.bl_rna.properties[k]
                if getattr(prop,'is_array',False):
                    if not isinstance(v,list) or len(v)!=prop.array_length or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 or x>1 for x in v): raise ValueError('Invalid color: '+k)
                elif prop.type=='ENUM':
                    if v not in prop.enum_items.keys(): raise ValueError('Invalid choice: '+k)
                elif prop.type=='BOOLEAN':
                    if type(v) is not bool: raise ValueError('Invalid switch: '+k)
                elif prop.type in {'FLOAT','INT'}:
                    if type(v) not in (int,float) or not math.isfinite(v) or not prop.hard_min<=v<=prop.hard_max or (prop.type=='INT' and type(v) is not int): raise ValueError('Invalid number: '+k)
            ptr=context.scene.as_pointer(); engine._BUSY.add(ptr)
            try:
                for k,v in settings.items(): setattr(p,k,v)
            finally: engine._BUSY.discard(ptr)
            engine.sync(context.scene)
        except (OSError,ValueError,TypeError,AttributeError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MCENV_OT_reset(bpy.types.Operator):
    bl_idname='mcenv.reset'
    bl_label='Reset Environment Settings'
    bl_options={'REGISTER','UNDO'}

    def invoke(self,context,event): return context.window_manager.invoke_confirm(self,event)

    def execute(self,context):
        p=context.scene.mc_env; ptr=context.scene.as_pointer(); engine._BUSY.add(ptr)
        try:
            for k in preset_data(p)['settings']: p.property_unset(k)
        finally: engine._BUSY.discard(ptr)
        engine.sync(context.scene)
        return {'FINISHED'}


CLASSES=(MCENV_OT_create,MCENV_OT_remove,MCENV_OT_uninstall,MCENV_OT_image,MCENV_OT_wind,MCENV_OT_unwind,MCENV_OT_tint,MCENV_OT_untint,MCENV_OT_atlas,MCENV_OT_export,MCENV_OT_import,MCENV_OT_reset)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
