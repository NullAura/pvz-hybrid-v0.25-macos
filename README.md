# 植物大战僵尸杂交版 v0.25 for macOS

本项目为《植物大战僵尸杂交版》v0.25 提供非官方 macOS 兼容发行方案。发行包集成运行游戏所需的 Godot 与 .NET 组件，无需安装 Windows 或 CrossOver。

> 本项目与游戏原作者、发行方及相关权利人无隶属或授权关系。

## 下载

请从 [Releases](https://github.com/NullAura/pvz-hybrid-v0.25-macos/releases/latest) 下载以下文件：

- `v0.25-macOS-Installer.dmg`
- `v0.25-macOS-Installer.dmg.sha256`

可在终端中校验文件完整性：

```sh
shasum -a 256 -c v0.25-macOS-Installer.dmg.sha256
```

## 兼容性

| 项目 | 要求 |
| --- | --- |
| 操作系统 | macOS 13 或更高版本 |
| Intel Mac | 原生运行 |
| Apple 芯片 Mac | 通过 Rosetta 2 运行 |
| 游戏架构 | x86_64 |

Rosetta 2 是 Apple 提供的 macOS 官方兼容组件，不是 Windows 或
CrossOver。安装器会自动检测；如尚未安装，将通过 Apple“软件更新”服务安装。

## 安装

1. 打开下载的 DMG。
2. 双击 `安装植物大战僵尸杂交版v0.25.pkg`。
3. 按照 macOS“安装器”中的步骤完成安装。
4. 从“启动台”或“应用程序”文件夹启动游戏。

安装器会检查系统版本、处理器架构、磁盘空间、游戏是否正在运行以及
Rosetta 2 状态。升级安装会替换旧 App，但不会删除用户目录中的存档。

用于公开分发的 DMG、PKG 和 App 应使用 Developer ID 签名并通过 Apple
公证。未签名的测试构建需要在 Finder 中右键安装包并选择“打开”。

## 兼容性调整

- 修正控制台数值参数的解析逻辑，包括 `/coin 100000`
- 恢复游戏内图形指令面板
- 修正 `/debug openalllevel on` 的指令处理
- 支持使用 `/win` 进入正常关卡结算流程
- 修复友方、魅惑及玩家控制的僵尸被计入敌方目标，导致波次或关卡无法结束
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
- 联机、更新检查等上游功能可能受网络环境或服务状态影响

## 构建安装器

安装器构建脚本、双语界面资源、Rosetta 检测逻辑与 Developer ID/公证参数
位于 [`release-src/installer`](release-src/installer/README.md)。

对上游程序集进行兼容性修复的可复现工具及使用方式位于
[`PvzAssemblyPatcher`](.tools/PvzAssemblyPatcher/README.md)。

## 项目范围

代码仓库保存 macOS 启动器源码、应用元数据和发行说明。完整游戏包通过 GitHub Releases 提供，不纳入 Git 历史。

游戏内容、名称、商标及相关素材的权利归其各自权利人所有。Godot Engine 按 MIT License 分发。本项目仅用于提供 macOS 兼容性支持。
