# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-owned data only. No network, external assets, eval or third-party packages."""
import math
import uuid
import random
import bpy
from mathutils import Vector
from bpy.app.handlers import persistent
from .properties import BIOMES, rgb

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
    b=BIOMES[p.biome]
    if kind == 'WATER': return rgb(b[3])
    if kind == 'GRASS': return rgb(b[1])
    if kind == 'SPRUCE': return rgb('619961')
    if kind == 'BIRCH': return rgb('80a755')
    return rgb(b[2])


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
        vor=node(t,'ShaderNodeTexVoronoi','Stars',distance='EUCLIDEAN')
        vor.inputs['Scale'].default_value=140
        link(t,rot,'Vector',vor,'Vector')
        threshold=math_node(t,'Star size','LESS_THAN',b=.045)
        link(t,vor,'Distance',threshold,0)
        sep=node(t,'ShaderNodeSeparateXYZ','Sky height')
        link(t,coords,'Normal',sep,0)
        above=math_node(t,'Above horizon','GREATER_THAN',b=.02)
        link(t,sep,'Z',above,0)
        mask=math_node(t,'Star mask','MULTIPLY')
        link(t,above,0,mask,0); link(t,threshold,0,mask,1)
        stars=node(t,'ShaderNodeMixRGB','Star color',blend_type='MIX')
        link(t,mask,0,stars,0)
        link(t,stars,0,sky,'Color')
        # Custom images are camera-only, keeping ambient under independent control.
        image=node(t,'ShaderNodeTexImage','Flat image',interpolation='Closest')
        link(t,coords,'Window',image,'Vector')
        box=node(t,'ShaderNodeTexImage','Box image',projection='BOX',interpolation='Closest')
        link(t,rot,0,box,'Vector')
        env=node(t,'ShaderNodeTexEnvironment','Panorama',interpolation='Linear')
        link(t,rot,0,env,'Vector')
        scale=node(t,'ShaderNodeVectorMath','Image aspect',operation='MULTIPLY')
        scale.inputs[1].default_value=(1,1,1)
        link(t,coords,'Window',scale,0)
        link(t,scale,0,image,'Vector')
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


