# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-owned data only. No network, external assets, eval or third-party packages."""
import math
import uuid
import random
import colorsys
import bpy
from mathutils import Vector
from bpy.app.handlers import persistent
from .properties import BIOMES, CLIMATE, DRY_FOLIAGE, rgb, linear
from . import assets

_BUSY = set()
_ERRORS = {}
BRAND = 'MCenv'
# Preserve data from version 1.0 without keeping the old display name.
LEGACY_BRAND = 'mc' + '-env'


def migrate_named_data(scene):
    token = scene.mc_env.owner_id
    for datablocks in (bpy.data.worlds, bpy.data.materials, bpy.data.images):
        for block in datablocks:
            if block.name.startswith(LEGACY_BRAND+' '+token+' '):
                block.name = BRAND+block.name[len(LEGACY_BRAND):]
    for col in scene.collection.children:
        if col.get('mcenv_owner') == token and col.name.startswith(LEGACY_BRAND):
            col.name = BRAND+col.name[len(LEGACY_BRAND):]
    for obj in scene.objects:
        if obj.get('mcenv_owner') == token:
            if obj.name.startswith(LEGACY_BRAND): obj.name = BRAND+obj.name[len(LEGACY_BRAND):]
            if obj.data and obj.data.name.startswith(LEGACY_BRAND): obj.data.name = BRAND+obj.data.name[len(LEGACY_BRAND):]


def mix(a, b, t):
    return tuple(x*(1-t)+y*t for x, y in zip(a,b))


def rgba(c):
    return (*c[:3], 1)


def owner(scene):
    p = scene.mc_env
    # A linked scene copy inherits a collection but must not edit the source rig.
    shared = [c for c in scene.collection.children if c.get('mcenv_owner') == p.owner_id
              and c.get('mcenv_scene') is not None and c.get('mcenv_scene') != scene]
    if shared:
        for c in shared: scene.collection.children.unlink(c)
        p.owner_id = ''
    if not p.owner_id:
        p.owner_id = uuid.uuid4().hex[:12]
    return p.owner_id


def owned(scene, role):
    token = scene.mc_env.owner_id
    return next((o for o in scene.objects if o.get('mcenv_owner') == token and o.get('mcenv_role') == role), None)


def collection(scene):
    token = owner(scene)
    col = next((c for c in scene.collection.children if c.get('mcenv_owner') == token), None)
    if col is None:
        col = bpy.data.collections.new('MCenv • Environment')
        col['mcenv_owner'] = token
        col['mcenv_scene'] = scene
        scene.collection.children.link(col)
    return col


def object_for(scene, role, kind='MESH'):
    obj = owned(scene, role)
    if obj:
        return obj
    data = bpy.data.lights.new('MCenv '+role, 'SUN') if kind == 'SUN' else bpy.data.meshes.new('MCenv '+role)
    obj = bpy.data.objects.new('MCenv • '+role, data)
    obj['mcenv_owner'] = owner(scene)
    obj['mcenv_role'] = role
    collection(scene).objects.link(obj)
    obj.hide_select = True
    return obj


def material(scene, role):
    name = 'MCenv '+scene.mc_env.owner_id+' '+role
    m = bpy.data.materials.get(name)
    if not m:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    return m


def node(tree, kind, name, **attrs):
    n = tree.nodes.new(kind)
    n.name = name
    n.label = name
    for k,v in attrs.items():
        setattr(n,k,v)
    return n


def link(t, a, out, b, inp):
    t.links.new(a.outputs[out], b.inputs[inp])


def math_node(t, name, op, a=None, b=None):
    n=node(t, 'ShaderNodeMath', name, operation=op)
    if a is not None: n.inputs[0].default_value=a
    if b is not None: n.inputs[1].default_value=b
    return n


