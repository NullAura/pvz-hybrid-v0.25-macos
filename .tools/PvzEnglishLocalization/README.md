# PvzEnglishLocalization

该目录保存英文语言包的可复现构建工具，不包含原游戏资源。

`build_catalog.py` 只合并人工审校过的英文条目，不调用自动翻译服务或模型。
构建时会检查 Godot 富文本标签、格式化占位符、资源路径和控制台指令，任何
缺失条目或残留中文都会使构建失败。

`build_translation.gd` 根据中文 `OptimizedTranslation` 原有的哈希表顺序生成
英文资源，因此即使少数原始文本键无法恢复，也能保持正确映射。

植物名、僵尸名、剧情文本、图鉴说明和界面文字均按游戏语境人工翻译。

`build_runtime_map.py` 把已验证语言表与人工维护的运行时词典合并成精确字符串
映射。`build_resource_patch.py` 仅替换 Godot 文本资源中与词典完整匹配的字符串，
不会对片段执行模糊替换，也不会更改对象 ID、数值或资源路径。程序集使用
`PvzAssemblyPatcher patch-strings` 应用同一份映射。英文资源补丁还会只注册
英文 `OptimizedTranslation` 并把回退语言固定为 `en`，保证系统语言为中文时
也不会重新选中中文语言包。

`apply_graphic_localization.py` 只把已经逐张审校、由原图重绘并重新导入的英文
贴图加入资源补丁。英文按钮保持原图的画布尺寸、轮廓、材质和透明通道，不通过
场景中的矩形色块覆盖中文字，也不更改按钮路径、信号、点击区域或游戏状态。
原游戏贴图和导入产物不进入仓库，构建时由本地合法游戏资源生成。

具有交互状态的贴图必须按中文版成组处理：普通、悬停、高亮、按下、禁用和锁定
状态分别以对应的中文原图为基础重绘，不能用一个状态复制替代另一个状态。构建
校验要求英文贴图画布尺寸与各自原图完全一致，并确认文字裁切区之外的像素没有
变化。场景节点、命中区域、信号、动画和音效资源保持不变；最终还需在实际应用
中逐项执行鼠标悬停、按下、进入和返回的回归测试。

`audit_localization_parity.py` 会将英文 PCK 与中文版基准逐项比较，并重新执行
每个文本资源的精确字符串替换。除语言资源和列入图形清单的导入贴图外，任何
新增、删除或改变的 PCK 条目都会使审计失败。对于 Godot 场景，审计还会比较
节点数量、顺序、类型、唯一 ID、父子关系及全部信号连接。`TabContainer` 和
`MenuBar` 会直接把直属子节点名显示为标签，因此仅允许这些可见标签按词典改名；
其后代路径必须解析到与中文版相同的节点，其他内部节点名一律不允许改变。
程序集则使用 `PvzAssemblyPatcher compare-logic` 比较全部类型、字段、方法、
局部变量、IL 指令、跳转和异常处理结构，只允许 `ldstr` 的可见字符串值不同。

翻译脚本可同时通过 `--messages-json` 导出按哈希表遍历顺序排列的英文消息。
随后使用 Godot 4.7 执行：

```text
godot --headless --script build_translation.gd -- \
  --source Translate.zh.translation \
  --messages messages.json \
  --output Translate.en.translation
```