def moon_image(scene):
    p=scene.mc_env
    name='MCenv '+p.owner_id+' Moon phase'
    im=bpy.data.images.get(name)
    if im is None: im=bpy.data.images.new(name,32,32,alpha=True)
    if im.get('phase') != p.moon_phase:
        phase=int(p.moon_phase); pixels=[]
        for y in range(32):
            for x in range(32):
                u=(x+.5)/16-1; v=(y+.5)/16-1
                # Pixelated circular lunar disk with a geometric terminator.
                radius=math.sqrt(max(0,1-v*v))
                light=(u*u+v*v<.92 and (u <= math.cos(phase*math.pi/4)*radius if phase<=4 else u >= -math.cos(phase*math.pi/4)*radius))
                val=.8 if ((x//4+y//4)%3) else .57
                pixels.extend((val,val,val,1 if light else 0))
        im.pixels.foreach_set(pixels); im.update(); im['phase']=p.moon_phase
    return im


def celestial(scene, role, direction, scale, tint, image, tilt):
    o=object_for(scene,role)
    if not o.data.vertices:
        cube_geometry(o.data,[(0,0,0)],1,1,1,True)
        uv=o.data.uv_layers.new(name='UVMap')
        for poly in o.data.polygons:
            for li,co in zip(poly.loop_indices,[(0,0),(1,0),(1,1),(0,1)]): uv.data[li].uv=co
    center=scene.camera.matrix_world.translation if scene.camera else Vector((0,0,0))
    o.location=center+direction*900
    o.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    o.rotation_euler.rotate_axis('Z',math.radians(tilt))
    o.scale=(36*scale,36*scale,36*scale)
    o.hide_render=scale <= 0 or scene.mc_env.sky_mode != 'MINECRAFT'
    o.hide_viewport=o.hide_render
    if hasattr(o,'visible_shadow'): o.visible_shadow=False
    m=emission_mat(scene,role); put_mat(o,m); t=m.node_tree
    em=t.nodes['Emission']; em.inputs[0].default_value=rgba(tint); em.inputs[1].default_value=1
    tex=t.nodes['Texture']; tex.image=image
    alpha=t.nodes['Alpha']
    for socket in (em.inputs[0],alpha.inputs[0]):
        for l in list(socket.links): t.links.remove(l)
    alpha.inputs[0].default_value=1
    if image:
        link(t,tex,'Color',em,0); link(t,tex,'Alpha',alpha,0)


def ground_setup(scene):
    p=scene.mc_env; o=object_for(scene,'Ground')
    if not o.data.vertices:
        cube_geometry(o.data,[(0,0,0)],1,1,1,True)
        uv=o.data.uv_layers.new(name='UVMap')
        for poly in o.data.polygons:
            for li,co in zip(poly.loop_indices,[(0,0),(1,0),(1,1),(0,1)]): uv.data[li].uv=co
    o.location=(0,0,p.ground_height); o.scale=(p.ground_size,p.ground_size,1)
    o.hide_render=not p.ground; o.hide_viewport=not p.ground
    m=material(scene,'Ground'); put_mat(o,m); t=m.node_tree
    if not t.nodes.get('Surface'):
        t.nodes.clear()
        out=node(t,'ShaderNodeOutputMaterial','Output')
        bs=node(t,'ShaderNodeBsdfPrincipled','Surface'); link(t,bs,0,out,0)
        bs.inputs['Roughness'].default_value=.85
        coord=node(t,'ShaderNodeTexCoord','Coordinates')
        scale=node(t,'ShaderNodeVectorMath','Tiling',operation='SCALE')
        link(t,coord,'Generated',scale,0)
        noise=node(t,'ShaderNodeTexNoise','Pixels'); noise.inputs['Scale'].default_value=16; noise.inputs['Detail'].default_value=0
        # Quantize coordinates before noise for blocky original texture.
        snap=node(t,'ShaderNodeVectorMath','Pixel grid',operation='SNAP'); snap.inputs[1].default_value=(1/16,1/16,1/16)
        link(t,scale,0,snap,0); link(t,snap,0,noise,0)
        tint=node(t,'ShaderNodeMixRGB','Tint',blend_type='MULTIPLY'); tint.inputs[0].default_value=.3
        link(t,noise,'Fac',tint,2); link(t,tint,0,bs,'Base Color')
        for name in ('Albedo','Normal','Roughness'):
            im=node(t,'ShaderNodeTexImage',name,interpolation='Closest',extension='REPEAT'); link(t,scale,0,im,0)
        normal=node(t,'ShaderNodeNormalMap','Normal map'); link(t,t.nodes['Normal'],'Color',normal,'Color')
        albedo_tint=node(t,'ShaderNodeMixRGB','Image biome tint',blend_type='MULTIPLY')
        albedo_tint.inputs[0].default_value=1
        link(t,t.nodes['Albedo'],'Color',albedo_tint,1)
    t.nodes['Tiling'].inputs['Scale'].default_value=p.ground_size/p.ground_tile
    c=biome_color(p,'GRASS') if p.ground_type=='GRASS' else biome_color(p,'WATER') if p.ground_type=='WATER' else rgb({'DIRT':'846044','SAND':'dbc998','STONE':'858585','SNOW':'edf4ff'}[p.ground_type])
    t.nodes['Tint'].inputs[1].default_value=rgba(c)
    t.nodes['Image biome tint'].inputs[2].default_value=rgba(c if p.ground_type in {'GRASS','WATER'} else (1,1,1))
    bs=t.nodes['Surface']
    bs.inputs['Roughness'].default_value=.14 if p.ground_type=='WATER' else .85
    for name,img,socket,source in [('Albedo',p.ground_image,'Base Color','Color'),('Roughness',p.ground_material,'Roughness','Color'),('Normal',p.ground_normal,'Normal','Normal')]:
        tex=t.nodes[name]; tex.image=img
        for l in list(bs.inputs[socket].links): t.links.remove(l)
        if img:
            if name=='Albedo': link(t,t.nodes['Image biome tint'],0,bs,socket)
            else: link(t,t.nodes['Normal map'] if name=='Normal' else tex,source,bs,socket)
        elif name=='Albedo': link(t,t.nodes['Tint'],0,bs,socket)


def clouds_setup(scene, seconds, c):
    p=scene.mc_env; o=object_for(scene,'Clouds')
    sig=str((p.cloud_mode,p.cloud_size,p.cloud_thickness,p.cloud_coverage,p.cloud_seed,p.cloud_image.name if p.cloud_image else '',p.cloud_image.size[:] if p.cloud_image else ''))
    if o.get('signature') != sig:
        rng=random.Random(p.cloud_seed); centers=[]; n=32; cell=p.cloud_size/n
        pixels=p.cloud_image.pixels if p.cloud_image and p.cloud_image.has_data else None
        iw,ih=p.cloud_image.size[:] if pixels else (0,0)
        # Sample a small low-frequency field for connected pixel clouds.
        field=[[rng.random() for _ in range(10)] for _ in range(10)]
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
    m=emission_mat(scene,'Clouds'); put_mat(o,m)
    m.node_tree.nodes['Emission'].inputs[0].default_value=rgba(c)
    m.node_tree.nodes['Alpha'].inputs[0].default_value=.5 if p.cloud_mode=='FADED' else 1
    if hasattr(m,'surface_render_method'): m.surface_render_method='DITHERED'


def fog_setup(scene, sky):
    p=scene.mc_env; o=object_for(scene,'Fog')
    if not o.data.vertices: cube_geometry(o.data,[(0,0,0)])
    span=max(p.ground_size,2048)
    o.location=(0,0,p.fog_height/2); o.scale=(span,span,p.fog_height)
    o.hide_render=not p.fog; o.hide_viewport=not p.fog; o.display_type='WIRE'
    m=material(scene,'Fog'); put_mat(o,m); t=m.node_tree
    if not t.nodes.get('Volume'):
        t.nodes.clear()
        out=node(t,'ShaderNodeOutputMaterial','Output')
        vol=node(t,'ShaderNodeVolumePrincipled','Volume'); link(t,vol,0,out,'Volume')
        geo=node(t,'ShaderNodeTexCoord','Coordinates')
        dist=node(t,'ShaderNodeVectorMath','Camera distance',operation='DISTANCE')
        link(t,geo,'Position' if 'Position' in geo.outputs else 'Object',dist,0)
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
        sky=mix(p.night_sky,p.day_sky,daylight)
        sky=mix(sky,rgb('f6a16a'),twilight*.5)
        if p.fog and p.fog_sky: sky=mix(sky,p.fog_color if p.fog_custom else sky,.35)
        w=world_setup(scene); t=w.node_tree
        ambient=t.nodes['Ambient']; ambient.inputs[0].default_value=rgba(mix(p.night_ambient,p.day_ambient,daylight)); ambient.inputs[1].default_value=p.ambient_strength
        t.nodes['Rotation'].inputs['Angle'].default_value=math.radians(p.rotation+p.background_rotation)
        t.nodes['Star size'].inputs[1].default_value=p.stars_size
        stars=t.nodes['Star color']; stars.inputs[1].default_value=rgba(sky)
        stars.inputs[2].default_value=rgba(mix(sky,tuple(v*p.stars_strength for v in p.night_stars),night))
        visible=t.nodes['Visible sky']; desired=stars
        if p.sky_mode=='CUSTOM' and p.background_image:
            name={'IMAGE':'Flat image','BOX':'Box image','EQUIRECTANGULAR':'Panorama'}[p.background_type]
            desired=t.nodes[name]; desired.image=p.background_image
            aspect=1
            if p.background_type=='IMAGE' and not p.background_stretch:
                iw,ih=p.background_image.size[:]
                aspect=(scene.render.resolution_x/scene.render.resolution_y)/(iw/max(1,ih))
            t.nodes['Image aspect'].inputs[1].default_value=(aspect,1,1)
        if not visible.inputs['Color'].links or visible.inputs['Color'].links[0].from_node != desired:
            link(t,desired,'Color' if desired!=stars else 0,visible,'Color')
        a=(hour-6)*math.tau/24; heading=math.radians(p.rotation)
        direction=Vector((math.cos(a)*math.cos(heading),math.cos(a)*math.sin(heading),math.sin(a)))
        for role,d,energy,c in [('Sunlight',direction,p.sun_strength*daylight,mix(p.day_sunlight,rgb('ffad66'),twilight*.65)),('Moonlight',-direction,p.night_strength*night,rgb('a9c2ff'))]:
            o=object_for(scene,role,'SUN'); o.rotation_euler=(-d).to_track_quat('-Z','Y').to_euler()
            o.data.energy=energy; o.data.color=c; o.data.angle=math.radians(p.sun_angle)
        celestial(scene,'Sun',direction,p.sun_scale,p.day_sunlight,p.sun_image,p.sun_tilt)
        celestial(scene,'Moon',-direction,p.moon_scale,rgb('dce7ff'),p.moon_image or moon_image(scene),p.moon_tilt)
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
            t=m.node_tree
            for n in t.nodes:
                if n.get('mcenv_tint'): n.inputs[2].default_value=rgba(biome_color(p,n['mcenv_tint']))
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
