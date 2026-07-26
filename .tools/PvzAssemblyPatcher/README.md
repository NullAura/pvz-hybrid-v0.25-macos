# PvzAssemblyPatcher

该工具使用 Mono.Cecil 对上游 `PlantsVsZombies.dll` 应用可复现的 macOS
兼容性修复。它不会读取或修改玩家存档。

## 构建

```sh
dotnet build .tools/PvzAssemblyPatcher/PvzAssemblyPatcher.csproj
```

## 使用

先备份目标程序集，然后在程序集及其依赖文件所在目录中执行：

```sh
dotnet run --project .tools/PvzAssemblyPatcher -- \
  patch /path/to/PlantsVsZombies.dll

dotnet run --project .tools/PvzAssemblyPatcher -- \
  patch-victory /path/to/PlantsVsZombies.dll

dotnet run --project .tools/PvzAssemblyPatcher -- \
  patch-wave-resume /path/to/PlantsVsZombies.dll

dotnet run --project .tools/PvzAssemblyPatcher -- \
  patch-english-update /path/to/PlantsVsZombies.dll
```

- `patch` 修复游戏指令回调的参数展开逻辑。
- `patch-victory` 修复友方、魅惑及玩家控制僵尸阻塞波次或通关的问题。
- `patch-wave-resume` 修复首波启动前保存后，恢复关卡时波次系统保持停止的
  问题；同时禁止再次写入这种未完成初始化的检查点。
- `patch-english-update` 保留版本信息和手动更新链接，但不再用中文版上游更新
  弹窗阻断英文版主菜单。
- `inspect` 和 `inspect-victory` 只输出相关 IL，不写入程序集。

四个补丁命令均可重复执行；目标逻辑已修复时不会再次改写文件。补丁仅适用于
当前仓库所对应的 v0.25 程序集，更新上游游戏后应重新检查目标类型和 IL。
