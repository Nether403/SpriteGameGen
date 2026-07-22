extends SceneTree

func _initialize() -> void:
    var frames = load("res://character_sprite_frames.tres") as SpriteFrames
    if frames == null or not frames.has_animation("Walk"):
        push_error("Generated SpriteFrames did not load the Walk animation")
        quit(1)
        return
    if frames.get_frame_count("Walk") != 1:
        push_error("Generated SpriteFrames has the wrong frame count")
        quit(1)
        return
    if not frames.get_animation_loop("Walk"):
        push_error("Generated loop setting is incorrect")
        quit(1)
        return
    if abs(frames.get_frame_duration("Walk", 0) - 0.125) > 0.0001:
        push_error("Generated frame duration is incorrect")
        quit(1)
        return
    if frames.get_frame_texture("Walk", 0) == null:
        push_error("Generated frame texture did not load")
        quit(1)
        return
    var packed = load("res://character_animated_sprite_2d.tscn") as PackedScene
    if packed == null:
        push_error("Generated AnimatedSprite2D scene did not load")
        quit(1)
        return
    var node = packed.instantiate() as AnimatedSprite2D
    if node == null or node.sprite_frames == null or not node.centered or node.offset != Vector2(0, -1):
        push_error("Generated scene has invalid sprite configuration")
        quit(1)
        return
    quit(0)
