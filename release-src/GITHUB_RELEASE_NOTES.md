## 植物大战僵尸杂交版 v0.25 — macOS Release

本 Release 为《植物大战僵尸杂交版》v0.25 提供非官方 macOS 兼容发行包，无需安装 Windows 或 CrossOver。

### 系统要求

- macOS 13 或更高版本
- Intel Mac 可直接运行
- Apple 芯片 Mac 需要 Rosetta 2

### 兼容性调整

- 修正控制台数值参数解析，包括 `/coin 100000`
- 恢复游戏内图形指令面板
- 修正 `/debug openalllevel on`
- 支持使用 `/win` 进入正常关卡结算流程
- 集成 Godot 4.7 Stable Mono 与 .NET 9 x64 运行环境

### 安装说明

1. 下载并打开 `植物大战僵尸杂交版v0.25-macOS-Installer.dmg`。
2. 双击 `安装植物大战僵尸杂交版v0.25.pkg`。
3. 按照 macOS“安装器”完成安装。
4. 从“启动台”或“应用程序”文件夹启动游戏。

安装器会检查 macOS 版本、处理器架构、磁盘空间、游戏运行状态和 Rosetta
2。Apple 芯片 Mac 如缺少 Rosetta 2，安装器会通过 Apple“软件更新”服务
完成安装；整个过程不依赖 Windows 或 CrossOver。

升级安装不会删除用户目录中的游戏存档。

### macOS 安全提示

当前构建尚未使用 Developer ID 签名和 Apple 公证。首次打开安装包时，
macOS 可能阻止运行；请在尝试打开后前往“系统设置 → 隐私与安全性”，
点击“仍要打开”。公司或学校管理的 Mac 可能不允许安装未公证的软件。

### 文件校验

```sh
shasum -a 256 -c 植物大战僵尸杂交版v0.25-macOS-Installer.dmg.sha256
```

本项目与游戏原作者、发行方及相关权利人无隶属或授权关系。游戏内容、名称、商标及相关素材的权利归其各自权利人所有。
