"""Generic test items only; never import a customer quotation as a fixture."""
DEMO = [{
    "room": "Sample Room", "floor": "GF", "cat": "custom_cabinet",
    "material": "body_particle", "door": "door_melamine",
    "cab_name": "Sample Wardrobe", "length_mm": 1800,
    "height_mm": 2400, "depth_mm": 600, "qty": 1,
    "note": "", "note_en": "", "room_note": "", "room_note_en": "",
    "extras": {}, "extras_size": {},
}]
BOUNDARY = [{
    "room": "Sample Room", "floor": "GF", "cat": "custom_cabinet",
    "material": "body_particle", "door": "", "cab_name": "Sample Low Cabinet",
    "length_mm": 1200, "height_mm": 450, "depth_mm": 400, "qty": 1,
    "note": "", "note_en": "", "room_note": "", "room_note_en": "",
    "apply_min_height": False, "extras": {}, "extras_size": {},
}]
