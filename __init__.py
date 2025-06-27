import bpy
from .operators.colmap_exporter import BlenderExporterForColmap
from .operators.apply_modifier import COLMAP_PREP_OT_apply_modifier
from .panels.colmap_prep_panel import COLMAP_PREP_PT_panel

bl_info = {
    "name": "Scene exporter for colmap",
    "description": "Generates a dataset for colmap by exporting blender camera poses and rendering scene.",
    "author": "Ohayoyogi",
    "version": (0, 3, 0),
    "blender": (3, 6, 0),
    "location": "View3D > N-Panel > COLMAP PREP",
    "warning": "",
    "wiki_url": "https://github.com/mnmly/blender-exporter-colmap",
    "tracker_url": "https://github.com/mnmly/blender-exporter-colmap/issues",
    "category": "Mesh",
}

classes = (
    BlenderExporterForColmap,
    COLMAP_PREP_PT_panel,
    COLMAP_PREP_OT_apply_modifier
)

def menu_func_export(self, context):
    """Add to export menu"""
    self.layout.operator(BlenderExporterForColmap.bl_idname, text="COLMAP (folder)")

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
