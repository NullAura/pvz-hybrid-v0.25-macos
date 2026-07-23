# 植物大战僵尸杂交版 v0.25 for macOS

本项目为《植物大战僵尸杂交版》v0.25 提供非官方 macOS 兼容发行方案。发行包集成运行游戏所需的 Godot 与 .NET 组件，无需安装 Windows 或 CrossOver。

> 本项目与游戏原作者、发行方及相关权利人无隶属或授权关系。

## 下载

请从 [Releases](https://github.com/NullAura/pvz-hybrid-v0.25-macos/releases/latest) 下载以下文件：

- `v0.25-macOS-Release.zip`
- `v0.25-macOS-Release.zip.sha256`

可在终端中校验文件完整性：

```sh
shasum -a 256 -c v0.25-macOS-Release.zip.sha256
```

## 兼容性

| 项目 | 要求 |
| --- | --- |
| 操作系统 | macOS 13 或更高版本 |
| Intel Mac | 原生运行 |
| Apple 芯片 Mac | 通过 Rosetta 2 运行 |
| 游戏架构 | x86_64 |

Apple 芯片 Mac 如尚未安装 Rosetta 2，可执行：

```sh
softwareupdate --install-rosetta
```

## 安装

1. 下载并完整解压 Release ZIP。
2. 将 `植物大战僵尸杂交版v0.25.app` 拖入“应用程序”文件夹。
3. 首次启动时右键应用并选择“打开”。
4. 如果 macOS 继续阻止启动，请在“系统设置 → 隐私与安全性”中选择“仍要打开”。

当前发行包采用 ad-hoc 签名，未经过 Apple Developer ID 公证，因此首次启动需要由用户手动确认。

## 兼容性调整

- 修正控制台数值参数的解析逻辑，包括 `/coin 100000`
- 恢复游戏内图形指令面板
- 修正 `/debug openalllevel on` 的指令处理
- 支持使用 `/win` 进入正常关卡结算流程
- 提供自包含的 Godot 4.7 Stable Mono 与 .NET 9 x64 运行环境

## 指令控制台

按键盘左上角、`Esc` 下方的 `` ` / ~ `` 键打开控制台。常用指令：

```text
/coin 100000
/debug openalllevel on
/win
```

`/win` 应在进入关卡后使用。

## 存档与日志

存档目录：

```text
~/Library/Application Support/Godot/app_userdata/植物大战僵尸杂交版/
```

启动器日志：

```text
~/Library/Logs/PVZHybrid025/launcher.log
```

更新或重新安装前，建议自行备份存档目录。

## 已知限制

- Apple 芯片设备需要 Rosetta 2
- 当前版本不提供 arm64 原生游戏运行时
- 发行包未经过 Apple 公证
- 联机、更新检查等上游功能可能受网络环境或服务状态影响

## 项目范围

代码仓库保存 macOS 启动器源码、应用元数据和发行说明。完整游戏包通过 GitHub Releases 提供，不纳入 Git 历史。

游戏内容、名称、商标及相关素材的权利归其各自权利人所有。Godot Engine 按 MIT License 分发。本项目仅用于提供 macOS 兼容性支持。
