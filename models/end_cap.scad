// ============================================
// Artemis II LED Tracker - End Cap
// Print 2x (one for each end of the strip)
// Print in silk specter to match channels
// ============================================
// Settings: 0.2mm layer height, 3 walls, 15% infill
// ============================================

/* [Must match channel_segment.scad values] */
strip_width = 12;
strip_clearance = 0.5;
wall = 2;
base = 2;
total_height = 10;

/* [End Cap] */
cap_depth = 3;             // How deep the cap plugs into channel (mm)
cap_thick = 2;             // End wall thickness (mm)
tol = 0.25;                // Fit tolerance (mm)
wire_hole_d = 5;           // Hole for wire pass-through (mm), set to 0 for solid

/* [Computed] */
inner_w = strip_width + strip_clearance * 2;
outer_w = inner_w + wall * 2;
inner_h = total_height - base;

module end_cap() {
    difference() {
        union() {
            // Outer face (flush with channel end)
            cube([outer_w, cap_thick, total_height]);

            // Inner plug (slides into channel)
            translate([wall + tol, -cap_depth, base + tol])
                cube([inner_w - tol * 2, cap_depth + 0.01, inner_h - tol * 2]);
        }

        // Wire pass-through hole (for data + power cables)
        if (wire_hole_d > 0)
            translate([outer_w / 2, -cap_depth - 0.01, base + inner_h / 2])
                rotate([-90, 0, 0])
                    cylinder(d = wire_hole_d, h = cap_depth + cap_thick + 0.02, $fn = 30);
    }
}

end_cap();