def biome_color(p, kind):
    if p.biome == 'CUSTOM':
        return tuple(getattr(p, kind.lower()+'_color'))
    b=BIOMES.get(p.biome, BIOMES['PLAINS'])
    if kind == 'WATER': return rgb(b[3])
    # Only spruce and birch keep fixed Java tints. Mangrove's #92c648
    # inventory tint is not its placed-block biome tint.
    if kind == 'SPRUCE': return rgb('619961')
    if kind == 'BIRCH': return rgb('80a755')
    grass = kind == 'GRASS'
    dry = kind == 'DRY_FOLIAGE'
    image = p.dry_foliage_colormap if dry else p.grass_colormap if grass else p.foliage_colormap
    # Dry foliage has its own overrides, not the green foliage overrides.
    hardcoded = p.biome in ({'SWAMP','MANGROVE','BADLANDS','DARK_FOREST','PALE_GARDEN','DAPPLED_FOREST'} if dry else
                           {'SWAMP','MANGROVE','BADLANDS','CHERRY_GROVE','PALE_GARDEN','DAPPLED_FOREST'})
    if image and image.has_data and image.channels >= 3 and not hardcoded:
        temp,rain = CLIMATE.get(p.biome, (.8,.4))
        temp=max(0,min(1,temp)); rain=max(0,min(1,rain))*temp
        x=int((1-temp)*255); y=int((1-rain)*255)
        width,height=image.size[:]
        ix=min(width-1,int(x*width/256))
        # Minecraft colormap coordinates are top-left; Blender pixels bottom-left.
        iy=height-1-min(height-1,int(y*height/256))
        k=(iy*width+ix)*image.channels
        c=tuple(image.pixels[k+i] for i in range(3))
        if not image.is_float and image.colorspace_settings.name == 'sRGB':
            c=tuple(linear(v) for v in c)
        if grass and p.biome == 'DARK_FOREST':
            # Java dark forest: (sampled sRGB grass + 0x28340a) / 2.
            def srgb(v): return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055
            c=tuple(linear((srgb(v)+int('28340a'[i*2:i*2+2],16)/255)/2) for i,v in enumerate(c))
        return c
    if dry: return rgb(DRY_FOLIAGE.get(p.biome, 'a37546'))
    return rgb(b[1] if grass else b[2])


def ground_kind(p):
    if not p.ground_follow_biome: return 'GRASS'
    if p.biome in {'DESERT','BEACH','BADLANDS'}: return 'SAND'
    if p.biome in {'SNOWY','SNOWY_TAIGA','SNOWY_SLOPES','SNOWY_BEACH','GROVE','FROZEN_PEAKS','JAGGED_PEAKS'}: return 'SNOW'
    if p.biome in {'OCEAN','WARM_OCEAN','LUKEWARM_OCEAN','COLD_OCEAN','FROZEN_OCEAN','RIVER','FROZEN_RIVER'}: return 'WATER'
    if p.biome in {'STONY_SHORE','STONY_PEAKS'}: return 'STONE'
    return 'GRASS'


def biome_sky(p):
    if p.biome == 'PALE_GARDEN': return rgb('b9b9b9')
    temp=CLIMATE.get(p.biome, (.8,.4))[0]
    t=max(-1,min(1,temp/3))
    return tuple(linear(v) for v in colorsys.hsv_to_rgb(.6222222-t*.05,.5+t*.1,1))


def world_setup(scene):
    p=scene.mc_env
    name='MCenv '+p.owner_id+' World'
    w=bpy.data.worlds.get(name)
    if w is None:
        w=bpy.data.worlds.new(name)
        w.use_nodes=True
        t=w.node_tree; t.nodes.clear()
        out=node(t,'ShaderNodeOutputWorld','Output')
        light=node(t,'ShaderNodeLightPath','Ray type')
        ambient=node(t,'ShaderNodeBackground','Ambient')
        sky=node(t,'ShaderNodeBackground','Visible sky')
        choose=node(t,'ShaderNodeMixShader','Camera sky / ambient')
        link(t,light,'Is Camera Ray',choose,0)
        link(t,ambient,0,choose,1); link(t,sky,0,choose,2); link(t,choose,0,out,'Surface')
        coords=node(t,'ShaderNodeTexCoord','Coordinates')
        rot=node(t,'ShaderNodeVectorRotate','Rotation',rotation_type='AXIS_ANGLE')
        rot.inputs['Axis'].default_value=(0,0,1)
        link(t,coords,'Normal',rot,'Vector')
        # Custom images are camera-only, keeping ambient under independent control.
        image=node(t,'ShaderNodeTexImage','Flat image',interpolation='Closest')
        box=node(t,'ShaderNodeTexImage','Box image',projection='BOX',interpolation='Closest')
        link(t,rot,0,box,'Vector')
        env=node(t,'ShaderNodeTexEnvironment','Panorama',interpolation='Linear')
        link(t,rot,0,env,'Vector')
        scale=node(t,'ShaderNodeVectorMath','Image aspect',operation='MULTIPLY')
        scale.inputs[1].default_value=(1,1,1)
        link(t,coords,'Window',scale,0)
        link(t,scale,0,image,'Vector')
    t=w.node_tree
    # Older versions painted stars with Voronoi nodes; real geometry stars replaced them.
    for legacy in ('Stars','Star size','Sky height','Above horizon','Star mask','Star color'):
        n=t.nodes.get(legacy)
        if n: t.nodes.remove(n)
    scene.world=w
    return w


