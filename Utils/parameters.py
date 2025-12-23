# Stock Cube Parameters
stock_min_x = 10.0
stock_min_y = 10.0
stock_min_z = 10.0

stock_max_x = 50.0 #50
stock_max_y = 50.0 #50
stock_max_z = 50.0 #50

stock_dim_x = None
stock_dim_y = None
stock_dim_z = None

# General Feature Parameters
min_len = 2.0 #2
clearance = 1 #1
inner_bounds_clearance = 2

# Round Parameters
round_radius_min = 0.1
round_radius_max = 5.0

# Variable Round Parameters
variable_round_radius_min = 0.1
variable_round_radius_max = 5.0

# Thread / Stud Parameters
thread_profile_scale_min = 0.5  # ratio applied to available half-width/height
thread_profile_scale_max = 0.9
stud_height_scale_min = 0.5     # ratio of available height for stud extrusion
stud_height_scale_max = 1.0

# Chamfer Parameters
chamfer_depth_min = 0.1 # 1
chamfer_depth_max = 4.0 #4

# Possible Machining Features
feat_names = ['chamfer', #0
              'through_hole', #1
              'triangular_passage', #2
              'rectangular_passage', #3
              '6sides_passage', #4
              'triangular_through_slot', #5
              'rectangular_through_slot', #6
              'circular_through_slot', #7
              'rectangular_through_step', #8
              '2sides_through_step', #9
              'slanted_through_step', #10
              'Oring', #11
              'blind_hole', #12
              'triangular_pocket', #13
              'rectangular_pocket', #14
              '6sides_pocket', #15
              'circular_end_pocket', #16
              'rectangular_blind_slot', #17
              'v_circular_end_blind_slot', #18
              'h_circular_end_blind_slot', #19
              'triangular_blind_step', #20
              'circular_blind_step', #21
              'rectangular_blind_step', #22
              'round', #23
              'counterbore', #24
              'boss', #25
              'countersunk_hole', #26
              'rib', #27
              'variable_round', #28
              'stud', #29
              'threaded_hole', #30
              'stock'] #31

feat_names_planar = ['rectangular_through_slot', #0
             'triangular_through_slot', #1
             'rectangular_passage', #2
             'triangular_passage', #3
             '6sides_passage', #4
             'rectangular_through_step', #5
             '2sides_through_step', #6
             'slanted_through_step', #7
             'rectangular_blind_step', #8
             'triangular_blind_step', #9
             'rectangular_blind_slot', #10
             'rectangular_pocket', #11
             'triangular_pocket', #12
             '6sides_pocket', #13
             'chamfer', #14
             'stock'] #15
