import bpy
from bpy.types import Panel

class COLMAP_PREP_PT_panel(Panel):
    """Point Cloud Generator Panel"""
    bl_label = "COLMAP PREP"
    bl_idname = "COLMAP_PREP_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "COLMAP PREP"
    
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.scale_y = 2.0
        row.operator("colmap_prep.apply_modifier", text="Apply to Selected Planes")

        layout.separator()
        box = layout.box()
        box.label(text="Instructions:", icon='INFO')
        box.label(text="1. Select plane objects with materials")
        box.label(text="2. Ensure materials have image textures")
        box.label(text="3. Click 'Apply to Selected Planes'")