def cube_geometry(mesh, centers, sx=1, sy=1, sz=1, flat=False):
    verts=[]; faces=[]
    for x,y,z in centers:
        i=len(verts)
        if flat:
            verts.extend([(x-sx/2,y-sy/2,z),(x+sx/2,y-sy/2,z),(x+sx/2,y+sy/2,z),(x-sx/2,y+sy/2,z)])
            faces.append(tuple(i+j for j in range(4)))
        else:
            verts.extend([(x+dx*sx/2,y+dy*sy/2,z+dz*sz/2) for dx,dy,dz in
                          [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]])
            faces.extend([tuple(i+j for j in face) for face in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]])
    mesh.clear_geometry()
    mesh.from_pydata(verts,[],faces)
    mesh.update()


def put_mat(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
    elif obj.data.materials[0] != mat:
        obj.data.materials[0]=mat


def emission_mat(scene, role):
    m=material(scene,role); t=m.node_tree
    if not t.nodes.get('Emission'):
        t.nodes.clear()
        out=node(t,'ShaderNodeOutputMaterial','Output')
        em=node(t,'ShaderNodeEmission','Emission')
        trans=node(t,'ShaderNodeBsdfTransparent','Transparent')
        choose=node(t,'ShaderNodeMixShader','Alpha')
        choose.inputs[0].default_value=1
        link(t,trans,0,choose,1); link(t,em,0,choose,2); link(t,choose,0,out,0)
        tex=node(t,'ShaderNodeTexImage','Texture',interpolation='Closest')
        uv=node(t,'ShaderNodeTexCoord','UV')
        link(t,uv,'UV',tex,'Vector')
    return m


def celestial(scene, role, direction, scale, image, tilt):
    """Project a sprite into the World, independent of camera/viewport clipping.

    Like Mine-imator, opaque black-backed sprites are added to the sky; RGBA
    overrides use their alpha. Like MCprep's shader sky, this works without a
    distant mesh and keeps sky artwork separate from scene illumination.
    """
    t=scene.world.node_tree
    prefix=role+' sprite '
    if not t.nodes.get(prefix+'Texture'):
        def n(kind, name, **attrs): return node(t,kind,prefix+name,**attrs)
        def dot(name):
            result=n('ShaderNodeVectorMath',name,operation='DOT_PRODUCT')
            link(t,t.nodes['Coordinates'],'Normal',result,0)
            return result
        forward=dot('Forward'); right=dot('Right'); up=dot('Up')
        # Perspective UVs: (ray dot right/up) / (ray dot forward).
        uv=n('ShaderNodeCombineXYZ','UV')
        for axis,source in [('X',right),('Y',up)]:
            divide=n('ShaderNodeMath',axis+' divide',operation='DIVIDE')
            link(t,source,'Value',divide,0); link(t,forward,'Value',divide,1)
            size=n('ShaderNodeMath',axis+' size',operation='MULTIPLY_ADD')
            size.inputs[2].default_value=.5
            link(t,divide,0,size,0); link(t,size,0,uv,axis)
        texture=n('ShaderNodeTexImage','Texture',interpolation='Closest',extension='CLIP')
        link(t,uv,0,texture,'Vector')
        facing=n('ShaderNodeMath','Facing',operation='GREATER_THAN')
        facing.inputs[1].default_value=0
        link(t,forward,'Value',facing,0)
        opacity=n('ShaderNodeMath','Opacity',operation='MULTIPLY')
        link(t,facing,0,opacity,0)
        alpha=n('ShaderNodeMath','Alpha',operation='MULTIPLY')
        link(t,texture,'Alpha',alpha,0); link(t,opacity,0,alpha,1)
        masked=n('ShaderNodeMixRGB','Masked',blend_type='MULTIPLY')
        masked.inputs[0].default_value=1
        link(t,texture,'Color',masked,1); link(t,alpha,0,masked,2)
        blend=n('ShaderNodeMixRGB','Blend')
        link(t,alpha,0,blend,0); link(t,texture,'Color',blend,2)
    # World Normal points into the scene; negate the outgoing sky direction.
    normal=-direction.normalized()
    rotation=normal.to_track_quat('Z','Y')
    right=rotation @ Vector((1,0,0)); up=rotation @ Vector((0,1,0))
    angle=math.radians(tilt)
    t.nodes[prefix+'Forward'].inputs[1].default_value=normal
    t.nodes[prefix+'Right'].inputs[1].default_value=right*math.cos(angle)+up*math.sin(angle)
    t.nodes[prefix+'Up'].inputs[1].default_value=up*math.cos(angle)-right*math.sin(angle)
    # Full card spans about ten degrees, with the pixel core inside that card.
    for axis in ('X','Y'):
        t.nodes[prefix+axis+' size'].inputs[1].default_value=1/max(.000001,.18*scale)
    t.nodes[prefix+'Texture'].image=image
    visibility=max(0,min(1,(direction.z+.15)/.15))
    t.nodes[prefix+'Opacity'].inputs[1].default_value=visibility if scale>0 and scene.mc_env.sky_mode=='MINECRAFT' else 0
    blend=t.nodes[prefix+'Blend']
    additive=image is not None and bool(image.get('mcenv_additive'))
    blend.blend_type='ADD' if additive else 'MIX'
    if additive:
        for old in list(blend.inputs[0].links): t.links.remove(old)
        blend.inputs[0].default_value=1
        link(t,t.nodes[prefix+'Masked'],0,blend,2)
    else:
        link(t,t.nodes[prefix+'Alpha'],0,blend,0)
        link(t,t.nodes[prefix+'Texture'],'Color',blend,2)
    if role=='Sun':
        source=t.nodes['Visible sky'].inputs['Color']
        # sync() has just restored the selected base background input.
        if source.links: t.links.new(source.links[0].from_socket,blend.inputs[1])
        else:
            for old in list(blend.inputs[1].links): t.links.remove(old)
            blend.inputs[1].default_value=source.default_value[:]
    else:
        link(t,t.nodes['Sun sprite Blend'],0,blend,1)
        link(t,blend,0,t.nodes['Visible sky'],'Color')
    # Only remove obsolete MCenv-owned cards, never user objects.
    old=owned(scene,role)
    if old:
        mesh=old.data
        bpy.data.objects.remove(old,do_unlink=True)
        if mesh.users==0: bpy.data.meshes.remove(mesh)


def stars_setup(scene, night):
    """Real square-star dome over the whole sky; fades in at dusk, out at dawn."""
    p=scene.mc_env; o=object_for(scene,'Stars')
    sig=str((round(p.stars_size,3),p.stars_count,round(p.stars_size_random,3)))
    if o.get('sig') != sig:
        rng=random.Random(20); verts=[]; faces=[]
        # Uniform directions over the full sky above the horizon (both hemispheres).
        for i in range(p.stars_count):
            z=rng.uniform(.03,1); a=rng.uniform(0,math.tau)
            r=math.sqrt(max(0,1-z*z))
            d=Vector((math.cos(a)*r,math.sin(a)*r,z))
            # Exactly one size draw per star keeps positions stable while the
            # random-size slider changes; 0 variation = every star identical.
            s=max(.1,1+p.stars_size_random*(rng.random()*2-1)*.8)*p.stars_size*140
            t1=d.cross(Vector((0,0,1)))
            if t1.length<1e-4: t1=Vector((1,0,0))
            t1.normalize(); t2=t1.cross(d).normalized()
            c=d*900
            for dx,dy in [(-1,-1),(1,-1),(1,1),(-1,1)]:
                verts.append(tuple(c+t1*(s*.5*dx)+t2*(s*.5*dy)))
            i0=len(verts)-4; faces.append((i0,i0+1,i0+2,i0+3))
        o.data.clear_geometry(); o.data.from_pydata(verts,[],faces); o.data.update()
        o['sig']=sig
    o.location=scene.camera.matrix_world.translation if scene.camera else Vector((0,0,0))
    o.rotation_euler=(0,0,math.radians(p.rotation))
    o.hide_render=p.sky_mode!='MINECRAFT'; o.hide_viewport=o.hide_render
    m=emission_mat(scene,'Stars'); put_mat(o,m); t=m.node_tree
    em=t.nodes['Emission']
    em.inputs[0].default_value=rgba(p.night_stars); em.inputs[1].default_value=p.stars_strength
    t.nodes['Alpha'].inputs[0].default_value=night
    m.use_backface_culling=False
    if hasattr(m,'surface_render_method'): m.surface_render_method='DITHERED'


def ground_setup(scene):
    p=scene.mc_env; o=object_for(scene,'Ground')
    if not o.data.vertices:
        cube_geometry(o.data,[(0,0,0)],1,1,1,True)
        uv=o.data.uv_layers.new(name='UVMap')
        for poly in o.data.polygons:
            for li,co in zip(poly.loop_indices,[(0,0),(1,0),(1,1),(0,1)]): uv.data[li].uv=co
    o.location=(0,0,-.02); o.scale=(1024,1024,1)
    o.hide_render=not p.ground; o.hide_viewport=not p.ground
    m=material(scene,'Ground'); put_mat(o,m); t=m.node_tree
    if not t.nodes.get('Ground texture'):
        t.nodes.clear()
        out=node(t,'ShaderNodeOutputMaterial','Output')
        bs=node(t,'ShaderNodeBsdfPrincipled','Surface'); link(t,bs,0,out,0)
        coord=node(t,'ShaderNodeTexCoord','Coordinates')
        tiling=node(t,'ShaderNodeVectorMath','Tiling',operation='SCALE')
        tiling.inputs['Scale'].default_value=1024
        link(t,coord,'UV',tiling,0)
        tex=node(t,'ShaderNodeTexImage','Ground texture',interpolation='Closest',extension='REPEAT')
        link(t,tiling,0,tex,'Vector')
        tint=node(t,'ShaderNodeMixRGB','Biome tint',blend_type='MULTIPLY')
        tint.inputs[0].default_value=1
        link(t,tex,'Color',tint,1); link(t,tint,0,bs,'Base Color')
    image=p.ground_image or assets.bundled_image('block/main/grass_block_top.png')
    t.nodes['Ground texture'].image=image
    kind=ground_kind(p)
    color=biome_color(p,'GRASS') if kind=='GRASS' else biome_color(p,'WATER') if kind=='WATER' else rgb({'SAND':'dbc998','STONE':'858585','SNOW':'edf4ff'}[kind])
    tint=(1,1,1)
    if p.ground_follow_biome:
        from .biome_materials import image_baseline
        signature=str((image.as_pointer(),tuple(image.size),image.colorspace_settings.name,kind))
        if m.get('mcenv_ground_image') != signature:
            m['mcenv_ground_baseline']=image_baseline(image,kind=='GRASS')[0]
            m['mcenv_ground_image']=signature
        baseline=m.get('mcenv_ground_baseline',(1,1,1))
        tint=tuple(color[i]/max(.04,baseline[i]) for i in range(3))
    elif image.get('mcenv_asset')=='block/main/grass_block_top.png':
        # The bundled top is grayscale; use a fixed plains tint until following.
        tint=rgb('91bd59')
    t.nodes['Biome tint'].inputs[2].default_value=rgba(tint)
    bs=t.nodes['Surface']
    bs.inputs['Roughness'].default_value=.14 if kind=='WATER' else .85
    bs.inputs['IOR'].default_value=1.333 if kind=='WATER' else 1.45
    transmission=bs.inputs.get('Transmission Weight') or bs.inputs.get('Transmission')
    if transmission: transmission.default_value=.35 if kind=='WATER' else 0


def cloud_material(scene, faded):
    # Solid clouds get a pure emission shader. Keeping a Transparent BSDF in
    # the tree would route the whole cloud sheet through EEVEE's transparent
    # pipeline even at full opacity, which can hide geometry behind the empty
    # parts of the field (stars). Faded clouds keep the transparency mix.
    m=material(scene,'Clouds'); t=m.node_tree
    want='FADED' if faded else 'SOLID'
    if t.nodes.get('Emission') is None or m.get('mcenv_cloud_tree') != want:
        t.nodes.clear()
        out=node(t,'ShaderNodeOutputMaterial','Output')
        em=node(t,'ShaderNodeEmission','Emission')
        if faded:
            trans=node(t,'ShaderNodeBsdfTransparent','Transparent')
            choose=node(t,'ShaderNodeMixShader','Alpha')
            choose.inputs[0].default_value=.5
            link(t,trans,0,choose,1); link(t,em,0,choose,2); link(t,choose,0,out,0)
        else:
            link(t,em,0,out,0)
        m['mcenv_cloud_tree']=want
    return m


def clouds_setup(scene, seconds, c):
    p=scene.mc_env; o=object_for(scene,'Clouds')
    sig=str(('v2',p.cloud_mode,p.cloud_size,p.cloud_blocks,p.cloud_thickness,p.cloud_coverage,p.cloud_seed,p.cloud_image.name if p.cloud_image else '',p.cloud_image.size[:] if p.cloud_image else ''))
    if o.get('signature') != sig:
        rng=random.Random(p.cloud_seed); centers=[]
        # Size adds one random block column on every side per step; Scale
        # keeps fixing the block size, so the field physically grows.
        n=32+2*p.cloud_blocks; cell=p.cloud_size/32
        pixels=p.cloud_image.pixels if p.cloud_image and p.cloud_image.has_data else None
        iw,ih=p.cloud_image.size[:] if pixels else (0,0)
        # Sample a small low-frequency field for connected pixel clouds.
        side=max(10,int((n-1)/4)+2)
        field=[[rng.random() for _ in range(side)] for _ in range(side)]
        for y in range(n):
            for x in range(n):
                if pixels:
                    ix=min(iw-1,int(x/n*iw)); iy=min(ih-1,int(y/n*ih)); k=(iy*iw+ix)*4
                    keep=sum(pixels[k:k+3])/3*pixels[k+3]>.5
                else:
                    fx=x/4; fy=y/4; ix=int(fx); iy=int(fy); u=fx-ix; v=fy-iy
                    val=field[iy][ix]*(1-u)*(1-v)+field[iy][ix+1]*u*(1-v)+field[iy+1][ix]*(1-u)*v+field[iy+1][ix+1]*u*v
                    keep=val>1-p.cloud_coverage
                if keep: centers.append(((x-n/2+.5)*cell,(y-n/2+.5)*cell,0))
        cube_geometry(o.data,centers,cell,cell,max(.001,p.cloud_thickness),p.cloud_mode=='FLAT' or p.cloud_thickness==0)
        o['signature']=sig
    o.location=(p.cloud_offset+seconds*p.cloud_speed,0,p.cloud_height)
    o.hide_render=not p.clouds; o.hide_viewport=not p.clouds
    m=cloud_material(scene,p.cloud_mode=='FADED'); put_mat(o,m)
    m.node_tree.nodes['Emission'].inputs[0].default_value=rgba(c)
    if hasattr(m,'surface_render_method'): m.surface_render_method='DITHERED'
    m.use_backface_culling=False


def fog_setup(scene, sky):
    p=scene.mc_env; o=object_for(scene,'Fog')
    if not o.data.vertices: cube_geometry(o.data,[(0,0,0)])
    span=2048
    o.location=(0,0,p.fog_height/2); o.scale=(span,span,p.fog_height)
    o.hide_render=not p.fog; o.hide_viewport=not p.fog; o.display_type='WIRE'
    m=material(scene,'Fog'); put_mat(o,m); t=m.node_tree
    if not t.nodes.get('Volume'):
        t.nodes.clear()
        out=node(t,'ShaderNodeOutputMaterial','Output')
        vol=node(t,'ShaderNodeVolumePrincipled','Volume'); link(t,vol,0,out,'Volume')
        dist=node(t,'ShaderNodeVectorMath','Camera distance',operation='DISTANCE')
        # Geometry Position is world space, unlike object/generated coordinates.
        pos=node(t,'ShaderNodeNewGeometry','World position'); link(t,pos,'Position',dist,0)
        subtract=math_node(t,'Start','SUBTRACT'); link(t,dist,'Value',subtract,0)
        divide=math_node(t,'Falloff','DIVIDE'); divide.use_clamp=True; link(t,subtract,0,divide,0)
        density=math_node(t,'Density','MULTIPLY'); link(t,divide,0,density,0); link(t,density,0,vol,'Density')
    cam=scene.camera.matrix_world.translation if scene.camera else Vector((0,0,0))
    t.nodes['Camera distance'].inputs[1].default_value=cam
    t.nodes['Start'].inputs[1].default_value=p.fog_distance
    t.nodes['Falloff'].inputs[1].default_value=p.fog_size
    t.nodes['Density'].inputs[1].default_value=3/p.fog_size
    t.nodes['Volume'].inputs['Color'].default_value=rgba(p.fog_object_color if p.fog_custom_object else sky)


def sync(scene):
    if not hasattr(scene,'mc_env') or not scene.mc_env.enabled: return
    ptr=scene.as_pointer()
    if ptr in _BUSY: return
    _BUSY.add(ptr)
    try:
        p=scene.mc_env; owner(scene)
        migrate_named_data(scene)
        sec=(scene.frame_current-scene.frame_start)/(scene.render.fps/scene.render.fps_base)
        hour=(p.time+((scene.frame_current-scene.frame_start)*24/p.cycle_frames if p.preview_day_cycle else 0))%24
        elevation=math.sin((hour-6)*math.tau/24)
        daylight=max(0,min(1,(elevation+.12)/.42)); night=1-daylight
        twilight=max(0,1-abs(elevation)/.28)*int(p.twilight)
        # Stars start appearing shortly after sunset and vanish near sunrise.
        star_night=max(0,min(1,(.05-elevation)/.25))
        sky=mix(p.night_sky,biome_sky(p) if p.biome_atmosphere and p.biome!='CUSTOM' else p.day_sky,daylight)
        sky=mix(sky,rgb('f6a16a'),twilight*.5)
        if p.fog and p.fog_sky: sky=mix(sky,p.fog_color if p.fog_custom else sky,.35)
        w=world_setup(scene); t=w.node_tree
        ambient=t.nodes['Ambient']; ambient.inputs[0].default_value=rgba(mix(p.night_ambient,p.day_ambient,daylight)); ambient.inputs[1].default_value=p.ambient_strength
        t.nodes['Rotation'].inputs['Angle'].default_value=math.radians(p.rotation+p.background_rotation)
        visible=t.nodes['Visible sky']
        desired=None
        if p.sky_mode=='CUSTOM' and p.background_image:
            name={'IMAGE':'Flat image','BOX':'Box image','EQUIRECTANGULAR':'Panorama'}[p.background_type]
            desired=t.nodes[name]; desired.image=p.background_image
            aspect=1
            if p.background_type=='IMAGE' and not p.background_stretch:
                iw,ih=p.background_image.size[:]
                aspect=(scene.render.resolution_x/scene.render.resolution_y)/(iw/max(1,ih))
            t.nodes['Image aspect'].inputs[1].default_value=(aspect,1,1)
        for l in list(visible.inputs['Color'].links): t.links.remove(l)
        if desired is not None: link(t,desired,'Color',visible,'Color')
        else: visible.inputs['Color'].default_value=rgba(sky)
        a=(hour-6)*math.tau/24; heading=math.radians(p.rotation)
        direction=Vector((math.cos(a)*math.cos(heading),math.cos(a)*math.sin(heading),math.sin(a)))
        for role,d,energy,c in [('Sunlight',direction,p.sun_strength*daylight,mix(p.day_sunlight,rgb('ffad66'),twilight*.65)),('Moonlight',-direction,p.night_strength*night,rgb('a9c2ff'))]:
            o=object_for(scene,role,'SUN'); o.rotation_euler=(-d).to_track_quat('-Z','Y').to_euler()
            o.data.energy=energy; o.data.color=c; o.data.angle=math.radians(p.sun_angle)
        celestial(scene,'Sun',direction,p.sun_scale,assets.sun_image(p),p.sun_tilt)
        celestial(scene,'Moon',-direction,p.moon_scale,assets.moon_image(p),p.moon_tilt)
        stars_setup(scene,star_night)
        ground_setup(scene)
        clouds_setup(scene,sec,mix(p.night_clouds,p.day_clouds,daylight))
        fog_setup(scene,sky)
        update_bound(scene,sec)
        _ERRORS.pop(ptr,None)
    except Exception as exc:
        _ERRORS[ptr]=str(exc)
        print('MCenv update error:',repr(exc))
    finally: _BUSY.discard(ptr)


def update_bound(scene, seconds):
    p=scene.mc_env
    from .biome_materials import refresh
    seen_materials=set()
    for obj in scene.objects:
        for mod in obj.modifiers:
            if mod.type=='NODES' and mod.get('mcenv_wind') and mod.node_group:
                t=mod.node_group
                t.nodes['Time'].outputs[0].default_value=seconds*p.wind_speed
                t.nodes['Amplitude'].outputs[0].default_value=p.wind_strength if p.wind else 0
                t.nodes['Direction'].outputs[0].default_value=math.radians(p.wind_direction)
                t.nodes['Gust speed'].outputs[0].default_value=p.wind_directional_speed
                t.nodes['Gust strength'].outputs[0].default_value=p.wind_directional_strength
        for slot in obj.material_slots:
            m=slot.material
            if not m or not m.use_nodes: continue
            if m.as_pointer() in seen_materials: continue
            seen_materials.add(m.as_pointer())
            # Never update another scene's bound copy when objects are shared.
            if m.get('mcenv_biome_owner') not in (None,p.owner_id): continue
            refresh(m,p)
            t=m.node_tree
            for n in t.nodes:
                if n.get('mcenv_atlas'):
                    rows=n['mcenv_atlas']; n.inputs[1].default_value=(0,(rows-1-int(seconds*p.texture_fps)%rows)/rows,0)


def build_wind(obj):
    existing=next((m for m in obj.modifiers if m.get('mcenv_wind')),None)
    if existing: return
    group=obj.vertex_groups.get('MCENV_Wind') or obj.vertex_groups.new(name='MCENV_Wind')
    zs=[v.co.z for v in obj.data.vertices]
    lo=min(zs,default=0); span=max(zs,default=1)-lo
    for v in obj.data.vertices: group.add([v.index],max(0,min(1,(v.co.z-lo)/max(.001,span))), 'REPLACE')
    t=bpy.data.node_groups.new('MCenv Wind • '+obj.name,'GeometryNodeTree')
    t.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    t.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    inp=node(t,'NodeGroupInput','Input'); out=node(t,'NodeGroupOutput','Output')
    pos=node(t,'GeometryNodeInputPosition','Position'); sep=node(t,'ShaderNodeSeparateXYZ','XYZ'); link(t,pos,0,sep,0)
    attr=node(t,'GeometryNodeInputNamedAttribute','Weight',data_type='FLOAT'); attr.inputs['Name'].default_value='MCENV_Wind'
    for name in ['Time','Amplitude','Direction','Gust speed','Gust strength']: node(t,'ShaderNodeValue',name)
    phase=math_node(t,'Phase','ADD'); link(t,sep,'Z',phase,0); link(t,t.nodes['Time'],0,phase,1)
    wave=math_node(t,'Wave','SINE'); link(t,phase,0,wave,0)
    gusttime=math_node(t,'Gust time','MULTIPLY'); link(t,t.nodes['Time'],0,gusttime,0); link(t,t.nodes['Gust speed'],0,gusttime,1)
    gustsin=math_node(t,'Gust sine','SINE'); link(t,gusttime,0,gustsin,0)
    gustamp=math_node(t,'Gust amplitude','MULTIPLY'); link(t,gustsin,0,gustamp,0); link(t,t.nodes['Gust strength'],0,gustamp,1)
    add=math_node(t,'Combined','ADD'); link(t,wave,0,add,0); link(t,gustamp,0,add,1)
    amp=math_node(t,'Scaled','MULTIPLY'); link(t,add,0,amp,0); link(t,t.nodes['Amplitude'],0,amp,1)
    weighted=math_node(t,'Weighted','MULTIPLY'); link(t,amp,0,weighted,0); link(t,attr,'Attribute',weighted,1)
    cos=math_node(t,'Heading X','COSINE'); sin=math_node(t,'Heading Y','SINE')
    for n in [cos,sin]: link(t,t.nodes['Direction'],0,n,0)
    x=math_node(t,'Offset X','MULTIPLY'); y=math_node(t,'Offset Y','MULTIPLY')
    for n,trig in [(x,cos),(y,sin)]: link(t,trig,0,n,0); link(t,weighted,0,n,1)
    vec=node(t,'ShaderNodeCombineXYZ','Offset'); link(t,x,0,vec,'X'); link(t,y,0,vec,'Y')
    setpos=node(t,'GeometryNodeSetPosition','Sway'); link(t,inp,'Geometry',setpos,'Geometry'); link(t,vec,0,setpos,'Offset'); link(t,setpos,'Geometry',out,'Geometry')
    mod=obj.modifiers.new('MCenv Wind','NODES'); mod.node_group=t; mod['mcenv_wind']=True


@persistent
def frame_update(scene, *args):
    sync(scene)


@persistent
def load_update(*args):
    for scene in bpy.data.scenes: sync(scene)


def register():
    if frame_update not in bpy.app.handlers.frame_change_post: bpy.app.handlers.frame_change_post.append(frame_update)
    if load_update not in bpy.app.handlers.load_post: bpy.app.handlers.load_post.append(load_update)


def unregister():
    for items,func in [(bpy.app.handlers.frame_change_post,frame_update),(bpy.app.handlers.load_post,load_update)]:
        if func in items: items.remove(func)
    _BUSY.clear(); _ERRORS.clear()
