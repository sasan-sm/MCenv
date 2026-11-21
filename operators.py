# SPDX-License-Identifier: GPL-3.0-or-later
import json
import math
import bpy
from bpy.props import StringProperty, IntProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper
from . import engine, biome_materials
from .properties import BIOMES, DIMENSION_BIOME_ITEMS


class MCENV_OT_create(bpy.types.Operator):
    bl_idname='mcenv.create'
    bl_label='Create Environment'
    bl_description='Create a separate MCenv collection; preserve the current world for removal'
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
        if world and world.name.startswith((engine.BRAND+' '+p.owner_id, engine.LEGACY_BRAND+' '+p.owner_id)):
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
            if data.name.startswith((engine.BRAND+' '+p.owner_id+' ', engine.LEGACY_BRAND+' '+p.owner_id+' ')) and data.users==0: bpy.data.materials.remove(data)
        if world and world.name.startswith((engine.BRAND+' '+p.owner_id, engine.LEGACY_BRAND+' '+p.owner_id)) and world.users==0: bpy.data.worlds.remove(world)
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
            if self.property_name == 'grass_side_overlay':
                if not image.size[0] or image.channels != 4:
                    self.report({'ERROR'},'Grass side overlay must be an RGBA image with transparency (PNG recommended)')
                    return {'CANCELLED'}
                image.pack()
            setattr(context.scene.mc_env,self.property_name,image)
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class MCENV_OT_geometry_add(bpy.types.Operator):
    bl_idname='mcenv.geometry_add'
    bl_label='Add Geometry'
    bl_description='Add only the chosen or selected meshes to the renderable wireframe list'
    bl_options={'REGISTER','UNDO'}
    use_selected: BoolProperty(default=False,options={'HIDDEN','SKIP_SAVE'})

    def execute(self,context):
        scene=context.scene; p=scene.mc_env
        candidates=list(context.selected_objects) if self.use_selected or not p.geometry_candidate else [p.geometry_candidate]
        existing={item.object for item in p.geometry_objects if item.object}
        count=0; skipped=0
        for obj in candidates:
            if obj in existing: continue
            if (obj.type!='MESH' or obj.get('mcenv_owner') or obj.library or obj.override_library
                    or obj.data.library or obj.mode!='OBJECT' or len(obj.users_scene)>1
                    or obj.name not in scene.objects):
                skipped+=1; continue
            mod=engine.build_geometry(scene,obj)
            item=p.geometry_objects.add(); item.object=obj; item.node_group=mod.node_group
            existing.add(obj); count+=1
        engine.sync_geometry(scene)
        self.report({'INFO'} if count else {'WARNING'},f'Added {count} meshes; {skipped} unsupported objects skipped. Duplicates are not added.')
        return {'FINISHED'} if count else {'CANCELLED'}


class MCENV_OT_geometry_remove(bpy.types.Operator):
    bl_idname='mcenv.geometry_remove'
    bl_label='Remove Geometry'
    bl_description='Remove only the MCenv wireframe effect and list entry; preserve the original object'
    bl_options={'REGISTER','UNDO'}
    index: IntProperty(default=-1)

    def execute(self,context):
        p=context.scene.mc_env
        if not 0<=self.index<len(p.geometry_objects): return {'CANCELLED'}
        engine.remove_geometry(context.scene,p.geometry_objects[self.index])
        p.geometry_objects.remove(self.index)
        return {'FINISHED'}


