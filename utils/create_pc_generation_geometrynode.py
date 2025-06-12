import bpy


def create_point_material():

    if "M_Point" in bpy.data.materials:
        return bpy.data.materials["M_Point"]

    material = bpy.data.materials.new(name="M_Point")
    material.use_nodes = True
    
    node_tree = material.node_tree
    nodes = node_tree.nodes
    links = node_tree.links
    
    nodes.clear()
    
    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (300, 0)
    material_output.target = 'ALL' 
    
    attribute_node = nodes.new(type='ShaderNodeAttribute')
    attribute_node.location = (-200, 0)
    attribute_node.attribute_name = "Color" 
    attribute_node.attribute_type = 'GEOMETRY' 
    
    links.new(attribute_node.outputs['Color'], material_output.inputs['Surface'])

    return material


def create_geometry_node_setup():
    # Check if node group already exists
    if "PointCloudGeneration" in bpy.data.node_groups:
        return bpy.data.node_groups["PointCloudGeneration"]
    
    node_group = bpy.data.node_groups.new("PointCloudGeneration", "GeometryNodeTree")
    node_group.is_modifier = True

    nodes = node_group.nodes
    links = node_group.links
    
    nodes.clear()
    
    group_input = nodes.new(type='NodeGroupInput')
    group_input.location = (-800, 0)
    
    # Add inputs to the node group
    node_group.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    node_group.interface.new_socket(name="Image", in_out='INPUT', socket_type='NodeSocketImage')
    node_group.interface.new_socket(name="Radius", in_out='INPUT', socket_type='NodeSocketFloat')
    node_group.interface.new_socket(name="Density", in_out='INPUT', socket_type='NodeSocketFloat')
    node_group.interface.new_socket(name="Preview", in_out='INPUT', socket_type='NodeSocketBool')
    
    if hasattr(node_group.interface.items_tree[2], 'default_value'):
        node_group.interface.items_tree[2].default_value = 0.005  # Radius
    if hasattr(node_group.interface.items_tree[3], 'default_value'):
        node_group.interface.items_tree[3].default_value = 30000.0  # Density
    if hasattr(node_group.interface.items_tree[4], 'default_value'):
        node_group.interface.items_tree[4].default_value = True  # Preview
    
    image_texture = nodes.new(type='GeometryNodeImageTexture')
    image_texture.location = (-600, -200)
    
    # Create Named Attribute node
    named_attr = nodes.new(type='GeometryNodeInputNamedAttribute')
    named_attr.location = (-400, -400)
    named_attr.data_type = 'FLOAT_VECTOR'
    named_attr.inputs['Name'].default_value = "UVMap"
    
    # Create Distribute Points on Faces node
    distribute_points = nodes.new(type='GeometryNodeDistributePointsOnFaces')
    distribute_points.location = (-200, 0)
    distribute_points.distribute_method = 'RANDOM'
    
    # Create Store Named Attribute node
    store_named_attr = nodes.new(type='GeometryNodeStoreNamedAttribute')
    store_named_attr.location = (200, 0)
    store_named_attr.data_type = 'FLOAT_COLOR'
    store_named_attr.domain = 'POINT'
    store_named_attr.inputs['Name'].default_value = "Color"
    
    # Create Set Material node
    set_material = nodes.new(type='GeometryNodeSetMaterial')
    set_material.location = (400, 0)
    set_material.inputs[2].default_value = create_point_material()
    
    # Create Set Point Radius node
    set_point_radius = nodes.new(type='GeometryNodeSetPointRadius')
    set_point_radius.location = (600, 0)
    
    # Create Points to Vertices node
    points_to_vertices = nodes.new(type='GeometryNodePointsToVertices')
    points_to_vertices.location = (800, 0)
    
    # Create Switch nodes
    switch_node = nodes.new(type='GeometryNodeSwitch')
    switch_node.location = (1000, 0)
    switch_node.input_type = 'GEOMETRY'
    
    # Create Group Output node
    group_output = nodes.new(type='NodeGroupOutput')
    group_output.location = (1200, 0)
    
    # Add outputs to the node group
    node_group.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    
    # Create connections
    # Connect Group Input
    links.new(group_input.outputs['Geometry'], distribute_points.inputs['Mesh'])
    links.new(group_input.outputs['Image'], image_texture.inputs['Image'])
    links.new(group_input.outputs['Density'], distribute_points.inputs['Density'])
    links.new(group_input.outputs['Preview'], switch_node.inputs['Switch'])
    
    # Connect texture sampling
    links.new(named_attr.outputs['Attribute'], image_texture.inputs['Vector'])
    
    # Connect distribute points
    links.new(distribute_points.outputs['Points'], store_named_attr.inputs['Geometry'])
    links.new(image_texture.outputs['Color'], store_named_attr.inputs['Value'])
    
    # Connect store named attribute to set material
    links.new(store_named_attr.outputs['Geometry'], set_material.inputs['Geometry'])
    
    # Connect set material to set point radius
    links.new(set_material.outputs['Geometry'], set_point_radius.inputs['Points'])
    links.new(group_input.outputs['Radius'], set_point_radius.inputs['Radius'])
    
    # Connect to points to vertices
    links.new(set_point_radius.outputs['Points'], points_to_vertices.inputs['Points'])
    
    # Connect to switch
    links.new(points_to_vertices.outputs['Mesh'], switch_node.inputs['False'])
    links.new(set_point_radius.outputs['Points'], switch_node.inputs['True'])
    
    # Connect to outputs
    links.new(switch_node.outputs['Output'], group_output.inputs['Geometry'])
    # links.new(set_point_radius.outputs['Points'], group_output.inputs['Points'])
    # links.new(distribute_points.outputs['Selection'], group_output.inputs['Selection'])
    
    # Arrange nodes for better visibility
    for node in nodes:
        node.select = False
    
    print("Geometry node setup created successfully!")
    
    return node_group



# create_geometry_node_setup()
