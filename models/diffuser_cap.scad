// ============================================
// Artemis II LED Tracker - Diffuser Cap
// Print 6x in WHITE PLA
// Bambu Lab A1 Mini (180x180x180mm)
// ============================================
// Settings: 0.2mm layer height, 2 walls, 0% infill
// This gives ~0.8mm wall thickness = great diffusion
// TIP: Enable "fuzzy skin" in Bambu Studio for
//      an even better frosted-glass look
// ============================================

/* [Must match channel_segment.scad values] */
strip_width = 12;
strip_clearance = 0.5;
wall = 2;
total_height = 10;
lip_inset = 1.5;
lip_h = 1.2;
leds_per_seg = 10;
led_pitch = 16.667;

/* [Diffuser Properties] */
diff_thick = 1.0;          // Top surface thickness (mm) - thin = more glow
side_h = 2.0;              // Side tab height (mm) - sits on lips
fit_gap = 0.3;             // Clearance for easy slide-in fit (mm)
end_gap = 0.5;             // Shorten slightly so it slides in easily (mm)

/* [Computed] */
seg_len = leds_per_seg * led_pitch;
inner_w = strip_width + strip_clearance * 2;
cap_w = inner_w - fit_gap * 2;          // Fits between channel walls
cap_len = seg_len - end_gap * 2;        // Slightly shorter than channel
free_span = inner_w - lip_inset * 2;    // Open gap between lips
tab_w = (cap_w - free_span) / 2 + 0.3; // Tab overlap on each lip

module diffuser_cap() {
    // Flat diffuser top
    translate([0, 0, side_h])
        cube([cap_w, cap_len, diff_thick]);

    // Left side tab (rests on lip)
    cube([tab_w, cap_len, side_h + diff_thick]);

    // Right side tab (rests on lip)
    translate([cap_w - tab_w, 0, 0])
        cube([tab_w, cap_len, side_h + diff_thick]);
}

diffuser_cap();