class MCENV_OT_animation_add(bpy.types.Operator):
    bl_idname='mcenv.animation_add'
    bl_label='Add'
    bl_description='Animate the chosen object, or selected meshes if the picker is empty; originals remain unchanged'
    bl_options={'REGISTER','UNDO'}
    use_selected: BoolProperty(default=False, options={'HIDDEN','SKIP_SAVE'})

    def execute(self,context):
        scene=context.scene; p=scene.mc_env
        objects=list(context.selected_objects) if self.use_selected or not p.animation_candidate else [p.animation_candidate]
        existing={item.object for item in p.animation_objects if item.object}
        count=0; skipped=0
        for obj in objects:
            if obj in existing: continue
            if (obj.type!='MESH' or obj.get('mcenv_owner') or obj.library or obj.data.library or obj.data.users>1
                    or obj.override_library or obj.mode!='OBJECT' or obj.name not in scene.objects
                    or sum(obj.name in s.objects for s in bpy.data.scenes)>1):
                skipped+=1; continue
            mode='CUSTOM' if obj.vertex_groups.get('MCENV_Wind') else 'AUTO'
            engine.build_animation(scene,obj,mode)
            # Replace the old selected-object wind tool, never stack two sways.
            for mod in list(obj.modifiers):
                if engine.mod_tag(mod,'mcenv_wind'):
                    group=mod.node_group; obj.modifiers.remove(mod)
                    if group and group.users==0: bpy.data.node_groups.remove(group)
            item=p.animation_objects.add(); item.object=obj; item.mode=mode
            existing.add(obj); count+=1
        engine.sync(scene)
        self.report({'INFO'} if count else {'WARNING'},f'Added {count} objects; {skipped} unsupported/shared objects skipped. Duplicates are not added.')
        return {'FINISHED'} if count else {'CANCELLED'}


class MCENV_OT_animation_remove(bpy.types.Operator):
    bl_idname='mcenv.animation_remove'
    bl_label='Remove from Animate'
    bl_description='Remove only the MCenv animation modifier and list entry, not the object or painted weights'
    bl_options={'REGISTER','UNDO'}
    index: IntProperty(default=-1)

    def execute(self,context):
        p=context.scene.mc_env
        if not 0<=self.index<len(p.animation_objects): return {'CANCELLED'}
        obj=p.animation_objects[self.index].object
        if obj: engine.remove_animation(context.scene,obj)
        p.animation_objects.remove(self.index)
        engine.sync(context.scene)
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
        for obj in meshes:
            if not any(engine.animation_owner(m) for m in obj.modifiers): engine.build_wind(obj)
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
                if engine.mod_tag(mod,'mcenv_wind'):
                    group=mod.node_group; obj.modifiers.remove(mod)
                    if group and group.users==0: bpy.data.node_groups.remove(group)
        return {'FINISHED'}


def biome_objects(context):
    return list(context.selected_objects if context.scene.mc_env.biome_scope == 'SELECTED' else context.scene.objects)


class MCENV_OT_detect_biome(bpy.types.Operator):
    bl_idname='mcenv.detect_biome'
    bl_label='Apply Biome to Imported World'
    bl_description='After MCprep Prep Materials, detect grass, leaves and water; preserve originals and replace existing MCprep tint without double coloring'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        result=biome_materials.bind(context.scene,biome_objects(context))
        engine.sync(context.scene)
        message=f"Bound {result['slots']} slots / {result['materials']} new materials; {result['skipped']} unrelated, {result['unsupported']} unsupported slots skipped"
        self.report({'INFO'} if result['slots'] else {'WARNING'},message)
        return {'FINISHED'} if result['slots'] else {'CANCELLED'}


class MCENV_OT_restore_biome(bpy.types.Operator):
    bl_idname='mcenv.restore_biome'
    bl_label='Restore Original Materials'
    bl_description='Restore saved pre-MCenv materials in the chosen scope; leaves user-replaced slots alone'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        count=biome_materials.restore(context.scene,biome_objects(context))
        self.report({'INFO'},f'Restored {count} material slots')
        return {'FINISHED'}


