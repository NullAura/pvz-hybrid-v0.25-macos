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

1. 下载并完整解压 `v0.25-macOS-Release.zip`。
2. 将应用拖入“应用程序”文件夹。
3. 首次启动时右键应用并选择“打开”。

当前发行包采用 ad-hoc 签名，未经过 Apple Developer ID 公证。Apple 芯片 Mac 如未安装 Rosetta 2，可执行：

```sh
softwareupdate --install-rosetta
```

### 文件校验

```text
SHA-256: 26c14a194cc7925301ddf1b91745cded3ee5c601821fb97e7fd6ab3230fe47e9
```

本项目与游戏原作者、发行方及相关权利人无隶属或授权关系。游戏内容、名称、商标及相关素材的权利归其各自权利人所有。
