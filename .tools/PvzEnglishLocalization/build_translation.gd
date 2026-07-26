extends SceneTree


func _init() -> void:
	var arguments := _parse_arguments(OS.get_cmdline_user_args())
	for required in ["source", "messages", "output"]:
		if not arguments.has(required):
			_fail(
				"Usage: godot --headless --script build_translation.gd -- "
				+ "--source ORIGINAL_ZH.translation "
				+ "--messages messages.json "
				+ "--output Translate.en.translation"
			)
			return

	var source: Resource = ResourceLoader.load(arguments["source"])
	if source == null or not source is OptimizedTranslation:
		_fail("Source is not an OptimizedTranslation: " + arguments["source"])
		return

	var parsed: Variant = JSON.parse_string(
		FileAccess.get_file_as_string(arguments["messages"])
	)
	if not parsed is Array:
		_fail("Messages file must contain a JSON array: " + arguments["messages"])
		return

	var messages: Array = parsed
	var hash_table: PackedInt32Array = source.get("hash_table")
	var bucket_table: PackedInt32Array = source.get("bucket_table").duplicate()
	var expected_count := _count_messages(hash_table, bucket_table)
	if messages.size() != expected_count:
		_fail(
			"Message count mismatch: expected %d, got %d"
			% [expected_count, messages.size()]
		)
		return

	var strings := PackedByteArray()
	var message_index := 0
	for bucket_offset in hash_table:
		if bucket_offset == -1:
			continue
		var bucket_size := bucket_table[bucket_offset]
		for element_index in range(bucket_size):
			var element_offset := bucket_offset + 2 + element_index * 4
			var encoded: PackedByteArray = str(messages[message_index]).to_utf8_buffer()
			bucket_table[element_offset + 1] = strings.size()
			bucket_table[element_offset + 2] = encoded.size()
			bucket_table[element_offset + 3] = encoded.size()
			strings.append_array(encoded)
			message_index += 1

	var translation: OptimizedTranslation = source.duplicate(true)
	translation.locale = "en"
	translation.set("hash_table", hash_table)
	translation.set("bucket_table", bucket_table)
	translation.set("strings", strings)

	var save_error := ResourceSaver.save(translation, arguments["output"])
	if save_error != OK:
		_fail(
			"Could not save translation (%s): %s"
			% [error_string(save_error), arguments["output"]]
		)
		return

	var verification: Resource = ResourceLoader.load(
		arguments["output"],
		"",
		ResourceLoader.CACHE_MODE_IGNORE
	)
	if verification == null or not verification is OptimizedTranslation:
		_fail("Saved translation could not be reloaded.")
		return
	if verification.get_translated_message_list().size() != expected_count:
		_fail("Saved translation has the wrong number of messages.")
		return

	print(
		"Built English OptimizedTranslation: messages=%d bytes=%d output=%s"
		% [expected_count, strings.size(), arguments["output"]]
	)
	quit(0)


func _parse_arguments(raw_arguments: PackedStringArray) -> Dictionary:
	var parsed := {}
	var index := 0
	while index < raw_arguments.size():
		var argument := raw_arguments[index]
		if argument.begins_with("--") and index + 1 < raw_arguments.size():
			parsed[argument.trim_prefix("--")] = raw_arguments[index + 1]
			index += 2
		else:
			index += 1
	return parsed


func _count_messages(
	hash_table: PackedInt32Array,
	bucket_table: PackedInt32Array
) -> int:
	var count := 0
	for bucket_offset in hash_table:
		if bucket_offset != -1:
			count += bucket_table[bucket_offset]
	return count


func _fail(message: String) -> void:
	push_error(message)
	quit(1)
