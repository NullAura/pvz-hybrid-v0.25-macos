#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)
APP_NAME="植物大战僵尸杂交版v0.25.app"
PRODUCT_VERSION="0.25.0"
COMPONENT_ID="com.pvzhe.hybrid025.macos.installer.component"
PKG_NAME="安装植物大战僵尸杂交版v0.25.pkg"
DMG_NAME="植物大战僵尸杂交版v0.25-macOS-Installer.dmg"

APP_SOURCE=""
OUTPUT_DIR="${REPO_ROOT}/release/installer"
APP_SIGN_IDENTITY="-"
INSTALLER_SIGN_IDENTITY=""
NOTARY_PROFILE=""
KEEP_WORK=0

usage()
{
    printf '%s\n' \
        "用法：build-installer.sh [选项]" \
        "" \
        "  --app PATH             完整的 ${APP_NAME}" \
        "  --output DIR           输出目录（默认：release/installer）" \
        "  --app-sign IDENTITY    App/DMG 的 Developer ID Application 证书" \
        "  --installer-sign ID    PKG 的 Developer ID Installer 证书" \
        "  --notary-profile NAME  notarytool 钥匙串凭据名称" \
        "  --keep-work            保留临时构建目录" \
        "  -h, --help             显示帮助"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --app)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            APP_SOURCE=$2
            shift 2
            ;;
        --output)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            OUTPUT_DIR=$2
            shift 2
            ;;
        --app-sign)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            APP_SIGN_IDENTITY=$2
            shift 2
            ;;
        --installer-sign)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            INSTALLER_SIGN_IDENTITY=$2
            shift 2
            ;;
        --notary-profile)
            [ "$#" -ge 2 ] || { usage >&2; exit 2; }
            NOTARY_PROFILE=$2
            shift 2
            ;;
        --keep-work)
            KEEP_WORK=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf '未知选项：%s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ -n "${NOTARY_PROFILE}" ] &&
   { [ "${APP_SIGN_IDENTITY}" = "-" ] || [ -z "${INSTALLER_SIGN_IDENTITY}" ]; }; then
    printf '%s\n' "公证要求同时提供 Developer ID Application 和 Developer ID Installer 证书。" >&2
    exit 2
fi

WORK_DIR=$(/usr/bin/mktemp -d /private/tmp/pvz-hybrid-installer.XXXXXX)
cleanup()
{
    if [ "${KEEP_WORK}" -eq 1 ]; then
        printf '临时构建目录：%s\n' "${WORK_DIR}"
    else
        /bin/rm -rf -- "${WORK_DIR}"
    fi
}
trap cleanup EXIT HUP INT TERM

find_release_zip()
{
    /usr/bin/find "${REPO_ROOT}/release" -maxdepth 1 -type f \
        -name '*v0.25*macOS*Release.zip' -print 2>/dev/null |
        /usr/bin/head -n 1
}

if [ -z "${APP_SOURCE}" ]; then
    local_app="${REPO_ROOT}/${APP_NAME}"
    if [ -x "${local_app}/Contents/MacOS/PVZHybridGame" ] &&
       [ -f "${local_app}/Contents/Resources/PVZHybridGame.pck" ]; then
        APP_SOURCE=${local_app}
    else
        release_zip=$(find_release_zip)
        if [ -z "${release_zip}" ]; then
            printf '%s\n' "没有找到完整 App。请使用 --app 指定路径。" >&2
            exit 1
        fi
        printf '正在从现有 Release ZIP 提取完整 App：%s\n' "${release_zip}"
        /usr/bin/ditto -x -k -- "${release_zip}" "${WORK_DIR}/release-extract"
        APP_SOURCE=$(/usr/bin/find "${WORK_DIR}/release-extract" -type d \
            -name "${APP_NAME}" -prune -print | /usr/bin/head -n 1)
    fi
fi

[ -d "${APP_SOURCE}" ] || { printf 'App 不存在：%s\n' "${APP_SOURCE}" >&2; exit 1; }

required_paths="
Contents/Info.plist
Contents/MacOS/PVZHybridLauncher
Contents/MacOS/PVZHybridGame
Contents/Resources/PVZHybridGame.pck
Contents/Resources/data_PlantsVsZombies_macos_x86_64/PlantsVsZombies.dll
Contents/Resources/data_PlantsVsZombies_macos_x86_64/libhostfxr.dylib
"
for relative_path in ${required_paths}; do
    [ -e "${APP_SOURCE}/${relative_path}" ] || {
        printf 'App 缺少必要组件：%s\n' "${relative_path}" >&2
        exit 1
    }
done

bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "${APP_SOURCE}/Contents/Info.plist")
bundle_version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${APP_SOURCE}/Contents/Info.plist")
[ "${bundle_id}" = "com.pvzhe.hybrid025.macos" ] || {
    printf 'App Bundle ID 不符合预期：%s\n' "${bundle_id}" >&2
    exit 1
}
[ "${bundle_version}" = "${PRODUCT_VERSION}" ] || {
    printf 'App 版本不符合预期：%s\n' "${bundle_version}" >&2
    exit 1
}

PAYLOAD_ROOT="${WORK_DIR}/payload"
APP_STAGE="${PAYLOAD_ROOT}/Applications/${APP_NAME}"
/bin/mkdir -p "${PAYLOAD_ROOT}/Applications"
/usr/bin/ditto --noqtn --norsrc -- "${APP_SOURCE}" "${APP_STAGE}"
/usr/bin/find "${APP_STAGE}" -name '.DS_Store' -delete

