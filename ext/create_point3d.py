import bpy
import bmesh
from .read_write_model import Point3D
import mathutils
import os
from pathlib import Path
import math
import numpy as np


def create_point3d_from_mesh(mesh_obj):

    bpy.context.view_layer.objects.active = mesh_obj
    bpy.ops.object.mode_set(mode='OBJECT')
    
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = mesh_obj.evaluated_get(depsgraph)
    
    point3ds = []
    # f.write("# 3D point list with one line of data per point:\n")
    # f.write("# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[] as (IMAGE_ID, POINT2D_IDX)\n")
        
    if 'position' in eval_obj.data.attributes:
        position_attr = eval_obj.data.attributes['position'].data
        colour_attr = None
        for attr in eval_obj.data.attributes:
            if attr.data_type == 'FLOAT_COLOR':
                colour_attr = attr.data
                break
        
        for i, pos_data in enumerate(position_attr, 1):
            local_pos = pos_data.vector
            world_co = mesh_obj.matrix_world @ local_pos
            x, y, z = world_co.x, world_co.y, world_co.z
            
            if colour_attr and i-1 < len(colour_attr):
                colour = colour_attr[i-1].color
                r, g, b = int(colour[0] * 255), int(colour[1] * 255), int(colour[2] * 255)
            else:
                r, g, b = 128, 128, 128

            p3d = Point3D(
                    id=i,
                    xyz=np.array([x, y, z]),
                    rgb=np.array([r, g, b]),
                    error=0,
                    image_ids=np.array([]),
                    point2D_idxs=np.array([]),
            )
            point3ds.append(p3d)
    else:
        print("No 'position' attribute found in geometry data!")
    
    eval_obj.to_mesh_clear()

    return point3ds

