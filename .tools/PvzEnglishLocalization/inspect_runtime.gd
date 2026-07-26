extends SceneTree

func _initialize() -> void:
	call_deferred("_inspect")


func _inspect() -> void:
	print("INSPECT project_name=", ProjectSettings.get_setting("application/config/name"))
	print("INSPECT locale=", TranslationServer.get_locale())
	print("INSPECT translations=", ProjectSettings.get_setting("internationalization/locale/translations"))

	var packed := load("res://Scene/MainMenu/MainMenu.tscn") as PackedScene
	if packed == null:
		print("INSPECT could not load MainMenu.tscn")
		quit(2)
		return

	var menu := packed.instantiate()
	print("INSPECT before_ready")
	_print_visible_strings(menu)
	root.add_child(menu)
	await process_frame
	print("INSPECT after_ready")
	_print_visible_strings(menu)
	menu.queue_free()
	quit()


func _print_visible_strings(node: Node) -> void:
	for property_name in [
		"text",
		"title",
		"tooltip_text",
		"placeholder_text",
		"dialog_text",
		"ok_button_text",
		"cancel_button_text",
	]:
		for property in node.get_property_list():
			if property.name == property_name:
				var value: Variant = node.get(property_name)
				if value is String and not value.is_empty():
					print("INSPECT ", node.get_path(), ".", property_name, "=", value)
				break
	for child in node.get_children():
		_print_visible_strings(child)