if /usr/bin/find "${APP_STAGE}" \( \
    -iname '*save*' -o -iname '*userdata*' -o -iname '*crashreport*' \
    -o -iname '*pvzhe_logs*' -o -iname 'launcher.log' \
    \) -print | /usr/bin/grep -q .; then
    printf '%s\n' "App 内发现疑似用户存档或日志，已停止打包：" >&2
    /usr/bin/find "${APP_STAGE}" \( \
        -iname '*save*' -o -iname '*userdata*' -o -iname '*crashreport*' \
        -o -iname '*pvzhe_logs*' -o -iname 'launcher.log' \
        \) -print >&2
    exit 1
fi

if [ "${APP_SIGN_IDENTITY}" = "-" ]; then
    /usr/bin/codesign --force --deep --sign - "${APP_STAGE}"
else
    /usr/bin/codesign --force --deep --options runtime --timestamp \
        --sign "${APP_SIGN_IDENTITY}" "${APP_STAGE}"
fi

/usr/bin/codesign --verify --deep --strict --verbose=2 "${APP_STAGE}"

/bin/cp "${SCRIPT_DIR}/Component.plist" "${WORK_DIR}/Component.plist"
/usr/bin/xmllint --noout "${SCRIPT_DIR}/Distribution.xml"
/usr/bin/plutil -lint "${WORK_DIR}/Component.plist" >/dev/null
/bin/chmod 755 "${SCRIPT_DIR}/scripts/preinstall" "${SCRIPT_DIR}/scripts/postinstall"

COMPONENT_PKG="${WORK_DIR}/PVZHybrid025Component.pkg"
/usr/bin/pkgbuild \
    --root "${PAYLOAD_ROOT}" \
    --component-plist "${WORK_DIR}/Component.plist" \
    --scripts "${SCRIPT_DIR}/scripts" \
    --identifier "${COMPONENT_ID}" \
    --version "${PRODUCT_VERSION}" \
    --install-location "/" \
    --ownership recommended \
    --compression latest \
    --min-os-version 13.0 \
    "${COMPONENT_PKG}"

/bin/mkdir -p "${OUTPUT_DIR}"
FINAL_PKG="${OUTPUT_DIR}/${PKG_NAME}"
if [ -n "${INSTALLER_SIGN_IDENTITY}" ]; then
    /usr/bin/productbuild \
        --distribution "${SCRIPT_DIR}/Distribution.xml" \
        --resources "${SCRIPT_DIR}/resources" \
        --package-path "${WORK_DIR}" \
        --sign "${INSTALLER_SIGN_IDENTITY}" \
        --timestamp \
        "${FINAL_PKG}"
else
    /usr/bin/productbuild \
        --distribution "${SCRIPT_DIR}/Distribution.xml" \
        --resources "${SCRIPT_DIR}/resources" \
        --package-path "${WORK_DIR}" \
        "${FINAL_PKG}"
fi

/usr/sbin/pkgutil --check-signature "${FINAL_PKG}" || true
/usr/sbin/pkgutil --expand "${FINAL_PKG}" "${WORK_DIR}/expanded-product"
/usr/bin/xmllint --noout "${WORK_DIR}/expanded-product/Distribution"
[ -f "${WORK_DIR}/expanded-product/PVZHybrid025Component.pkg/Scripts/preinstall" ]
[ -f "${WORK_DIR}/expanded-product/PVZHybrid025Component.pkg/Scripts/postinstall" ]

DMG_STAGE="${WORK_DIR}/dmg"
/bin/mkdir -p "${DMG_STAGE}"
/usr/bin/ditto --noqtn --norsrc -- "${FINAL_PKG}" "${DMG_STAGE}/${PKG_NAME}"
/bin/cp "${SCRIPT_DIR}/DMG-README.txt" "${DMG_STAGE}/安装说明.txt"

FINAL_DMG="${OUTPUT_DIR}/${DMG_NAME}"
/bin/rm -f -- "${FINAL_DMG}"
/usr/bin/hdiutil create \
    -volname "安装 植物大战僵尸杂交版 v0.25" \
    -srcfolder "${DMG_STAGE}" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -ov \
    "${FINAL_DMG}"

if [ "${APP_SIGN_IDENTITY}" != "-" ]; then
    /usr/bin/codesign --force --timestamp --sign "${APP_SIGN_IDENTITY}" "${FINAL_DMG}"
fi

if [ -n "${NOTARY_PROFILE}" ]; then
    /usr/bin/xcrun notarytool submit "${FINAL_DMG}" \
        --keychain-profile "${NOTARY_PROFILE}" --wait
    /usr/bin/xcrun stapler staple "${FINAL_DMG}"
    /usr/bin/xcrun stapler validate "${FINAL_DMG}"
fi

/usr/bin/hdiutil verify "${FINAL_DMG}"

(
    cd "${OUTPUT_DIR}"
    /usr/bin/shasum -a 256 "${PKG_NAME}" > "${PKG_NAME}.sha256"
    /usr/bin/shasum -a 256 "${DMG_NAME}" > "${DMG_NAME}.sha256"
)

printf '\n构建完成：\n%s\n%s\n' "${FINAL_PKG}" "${FINAL_DMG}"
if [ "${APP_SIGN_IDENTITY}" = "-" ] || [ -z "${INSTALLER_SIGN_IDENTITY}" ]; then
    printf '%s\n' "注意：这是未公证测试版；公开分发前请使用 Developer ID 签名并公证。"
fi
