# SPDX-License-Identifier: GPL-3.0-or-later
"""Non-destructive, scene-scoped biome binding for MCprep-prepared materials.

MCprep compatibility is based on its MCPREP_saturate/MCPREP_diffuse metadata
and Add Color multiply stage (materials/generate.py). No MCprep installation
is required to use this module. A bundled RGBA overlay handles grass sides.
Nested shader groups and mixed texture atlases are intentionally not guessed:
use separate, per-block materials with local 0..1 UVs.
"""
import re
import sys
import bpy
from .properties import linear
from .assets import block_image

LEAVES = ('dark_oak', 'mangrove', 'spruce', 'birch', 'jungle', 'acacia', 'oak')
GRASS = {'grass', 'short_grass', 'tall_grass', 'tall_grass_top',
         'tall_grass_bottom', 'grass_block', 'grass_block_top', 'grass_top',
         'grass_block_overlay', 'grass_block_side_overlay', 'grass_side_overlay',
         'fern', 'large_fern_top', 'large_fern_bottom', 'double_plant_grass',
         'double_plant_fern', 'large_fern', 'sugar_cane', 'reeds', 'bush',
         'pink_petals_stem', 'wildflowers_stem', 'potted_fern'}
DRY = {'leaf_litter'}
SIDES = {'grass_block_side', 'grass_side', 'grass_side_saturated'}
WATER = {'water', 'water_still', 'water_flow', 'flowing_water', 'stationary_water',
         'water_overlay'}
ALIASES = {'grass_block_top': 'GRASS', 'grass_block_overlay': 'GRASS',
           'grass_block_side': 'GRASS_SIDE', 'grass_side': 'GRASS_SIDE',
           'leaves': 'OAK', 'leaves_oak': 'OAK', 'oak_leaves': 'OAK'}


def normalized(name):
    name = name.split(' • MCenv', 1)[0].replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'\.\d{3,}$', '', name.lower())
    name = re.sub(r'\.(png|jpg|jpeg|tga|bmp)$', '', name)
    name = re.sub(r'[_ -]\d{4}$', '', name)
    name = name.split('[', 1)[0].strip().replace('minecraft:', '')
    name = re.sub(r'^minecraft_block[-_]', '', name)
    return re.sub(r'[^a-z0-9_]+', '_', name).strip('_')


def canonical(name):
    # Loaded modules support both legacy MCprep_addon and Blender extensions.
    for key, module in tuple(sys.modules.items()):
        if 'mcprep' in key.lower() and key.endswith('.materials.generate'):
            function = getattr(module, 'get_mc_canonical_name', None)
            if function:
                try:
                    return normalized(function(name)[0])
                except (AttributeError, KeyError, TypeError, RuntimeError):
                    pass
    return normalized(name)


def classify_name(name):
    name = canonical(name)
    if name in GRASS: return 'GRASS'
    if name in DRY: return 'DRY_FOLIAGE'
    if name in SIDES: return 'GRASS_SIDE'
    if name in WATER: return 'WATER'
    if name in {'vine', 'vines'}: return 'FOLIAGE'
    for species in LEAVES:
        if name in {species+'_leaves', 'leaves_'+species}:
            return species.upper()
    return ALIASES.get(name)


def flag(node, name):
    props = getattr(node, 'mnp', None)
    return bool((props and getattr(props, name, False)) or node.get(name, False))


def diffuse_images(material):
    if not material.use_nodes: return []
    images = []
    for n in material.node_tree.nodes:
        if n.type != 'TEX_IMAGE' or not n.image or n.get('mcenv_side_overlay'): continue
        label = (n.name+' '+n.label).lower()
        if flag(n, 'MCPREP_diffuse') or 'diffuse' in label or 'albedo' in label:
            images.append(n.image)
    if not images:
        # Traverse color paths only, never normal/specular/roughness paths.
        seen = set()
        def visit(socket):
            for edge in socket.links:
                n = edge.from_node
                if n.as_pointer() in seen: continue
                seen.add(n.as_pointer())
                if n.type == 'TEX_IMAGE' and n.image:
                    if not n.get('mcenv_side_overlay'): images.append(n.image)
                elif n.type != 'GROUP':
                    for inp in n.inputs:
                        if inp.is_linked: visit(inp)
        for n in material.node_tree.nodes:
            socket = surface_color(n)
            if socket: visit(socket)
    return list(dict.fromkeys(images))


def classify(material):
    # Exact Java texture matches: stems are separate from flower petals;
    # moss, cherry/azalea leaves and lily pads must not receive biome tint.
    images = diffuse_images(material)
    image_kinds = {classify_name(im.name) or classify_name(im.filepath) for im in images}
    image_kinds.discard(None)
    kind = classify_name(material.get('mcenv_source_name', material.name))
    if len(images) > 1: return None
    return next(iter(image_kinds), kind)


