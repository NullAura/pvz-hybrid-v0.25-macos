#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)
APP_NAME="Plants vs. Zombies Hybrid v0.25 English.app"
PRODUCT_VERSION="0.25.0"
COMPONENT_ID="com.pvzhe.hybrid025.macos.en.installer.component"
PKG_NAME="Install Plants vs. Zombies Hybrid v0.25 English.pkg"
DMG_NAME="PVZ-Hybrid-v0.25-English-macOS-Installer.dmg"

APP_SOURCE=""
OUTPUT_DIR="${REPO_ROOT}/release/english-installer"
APP_SIGN_IDENTITY="-"
INSTALLER_SIGN_IDENTITY=""
NOTARY_PROFILE=""
KEEP_WORK=0

usage()
{
    printf '%s\n' \
        "Usage: build-installer.sh [options]" \
        "" \
        "  --app PATH             Complete ${APP_NAME}" \
        "  --output DIR           Output directory (default: release/english-installer)" \
        "  --app-sign IDENTITY    Developer ID Application identity for the app and DMG" \
        "  --installer-sign ID    Developer ID Installer identity for the product package" \
        "  --notary-profile NAME  notarytool keychain profile" \
        "  --keep-work            Keep the temporary build directory" \
        "  -h, --help             Show this help"
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
            printf 'Unknown option: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [ -n "${NOTARY_PROFILE}" ] &&
   { [ "${APP_SIGN_IDENTITY}" = "-" ] || [ -z "${INSTALLER_SIGN_IDENTITY}" ]; }; then
    printf '%s\n' "Notarization requires both Developer ID Application and Developer ID Installer identities." >&2
    exit 2
fi

[ -n "${APP_SOURCE}" ] || {
    printf '%s\n' "Use --app to select the assembled English app." >&2
    exit 2
}

WORK_DIR=$(/usr/bin/mktemp -d /private/tmp/pvz-hybrid-english-installer.XXXXXX)
cleanup()
{
    if [ "${KEEP_WORK}" -eq 1 ]; then
        printf 'Temporary build directory: %s\n' "${WORK_DIR}"
    else
        /usr/bin/find "${WORK_DIR}" -depth -delete
    fi
}
trap cleanup EXIT HUP INT TERM

[ -d "${APP_SOURCE}" ] || { printf 'App does not exist: %s\n' "${APP_SOURCE}" >&2; exit 1; }

required_paths="
Contents/Info.plist
Contents/MacOS/PVZHybridEnglishLauncher
Contents/MacOS/PVZHybridGame
Contents/Resources/PVZHybridGame.pck
Contents/Resources/dotnet-x64/dotnet
Contents/Resources/dotnet-x64/host/fxr/9.0.18/libhostfxr.dylib
Contents/Resources/data_PlantsVsZombies_macos_x86_64/PlantsVsZombies.dll
Contents/Resources/data_PlantsVsZombies_macos_x86_64/libhostfxr.dylib
"
for relative_path in ${required_paths}; do
    [ -e "${APP_SOURCE}/${relative_path}" ] || {
        printf 'App is missing a required component: %s\n' "${relative_path}" >&2
        exit 1
    }
done

bundle_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "${APP_SOURCE}/Contents/Info.plist")
bundle_version=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "${APP_SOURCE}/Contents/Info.plist")
[ "${bundle_id}" = "com.pvzhe.hybrid025.macos.en" ] || {
    printf 'Unexpected app Bundle ID: %s\n' "${bundle_id}" >&2
    exit 1
}
[ "${bundle_version}" = "${PRODUCT_VERSION}" ] || {
    printf 'Unexpected app version: %s\n' "${bundle_version}" >&2
    exit 1
}

PAYLOAD_ROOT="${WORK_DIR}/payload"
APP_STAGE="${PAYLOAD_ROOT}/Applications/${APP_NAME}"
/bin/mkdir -p "${PAYLOAD_ROOT}/Applications"
if ! /bin/cp -cR "${APP_SOURCE}" "${PAYLOAD_ROOT}/Applications/" 2>/dev/null; then
    if [ -e "${APP_STAGE}" ]; then
        /usr/bin/find "${APP_STAGE}" -depth -delete
    fi
    /usr/bin/ditto --noqtn --norsrc -- "${APP_SOURCE}" "${APP_STAGE}"
fi
/usr/bin/find "${APP_STAGE}" -name '.DS_Store' -delete

if /usr/bin/find "${APP_STAGE}" \( \
    -iname '*save*' -o -iname '*userdata*' -o -iname '*crashreport*' \
    -o -iname '*pvzhe_logs*' -o -iname 'launcher.log' \
    \) -print | /usr/bin/grep -q .; then
    printf '%s\n' "Possible user saves or logs were found inside the app; packaging stopped:" >&2
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

COMPONENT_PKG="${WORK_DIR}/PVZHybrid025EnglishComponent.pkg"
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
[ -f "${WORK_DIR}/expanded-product/PVZHybrid025EnglishComponent.pkg/Scripts/preinstall" ]
[ -f "${WORK_DIR}/expanded-product/PVZHybrid025EnglishComponent.pkg/Scripts/postinstall" ]

DMG_STAGE="${WORK_DIR}/dmg"
/bin/mkdir -p "${DMG_STAGE}"
/bin/cp -c "${FINAL_PKG}" "${DMG_STAGE}/${PKG_NAME}" 2>/dev/null ||
    /usr/bin/ditto --noqtn --norsrc -- "${FINAL_PKG}" "${DMG_STAGE}/${PKG_NAME}"
/bin/cp "${SCRIPT_DIR}/DMG-README.txt" "${DMG_STAGE}/Install Guide.txt"

FINAL_DMG="${OUTPUT_DIR}/${DMG_NAME}"
if [ -e "${FINAL_DMG}" ]; then
    /usr/bin/find "${FINAL_DMG}" -delete
fi
/usr/bin/hdiutil create \
    -volname "PVZ Hybrid v0.25 English Installer" \
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

printf '\nBuild complete:\n%s\n%s\n' "${FINAL_PKG}" "${FINAL_DMG}"
if [ "${APP_SIGN_IDENTITY}" = "-" ] || [ -z "${INSTALLER_SIGN_IDENTITY}" ]; then
    printf '%s\n' "This community build is ad-hoc signed and unnotarized because no Apple Developer ID was supplied."
fi
