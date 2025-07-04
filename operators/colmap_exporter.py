import bpy
import mathutils
from pathlib import Path
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from .. utils.create_point3d import create_point3d_from_mesh
from .. utils.read_write_model import write_model, Camera, Image
import numpy as np
import glob

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

    camera_model: EnumProperty(
        name="Camera Model",
        description="Choose camera model for COLMAP",
        items=[
            ('PINHOLE', 'Pinhole', 'Pinhole camera model'),
            ('OPENCV', 'OpenCV', 'OpenCV camera model')
        ],
        default='OPENCV'
    )

    downsample_images: BoolProperty(
        name="Downsample Images",
        description="Create downsampled versions of the rendered images",
        default=True
    )

    downsample_factors: StringProperty(
        name="Downsample Factors",
        description="Space-separated list of factors to downsample images by",
        default="2 4 8"
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

        if self.camera_model == 'PINHOLE':
            return [fx, fy, cx, cy]
        elif self.camera_model == 'OPENCV':
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
                    model=self.camera_model,
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

    def _downsample_and_save(self, img_path, output_dir, factor):
        """Downsample a single image using Blender's API and save it."""
        image = None
        try:
            # Load image into Blender
            image = bpy.data.images.load(str(img_path), check_existing=False)

            if factor <= 1:
                bpy.data.images.remove(image)
                return False

            # Calculate new size and scale
            new_width = image.size[0] // factor
            new_height = image.size[1] // factor
            image.scale(new_width, new_height)

            # Backup scene render settings
            scene = bpy.context.scene
            render_settings = scene.render.image_settings
            original_format = render_settings.file_format
            original_quality = render_settings.quality
            original_color_mode = render_settings.color_mode

            # Set output format based on original extension
            output_path = output_dir / img_path.name
            file_ext = img_path.suffix.lower()

            if file_ext in ['.jpg', '.jpeg']:
                render_settings.file_format = 'JPEG'
                render_settings.quality = 95
                render_settings.color_mode = 'RGB'
            elif file_ext == '.png':
                render_settings.file_format = 'PNG'
                render_settings.color_mode = 'RGBA'
            elif file_ext in ['.tif', '.tiff']:
                render_settings.file_format = 'TIFF'
            elif file_ext == '.bmp':
                render_settings.file_format = 'BMP'
            else:
                render_settings.file_format = 'PNG'
                output_path = output_path.with_suffix('.png')

            # Save the scaled image
            image.save_render(filepath=str(output_path))

            # Restore render settings
            render_settings.file_format = original_format
            render_settings.quality = original_quality
            render_settings.color_mode = original_color_mode

            bpy.data.images.remove(image)
            return True
        except Exception as e:
            self.report({'ERROR'}, f"Error processing {img_path.name}: {e}")
            if image and image.name in bpy.data.images:
                bpy.data.images.remove(image)
            return False

    def run_downsampling(self, base_path):
        """Run the image downsampling process based on operator properties."""
        self.report({'INFO'}, "Starting image downsampling...")

        images_dir = base_path / "images"
        if not images_dir.is_dir():
            self.report({'WARNING'}, f"'images' directory not found in {base_path}. Skipping downsampling.")
            return

        try:
            factors = [int(f) for f in self.downsample_factors.split() if f.strip()]
        except ValueError:
            self.report({'ERROR'}, "Invalid downsample factors. Use space-separated integers (e.g., '2 4 8').")
            return

        extensions = ['*.jpg', '*.jpeg', '*.png', '*.tif', '*.tiff', '*.bmp']
        image_files = []
        for ext in extensions:
            image_files.extend(glob.glob(str(images_dir / ext)))
            image_files.extend(glob.glob(str(images_dir / ext.upper())))

        if not image_files:
            self.report({'INFO'}, "No images found to downsample.")
            return

        for factor in factors:
            output_dir = base_path / f"images_{factor}"
            output_dir.mkdir(exist_ok=True)
            self.report({'INFO'}, f"Generating {len(image_files)} images for factor {factor} in {output_dir}...")
            
            for img_path_str in image_files:
                self._downsample_and_save(Path(img_path_str), output_dir, factor)

        self.report({'INFO'}, "Image downsampling finished.")

    def execute(self, context):
        context.window_manager.progress_begin(0, 100)
        result = {'CANCELLED'}
        try:
            output_path = Path(self.filepath)
            result = self.export_dataset(context, output_path, self.output_format)
            if result == {'FINISHED'} and self.downsample_images:
                self.run_downsampling(output_path)
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
        layout.prop(self, "camera_model")

        box = layout.box()
        box.prop(self, "downsample_images")
        if self.downsample_images:
            sub = box.row(align=True)
            sub.prop(self, "downsample_factors")