def mix_sockets(n):
    if n.bl_idname == 'ShaderNodeMixRGB':
        return n.inputs[0], n.inputs[1], n.inputs[2], n.outputs[0]
    if n.bl_idname == 'ShaderNodeMix' and n.data_type == 'RGBA':
        return n.inputs[0], n.inputs[6], n.inputs[7], n.outputs[2]
    return None


def surface_color(n):
    if n.type == 'BSDF_PRINCIPLED': return n.inputs.get('Base Color')
    if n.type in {'BSDF_DIFFUSE', 'BSDF_GLASS', 'BSDF_REFRACTION',
                  'BSDF_TRANSLUCENT'}:
        return n.inputs.get('Color')
    return None


def image_baseline(image, green_only=False):
    """Estimate baked chromaticity, not brightness; never edit image pixels."""
    if not image or not image.has_data or not image.size[0]:
        return (1., 1., 1.), False
    pixels = image.pixels
    count = image.size[0]*image.size[1]
    # At most 256 deterministic samples, deliberately not per-frame.
    step = max(1, (count+255)//256)
    samples = []
    colored = False
    for index in range(step//2, count, step):
        k = index*image.channels
        if image.channels < 3: continue
        c = tuple(pixels[k+i] for i in range(3))
        if image.channels == 4 and pixels[k+3] < .5: continue
        if max(c) < .03: continue
        if green_only and not (c[1] > c[0]*1.07 and c[1] > c[2]*1.07):
            continue
        colored |= max(c)-min(c) > .04
        if not image.is_float and image.colorspace_settings.name == 'sRGB':
            c = tuple(linear(v) for v in c)
        samples.append(c)
    if not samples or not colored: return (1., 1., 1.), False
    avg = [sum(c[i] for c in samples)/len(samples) for i in range(3)]
    peak = max(avg)
    # Limit extreme ratios from tiny/noisy channels in baked textures.
    return tuple(max(.04, c/peak) for c in avg), True


def tint_value(settings, n):
    from .engine import biome_color
    color = biome_color(settings, n['mcenv_tint'])
    base = n.get('mcenv_baseline', (1, 1, 1))
    return tuple(color[i]/max(.04, base[i]) for i in range(3))+(1,)


def side_overlay_image(settings):
    """Load once, pack the supplied default so saved blends are portable."""
    if settings.grass_side_overlay:
        image = settings.grass_side_overlay
        return image if image.size[0] and image.channels == 4 else None
    return block_image(settings, 'grass_block_side_overlay.png')


def refresh(material, settings):
    if not material or not material.use_nodes: return
    for n in material.node_tree.nodes:
        if n.get('mcenv_side_overlay'):
            image = side_overlay_image(settings)
            if image is not None and n.image != image:
                n.image = image
        sockets = mix_sockets(n) if n.get('mcenv_tint') else None
        if sockets:
            sockets[2].default_value = tint_value(settings, n)


def prepare_side(material, settings):
    """RGBA color layer over the original side, never a normal-map replacement.

    Intercept diffuse color links on surface-color paths only. Alpha, normal,
    bump, roughness and other texture branches stay connected as before.
    """
    tree = material.node_tree
    if material.get('mcenv_side_version') == 2 and any(
            n.get('mcenv_side_overlay') for n in tree.nodes):
        refresh(material, settings)
        return True
    images = diffuse_images(material)
    if len(images) != 1:
        return False
    sources = [n for n in tree.nodes if n.type == 'TEX_IMAGE'
               and n.image == images[0] and not n.get('mcenv_side_overlay')]
    # A strip/atlas cannot use a standalone overlay without a UV tile mapping.
    if len(sources) != 1 or not images[0].size[0] or images[0].size[0] != images[0].size[1]:
        return False
    source = sources[0]
    if source.projection != 'FLAT':
        return False
    seen, destinations = set(), []

    def visit(socket):
        for edge in list(socket.links):
            node = edge.from_node
            if node == source and edge.from_socket == source.outputs['Color']:
                destinations.append(edge.to_socket)
                continue
            if node.as_pointer() in seen:
                continue
            seen.add(node.as_pointer())
            if node.type not in {'GROUP', 'TEX_IMAGE'}:
                for inp in node.inputs:
                    if inp.is_linked:
                        visit(inp)

    for node in tree.nodes:
        socket = surface_color(node)
        if socket is not None and any(out.is_linked for out in node.outputs):
            visit(socket)
    if not destinations:
        return False
    image = side_overlay_image(settings)
    if image is None or not image.size[0] or image.channels != 4:
        return False
    # The entire dirt/grass composite must not receive MCprep's old multiplier.
    for node in tree.nodes:
        sockets = mix_sockets(node)
        if sockets and node.blend_type == 'MULTIPLY' and (
                flag(node, 'MCPREP_saturate') or node.name == 'Add Color'):
            node.mute = True
    overlay = tree.nodes.new('ShaderNodeTexImage')
    overlay.name = 'MCenv Grass Side Overlay'
    overlay.label = 'MCenv RGBA grass overlay (same UV as side)'
    overlay['mcenv_side_overlay'] = True
    overlay.image = image
    overlay.interpolation = 'Closest'
    overlay.extension = source.extension
    overlay.location = (source.location.x, source.location.y - 320)
    if source.inputs['Vector'].is_linked:
        tree.links.new(source.inputs['Vector'].links[0].from_socket, overlay.inputs['Vector'])
    else:
        overlay.inputs['Vector'].default_value = source.inputs['Vector'].default_value[:]
    tint = tree.nodes.new('ShaderNodeMixRGB')
    tint.name = 'MCenv Side Biome Tint'
    tint.label = 'MCenv grass tint (overlay only)'
    tint.blend_type = 'MULTIPLY'
    tint.inputs[0].default_value = 1
    tint.use_clamp = False
    tint['mcenv_tint'] = 'GRASS'
    tint['mcenv_baseline'] = (1., 1., 1.)
    tint.location = (source.location.x + 250, source.location.y - 320)
    tree.links.new(overlay.outputs['Color'], tint.inputs[1])
    composite = tree.nodes.new('ShaderNodeMixRGB')
    composite.name = 'MCenv Side Alpha Composite'
    composite.label = 'MCenv tinted grass over original dirt'
    composite.blend_type = 'MIX'
    composite.location = (source.location.x + 480, source.location.y)
    tree.links.new(overlay.outputs['Alpha'], composite.inputs[0])
    tree.links.new(source.outputs['Color'], composite.inputs[1])
    tree.links.new(tint.outputs[0], composite.inputs[2])
    for destination in destinations:
        tree.links.new(composite.outputs[0], destination)
    material['mcenv_side_version'] = 2
    refresh(material, settings)
    return True


def prepare(material, settings, kind):
    """Only edits an owned copy. Returns False for unsupported shader layouts."""
    if not material.use_nodes: return False
    tree = material.node_tree
    if kind == 'GRASS_SIDE':
        return prepare_side(material, settings)
    # Reuse MCprep's original tint stage rather than stacking manual tint
    # nodes, which would cause multiply-on-multiply darkening.
    for n in list(tree.nodes):
        if not n.get('mcenv_tint') or 'mcenv_baseline' in n: continue
        sockets=mix_sockets(n)
        if not sockets: continue
        source=sockets[1].links[0].from_socket if sockets[1].is_linked else None
        for edge in list(sockets[3].links):
            destination=edge.to_socket
            if source: tree.links.new(source,destination)
            else: destination.default_value=sockets[1].default_value[:]
        tree.nodes.remove(n)
    existing = [n for n in tree.nodes if n.get('mcenv_tint')]
    if existing:
        for n in existing: n['mcenv_tint'] = kind
        refresh(material, settings)
        return True
    targets = [surface_color(n) for n in tree.nodes if surface_color(n) is not None
               and any(out.is_linked for out in n.outputs)]
    if not targets: return False
    images = diffuse_images(material)
    image = images[0] if len(images) == 1 else None
    mode = settings.biome_texture_mode
    baseline, _ = image_baseline(image, kind not in {'WATER','DRY_FOLIAGE'} and mode != 'COLORED')
    # Replace MCprep's active grayscale tint in place. This preserves its
    # animation, alpha, normals, roughness and every downstream shader branch.
    stages = [n for n in tree.nodes if mix_sockets(n) and
              (flag(n, 'MCPREP_saturate') or n.name == 'Add Color') and
              n.blend_type == 'MULTIPLY' and not n.mute and
              not mix_sockets(n)[2].is_linked and mix_sockets(n)[3].is_linked]
    if stages:
        for n in stages:
            n['mcenv_tint'] = kind
            n['mcenv_baseline'] = (1., 1., 1.)
            mix_sockets(n)[0].default_value = 1
            n.label = 'MCenv biome / MCprep Add Color'
        refresh(material, settings)
        return True
    if mode == 'GRAYSCALE': baseline = (1., 1., 1.)
    for socket in targets:
        source = socket.links[0].from_socket if socket.is_linked else None
        n = tree.nodes.new('ShaderNodeMixRGB')
        n.name = 'MCenv Biome tint'; n.label = 'MCenv '+kind.replace('_', ' ').title()
        n.blend_type = 'MULTIPLY'; n.inputs[0].default_value = 1
        n.use_clamp = False
        n['mcenv_tint'] = kind
        n['mcenv_baseline'] = baseline
        n.location = (socket.node.location.x-230, socket.node.location.y+150)
        if source:
            tree.links.new(source, n.inputs[1])
        else:
            n.inputs[1].default_value = socket.default_value[:]
        tree.links.new(n.outputs[0], socket)
    refresh(material, settings)
    return True


def bind(scene, objects):
    """Bind once; scene-owned material copies are shared within this operation.

    Object-linked slots prevent selected-only bindings changing unselected
    objects even when both objects use the very same Mesh datablock.
    """
    from .engine import owner
    settings = scene.mc_env
    token = owner(scene)
    cache = {}
    classified = {}
    # CollectionProperty.add() can reallocate RNA storage. Cache indices, not
    # PropertyGroup wrappers: retaining those across add() can hang Blender 4.5.
    records = {(r.object.as_pointer(),r.slot_index):i for i,r in enumerate(settings.material_bindings) if r.object}
    counts = {'slots': 0, 'materials': 0, 'skipped': 0, 'unsupported': 0}
    for obj in objects:
        if (obj.type != 'MESH' or obj.get('mcenv_owner') or obj.library or
                obj.override_library or not obj.data or obj.data.library):
            continue
        if len(obj.users_scene) > 1:
            # The very same Object cannot have different slots in two scenes.
            # Skip instead of silently changing an unrelated scene.
            counts['unsupported'] += len(obj.material_slots)
            continue
        for index, slot in enumerate(obj.material_slots):
            old = slot.material
            if not old: continue
            pointer=old.as_pointer()
            if pointer not in classified: classified[pointer]=classify(old)
            kind = classified[pointer]
            if not kind:
                counts['skipped'] += 1; continue
            record_index = records.get((obj.as_pointer(),index))
            record = settings.material_bindings[record_index] if record_index is not None else None
            if record and old == record.bound and old.get('mcenv_biome_owner') == token:
                # Re-running MCprep Prep Materials may replace this copy's nodes.
                if (old.get('mcenv_kind') == kind and old.get('mcenv_mode') == settings.biome_texture_mode
                        and (kind != 'GRASS_SIDE' or old.get('mcenv_side_version') == 2)):
                    if prepare(old, settings, kind):
                        counts['slots'] += 1
                    else: counts['unsupported'] += 1
                    continue
                # Changing mode/kind rebuilds from the original, never stacks.
                base = record.original or old
            else:
                base = old
            key = (base.as_pointer(), kind, settings.biome_texture_mode)
            mat = cache.get(key)
            if mat is None:
                mat = base.copy()
                mat.name = base.name.split(' • MCenv', 1)[0]+' • MCenv '+kind
                mat['mcenv_biome_owner'] = token
                mat['mcenv_source_name'] = base.get('mcenv_source_name', base.name)
                mat['mcenv_kind'] = kind; mat['mcenv_mode'] = settings.biome_texture_mode
                if not prepare(mat, settings, kind):
                    bpy.data.materials.remove(mat)
                    counts['unsupported'] += 1; continue
                cache[key] = mat; counts['materials'] += 1
            if record is None:
                record = settings.material_bindings.add()
                record.object = obj; record.slot_index = index
                records[(obj.as_pointer(),index)]=len(settings.material_bindings)-1
                record.original = old; record.original_link = slot.link
            elif old != record.bound:
                # A user replaced the slot since binding; don't restore stale data.
                record.original = old; record.original_link = slot.link
            slot.link = 'OBJECT'; slot.material = mat
            record.bound = mat
            counts['slots'] += 1
    return counts


def restore(scene, objects):
    settings = scene.mc_env
    pointers = {obj.as_pointer() for obj in objects}
    restored = 0
    for index in range(len(settings.material_bindings)-1, -1, -1):
        r = settings.material_bindings[index]
        if r.object and r.object.as_pointer() not in pointers: continue
        obj, mat = r.object, r.bound
        if obj and r.slot_index < len(obj.material_slots):
            slot = obj.material_slots[r.slot_index]
            if slot.material == mat:
                original = r.original
                # Don't overwrite a shared mesh material edited since binding.
                data_mat = obj.data.materials[r.slot_index]
                slot.link = 'DATA' if r.original_link == 'DATA' and data_mat == original else 'OBJECT'
                if slot.link == 'OBJECT': slot.material = original
                restored += 1
        settings.material_bindings.remove(index)
        # Removing the record releases its ID pointer before checking users.
        if mat and mat.get('mcenv_biome_owner') == settings.owner_id and mat.users == 0:
            bpy.data.materials.remove(mat)
    return restored
