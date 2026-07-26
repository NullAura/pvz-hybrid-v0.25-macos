extends SceneTree


func _initialize() -> void:
	var arguments := OS.get_cmdline_user_args()
	if arguments.size() != 2:
		push_error("usage: -- <res://texture.ctex> <output.png>")
		quit(2)
		return

	var texture := ResourceLoader.load(arguments[0]) as Texture2D
	if texture == null:
		push_error("unable to load texture: %s" % arguments[0])
		quit(3)
		return

	var image := texture.get_image()
	if image == null or image.is_empty():
		push_error("texture has no readable image: %s" % arguments[0])
		quit(4)
		return

	var result := image.save_png(arguments[1])
	if result != OK:
		push_error("unable to save PNG: %s" % error_string(result))
		quit(5)
		return

	print(
		"Exported texture: %dx%d -> %s"
		% [image.get_width(), image.get_height(), arguments[1]]
	)
	quit()
