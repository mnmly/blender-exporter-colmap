import bpy
import mathutils
from pathlib import Path
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from .. utils.create_point3d import create_point3d_from_mesh
from .. utils.read_write_model import write_model, Camera, Image
import numpy as np

class BlenderExporterForColmap(bpy.types.Operator, ExportHelper):

    """Export scene data for COLMAP reconstruction"""
    bl_idname = "colmap_prep.export"
    bl_label = "Export for COLMAP"
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = ""

    # Additional properties
    render_keyframes_only: BoolProperty(
        name="Render Keyframes Only",
        description="Only render at camera keyframe positions",
        default=True
    )
    
    output_format: EnumProperty(
        name="Output Format",
        description="Choose output format for COLMAP data",
        items=[
            ('txt', 'Text (.txt)', 'Text format'),
            ('bin', 'Binary (.bin)', 'Binary format')
        ],
        default='bin'
    )

    def get_pc_gen_modifier(self, obj):
        for mod in obj.modifiers:
            if mod.node_group.name == "PointCloudGeneration":
                return mod
        return None


    def get_camera_keyframes(self, camera):
        """Get all keyframe positions for a camera"""
        keyframes = set()
        
        if camera.animation_data and camera.animation_data.action:
            action = camera.animation_data.action
            for fcurve in action.fcurves:
                if fcurve.data_path.startswith(('location', 'rotation')):
                    for keyframe in fcurve.keyframe_points:
                        keyframes.add(int(keyframe.co[0]))
        
        # If no keyframes found, use current frame
        if not keyframes:
            keyframes.add(bpy.context.scene.frame_current)
            
        return sorted(keyframes)

    def setup_point_cloud_modifiers(self):
        """Prepare point cloud modifiers for export"""
        modifier_states = {}
        point3ds = []
        
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                mod = self.get_pc_gen_modifier(obj)
                if mod:
                    # Store original states
                    modifier_states[obj.name_full] = {
                        'show_viewport': mod.show_viewport,
                        'show_render': mod.show_render,
                        'preview_state': None
                    }
                    
                    # Enable modifier
                    mod.show_viewport = True
                    mod.show_render = True
                    
                    # Turn off Preview mode
                    if mod.node_group and "Group Input" in mod.node_group.nodes:
                        group_input = mod.node_group.nodes['Group Input']
                        if "Preview" in group_input.outputs:
                            identifier = group_input.outputs['Preview'].identifier
                            modifier_states[obj.name_full]['preview_state'] = mod.get(identifier, True)
                            mod[identifier] = False
                    
                    # Enable modifier
                    mod.show_viewport = True
                    mod.show_render = True
                    # Generate point cloud data
                    original_frame = bpy.context.scene.frame_current

                    bpy.context.scene.frame_set(original_frame + 1)  # Force update
                    
                    # Add your point cloud generation logic here
                    point3ds.extend(create_point3d_from_mesh(obj))

                    mod.show_viewport = False
                    mod.show_render = False
                    
                    bpy.context.scene.frame_set(original_frame)
        
        return modifier_states, point3ds
    
    def restore_modifier_states(self, modifier_states):
        """Restore original modifier states"""
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.name_full in modifier_states:
                mod = self.get_pc_gen_modifier(obj)
                if mod:
                    states = modifier_states[obj.name_full]
                    mod.show_viewport = states['show_viewport']
                    mod.show_render = states['show_render']
                    if states['preview_state'] is not None:
                        if mod.node_group and "Group Input" in mod.node_group.nodes:
                            group_input = mod.node_group.nodes['Group Input']
                            if "Preview" in group_input.outputs:
                                identifier = group_input.outputs['Preview'].identifier
                                mod[identifier] = states['preview_state']

    def get_camera_parameters(self, camera, scene):
        """Extract camera parameters for COLMAP"""
        width=int(scene.render.resolution_x * scene.render.resolution_percentage / 100.0)
        height=int(scene.render.resolution_y * scene.render.resolution_percentage / 100.0)
        
        # Calculate focal length in pixels
        focal_length = camera.data.lens
        sensor_width = camera.data.sensor_width
        sensor_height = camera.data.sensor_height
        
        fx = focal_length * width / sensor_width
        fy = focal_length * height / sensor_height
        
        # Principal point (assuming centered)
        cx = width / 2
        cy = height / 2
        
        # Distortion parameters (set to 0 for now)
        k1 = k2 = p1 = p2 = 0
        
        return [fx, fy, cx, cy, k1, k2, p1, p2]

    def get_camera_pose(self, camera):
        """Get camera pose in COLMAP format"""
        rotation_mode_backup = camera.rotation_mode
        camera.rotation_mode = "QUATERNION"
        
        cam_rot_orig = mathutils.Quaternion(camera.rotation_quaternion)
        
        cam_rot = mathutils.Quaternion((
            cam_rot_orig.x,
            cam_rot_orig.w, 
            cam_rot_orig.z,
            -cam_rot_orig.y
        ))
        
        # Get translation
        location = mathutils.Vector(camera.location)
        translation = -(cam_rot.to_matrix() @ location)
        
        # Restore rotation mode
        camera.rotation_mode = rotation_mode_backup
        
        return {
            'qvec': np.array([cam_rot.w, cam_rot.x, cam_rot.y, cam_rot.z]),
            'tvec': np.array([translation.x, translation.y, translation.z])
        }

    def render_camera_at_frame(self, camera, frame, output_path):
        """Render camera at specific frame"""
        original_frame = bpy.context.scene.frame_current
        original_camera = bpy.context.scene.camera
        
        try:
            bpy.context.scene.frame_set(frame)
            bpy.context.scene.camera = camera
            bpy.ops.render.render()
            bpy.data.images['Render Result'].save_render(str(output_path))
            
        finally:
            bpy.context.scene.frame_set(original_frame)
            bpy.context.scene.camera = original_camera

    def export_dataset(self, context, dirpath: Path, format: str):
        scene = context.scene
        output_dir = dirpath / 'sparse' / '0'
        images_dir = dirpath / 'images'

        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)
        
        scene_cameras = [obj for obj in scene.objects if obj.type == "CAMERA"]
        if not scene_cameras:
            self.report({'ERROR'}, "No cameras found in scene")
            return {'CANCELLED'}

        modifier_states, point3ds = self.setup_point_cloud_modifiers()

        try:
            cameras = {}
            images = {}
            total_renders = 0
            current_render = 0
            modifier_states = {}
            for camera in scene_cameras:
                if self.render_keyframes_only:
                    keyframes = self.get_camera_keyframes(camera)
                    total_renders += len(keyframes)
                else:
                    total_renders += 1
            
            camera_id = 1
            image_id = 1
            for camera in sorted(scene_cameras, key=lambda x: x.name_full):
                params = self.get_camera_parameters(camera, scene)
                cameras[camera_id] = Camera(
                    id=camera_id,
                    model='OPENCV',
                    width=int(scene.render.resolution_x * scene.render.resolution_percentage / 100.0),
                    height=int(scene.render.resolution_y * scene.render.resolution_percentage / 100.0),
                    params=params
                )
                if self.render_keyframes_only:
                    frames_to_render = self.get_camera_keyframes(camera)
                else:
                    frames_to_render = [scene.frame_current]

                for frame in frames_to_render:
                    original_frame = scene.frame_current
                    scene.frame_set(frame)

                    pose = self.get_camera_pose(camera)

                    file_format = scene.render.image_settings.file_format.lower()
                    if self.render_keyframes_only and len(frames_to_render) > 1:
                        filename = f"{camera.name_full}_frame_{frame:04d}.{file_format}"
                    else:
                        filename = f"{camera.name_full}.{file_format}"
                    images[image_id] = Image(
                        id=image_id,
                        qvec=pose['qvec'],
                        tvec=pose['tvec'],
                        camera_id=camera_id,
                        name=filename,
                        xys=[],
                        point3D_ids=[]
                    )
                    output_path = images_dir / filename
                    self.render_camera_at_frame(camera, frame, output_path)

                    current_render += 1
                    progress = (current_render / total_renders) * 100
                    context.window_manager.progress_update(progress)
                    # Restore frame
                    scene.frame_set(original_frame)
                    image_id += 1
                
                camera_id += 1

            write_model(cameras, images, {item.id: item for item in point3ds}, output_dir, self.output_format)
        finally:
            self.restore_modifier_states(modifier_states)

        return {'FINISHED'}

    def execute(self, context):
        context.window_manager.progress_begin(0, 100)
        try:
            result = self.export_dataset(context, Path(self.filepath), self.output_format)
        finally:
            context.window_manager.progress_end()
        
        return result

    def invoke(self, context, event):
        """Invoke the file browser"""
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def draw(self, context):
        """Draw the export options"""
        layout = self.layout
        
        layout.prop(self, "render_keyframes_only")
        layout.prop(self, "output_format")
