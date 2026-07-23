# 植物大战僵尸杂交版 v0.25 — macOS 兼容版

这是面向 macOS 的非官方兼容发行包。应用内已经包含 Godot 4.7 Stable Mono、.NET 9 x64 运行时和游戏数据，不需要安装 Windows 或 CrossOver。

## 下载

请在仓库右侧的 **Releases** 中下载：

- `v0.25-macOS-Release.zip`
- 对应的 `.sha256` 校验文件

## 系统要求

- macOS 13 或更高版本
- Intel Mac：直接运行
- Apple 芯片 Mac（M1/M2/M3/M4 等）：需要 Rosetta 2

Apple 芯片 Mac 如未安装 Rosetta 2，可在终端运行：

```sh
softwareupdate --install-rosetta
```

## 安装

1. 完整解压下载的 ZIP。
2. 将 `植物大战僵尸杂交版v0.25.app` 拖入“应用程序”。
3. 首次启动时右键应用，选择“打开”，然后再次选择“打开”。
4. 如果系统仍然拦截，请进入“系统设置 → 隐私与安全性”，选择“仍要打开”。

发行包使用临时签名，没有 Apple Developer ID 公证，因此首次启动需要手动确认。

## 已包含的修复

- 修复 `/coin 100000` 金币被写成 0 的问题
- 恢复图形指令面板
- 修复 `/debug openalllevel on`
- 支持 `/win` 按正常结算流程记录当前关卡通关
- 自包含 macOS x86_64 运行环境

## 验证结果

- 从最终 ZIP 解压后通过 macOS 深度签名校验
- 中文及 Unicode 文件名均带 UTF-8 标记
- 冷启动成功并加载 37 张地图
- 不包含打包者的个人存档

## 说明

这是非官方 macOS 兼容包。游戏内容及相关素材的权利归原作者和相应权利人所有；本仓库仅保存兼容启动器源码和发行说明。
