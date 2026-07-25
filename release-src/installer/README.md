# macOS 安装包

此目录用于生成面向普通用户的 macOS 安装镜像：

```text
植物大战僵尸杂交版v0.25-macOS-Installer.dmg
└── 安装植物大战僵尸杂交版v0.25.pkg
    └── /Applications/植物大战僵尸杂交版v0.25.app
```

安装器不依赖 Windows 或 CrossOver。Apple 芯片 Mac 若尚未安装
Rosetta 2，安装器会通过 macOS“软件更新”服务安装 Apple 官方组件。

## 构建

从已有完整 App 构建：

```sh
release-src/installer/build-installer.sh \
  --app "/path/to/植物大战僵尸杂交版v0.25.app"
```

也可以省略 `--app`。脚本会尝试从仓库的现有 Release ZIP 中提取完整
App。生成物默认写入 `release/installer/`。

## 面向公众发布

正式公开分发应准备以下两张 Apple Developer 证书：

- `Developer ID Application`：签名 App 和 DMG
- `Developer ID Installer`：签名 PKG

然后执行：

```sh
release-src/installer/build-installer.sh \
  --app "/path/to/植物大战僵尸杂交版v0.25.app" \
  --app-sign "Developer ID Application: Example (TEAMID)" \
  --installer-sign "Developer ID Installer: Example (TEAMID)" \
  --notary-profile "notary-profile"
```

`notary-profile` 应提前使用 `xcrun notarytool store-credentials` 保存。
脚本会提交外层 DMG 至 Apple 公证服务，并在成功后附加公证票据。

没有 Developer ID 时仍可生成用于测试的 ad-hoc App 和无签名 PKG，
但 Gatekeeper 会要求用户手动确认，不适合作为最终公开发行物。
