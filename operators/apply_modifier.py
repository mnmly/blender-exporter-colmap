from .. utils.create_pc_generation_geometrynode import create_geometry_node_setup
from bpy.types import Operator

class COLMAP_PREP_OT_apply_modifier(Operator):
    """Apply Point Cloud Generation modifier to selected planes"""
    bl_idname = "colmap_prep.apply_modifier"
    bl_label = "Apply Point Cloud Modifier"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.selected_objects and any(obj.type == 'MESH' for obj in context.selected_objects)
    
    def execute(self, context):
        # Ensure the geometry node group exists
        node_group = create_geometry_node_setup()
        
        applied_count = 0
        
        for obj in context.selected_objects:
            if obj.type != 'MESH':
                continue
            
            # Check if object already has the modifier
            existing_modifier = None
            for mod in obj.modifiers:
                if mod.type == 'NODES' and mod.node_group == node_group:
                    existing_modifier = mod
                    break
            
            # If modifier doesn't exist, create it
            if not existing_modifier:
                modifier = obj.modifiers.new(name="PointCloudGeneration", type='NODES')
                modifier.node_group = node_group
            else:
                modifier = existing_modifier
            
            # Try to get image from object's material
            image = None
            if obj.data.materials:
                for material in obj.data.materials:
                    if material:
                        image = get_image_from_material(material)
                        if image:
                            break
            
            image_identifier = modifier.node_group.nodes['Group Input'].outputs['Image'].identifier
            # Set the image input if found
            if image and image_identifier in modifier:
                modifier[image_identifier] = image
                print(f"Applied image '{image.name}' to {obj.name}")
            
            applied_count += 1
        
        if applied_count > 0:
            self.report({'INFO'}, f"Applied Point Cloud modifier to {applied_count} object(s)")
        else:
            self.report({'WARNING'}, "No mesh objects selected")
        
        return {'FINISHED'}

def get_image_from_material(material):
    """Extract image from material's shader nodes"""
    if not material or not material.use_nodes:
        return None
    
    nodes = material.node_tree.nodes
    
    # Look for Image Texture nodes
    for node in nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            return node.image
    
    return None