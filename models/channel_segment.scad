// ============================================
// Artemis II LED Tracker - Channel Segment
// Print 6x in silk specter filament
// Bambu Lab A1 Mini (180x180x180mm)
// ============================================
// Settings: 0.2mm layer height, 3 walls, 15% infill
// Orientation: print flat (base down)
// ============================================

/* [Strip Properties] */
strip_width = 12;          // LED strip width (mm)
strip_clearance = 0.5;     // Clearance each side of strip (mm)

/* [Channel Dimensions] */
wall = 2;                  // Side wall thickness (mm)
base = 2;                  // Bottom thickness (mm)
total_height = 10;         // Total wall height (mm)
lip_inset = 1.5;           // Inward lip width - holds diffuser (mm)
lip_h = 1.2;               // Lip thickness (mm)

/* [Segment] */
leds_per_seg = 10;         // LEDs per segment (10 x 6 = 60 total)
led_pitch = 16.667;        // LED spacing (mm) = 1000/60

/* [Joint - tab/slot connection] */
tab_len = 8;               // Tab length (mm)
tab_w = 8;                 // Tab width (mm)
tab_h = 4;                 // Tab height (mm)
tol = 0.2;                 // Joint tolerance (mm)

/* [Mounting] */
screw_d = 4;               // Screw hole diameter (mm)

/* [Computed - do not change] */
seg_len = leds_per_seg * led_pitch;  // ~166.67mm
inner_w = strip_width + strip_clearance * 2;  // 13mm
outer_w = inner_w + wall * 2;  // 17mm
$fn = 30;

module channel_segment() {
    difference() {
        union() {
            // Solid block, then carve out the channel
            cube([outer_w, seg_len, total_height]);

            // Male tab (+Y end)
            translate([(outer_w - tab_w) / 2, seg_len - 0.01, base])
                cube([tab_w, tab_len + 0.01, tab_h]);
        }

        // Carve main channel (full inner height, but leave lips)
        // Lower portion: full inner width (below lips)
        translate([wall, -0.01, base])
            cube([inner_w, seg_len + 0.02, total_height - base - lip_h + 0.01]);

        // Upper portion: only between lips (narrower)
        translate([wall + lip_inset, -0.01, total_height - lip_h - 0.01])
            cube([inner_w - lip_inset * 2, seg_len + 0.02, lip_h + 0.02]);

        // Female slot (-Y end)
        translate([(outer_w - tab_w) / 2 - tol, -0.01, base - tol])
            cube([tab_w + tol * 2, tab_len + tol + 0.01, tab_h + tol * 2]);

        // Mounting screw holes
        for (y = [seg_len * 0.3, seg_len * 0.7])
            translate([outer_w / 2, y, -0.01])
                cylinder(d = screw_d, h = base + 0.02);
    }
}

channel_segment();