class MCENV_OT_custom_biome(bpy.types.Operator):
    bl_idname='mcenv.custom_biome'
    bl_label='Customize This Biome'
    bl_description='Copy all current preset tint colors to Custom before editing'
    bl_options={'REGISTER','UNDO'}

    def execute(self,context):
        p=context.scene.mc_env; ptr=context.scene.as_pointer()
        kinds=['GRASS','FOLIAGE','DRY_FOLIAGE','WATER','OAK','SPRUCE','BIRCH','JUNGLE','ACACIA','DARK_OAK','MANGROVE']
        values={kind:engine.biome_color(p,kind) for kind in kinds}
        engine._BUSY.add(ptr)
        try:
            for kind,value in values.items(): setattr(p,kind.lower()+'_color',value)
            p.biome='CUSTOM'
        finally: engine._BUSY.discard(ptr)
        engine.sync(context.scene)
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
                    mul=engine.node(t,'ShaderNodeVectorMath','MCenv Atlas scale',operation='MULTIPLY'); mul.inputs[1].default_value=(1,1/rows,1)
                    if tex.inputs[0].links: t.links.new(tex.inputs[0].links[0].from_socket,mul.inputs[0])
                    else:
                        uv=engine.node(t,'ShaderNodeTexCoord','MCenv UV'); t.links.new(uv.outputs['UV'],mul.inputs[0])
                    add=engine.node(t,'ShaderNodeVectorMath','MCenv Atlas frame',operation='ADD'); add['mcenv_atlas']=rows
                    t.links.new(mul.outputs[0],add.inputs[0]); t.links.new(add.outputs[0],tex.inputs[0]); tex.interpolation='Closest'; count+=1
        engine.sync(context.scene)
        if count==0:
            self.report({'WARNING'},'No unbound vertical-strip images found on selected meshes'); return {'CANCELLED'}
        self.report({'INFO'},f'Animated {count} texture strips')
        return {'FINISHED'}


SKIP={'rna_type','name','enabled','owner_id','previous_world','previous_world_empty'}


def preset_data(p):
    data={}
    for prop in p.bl_rna.properties:
        key=prop.identifier
        if key in SKIP or key.startswith('fold_') or prop.type in {'POINTER','COLLECTION'}: continue
        value=getattr(p,key)
        data[key]=list(value) if getattr(prop,'is_array',False) else value
    return {'format':'MCenv','version':1,'settings':data}


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
            if data.get('format') not in {'MCenv',engine.LEGACY_BRAND} or data.get('version')!=1 or not isinstance(data.get('settings'),dict): raise ValueError('Not a MCenv v1 preset')
            valid=preset_data(p)['settings']; settings=data['settings']
            # Validate the entire document before making any scene changes.
            for k,v in settings.items():
                if k not in valid: raise ValueError('Unknown property: '+k)
                prop=p.bl_rna.properties[k]
                if getattr(prop,'is_array',False):
                    if not isinstance(v,list) or len(v)!=prop.array_length or any(type(x) not in (int,float) or not math.isfinite(x) or x<0 or x>1 for x in v): raise ValueError('Invalid color: '+k)
                elif prop.type=='ENUM':
                    if v not in (BIOMES.keys() if k=='biome' else prop.enum_items.keys()): raise ValueError('Invalid choice: '+k)
                elif prop.type=='BOOLEAN':
                    if type(v) is not bool: raise ValueError('Invalid switch: '+k)
                elif prop.type in {'FLOAT','INT'}:
                    if type(v) not in (int,float) or not math.isfinite(v) or not prop.hard_min<=v<=prop.hard_max or (prop.type=='INT' and type(v) is not int): raise ValueError('Invalid number: '+k)
            target_dimension=settings.get('dimension',p.dimension)
            target_biome=settings.get('biome',p.biome)
            if target_biome not in {item[0] for item in DIMENSION_BIOME_ITEMS[target_dimension]}:
                raise ValueError('Biome does not belong to the chosen dimension')
            ptr=context.scene.as_pointer(); engine._BUSY.add(ptr)
            try:
                # Dimension first: dynamic biome enums must see the target dimension.
                if 'dimension' in settings: p.dimension=settings['dimension']
                for k,v in settings.items():
                    if k!='dimension': setattr(p,k,v)
                p['_active_dimension']=p.dimension
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
            for key in list(p.keys()):
                if key.startswith(('_biome_', '_fog_')) or key=='_active_dimension': del p[key]
        finally: engine._BUSY.discard(ptr)
        engine.sync(context.scene)
        return {'FINISHED'}


CLASSES=(MCENV_OT_create,MCENV_OT_remove,MCENV_OT_image,MCENV_OT_geometry_add,MCENV_OT_geometry_remove,MCENV_OT_animation_add,MCENV_OT_animation_remove,MCENV_OT_wind,MCENV_OT_unwind,MCENV_OT_detect_biome,MCENV_OT_restore_biome,MCENV_OT_custom_biome,MCENV_OT_atlas,MCENV_OT_export,MCENV_OT_import,MCENV_OT_reset)


def register():
    for cls in CLASSES: bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
