import QtQuick
import QtQuick.Effects
import qs.Commons

Item {
  id: root

  property real iconSize: Style.bar.iconCanvas
  property color statusColor: Color.foreground
  property bool showStatusBadge: true
  property bool monochrome: false
  property bool transparent: false
  property color tintColor: Color.foreground

  // Dark tints crush the two-tone logo to near-black (gray * near-black ~= black).
  // Opaque keeps the original flat tint exactly; transparent just lightens a
  // dark tint so the center/outline grays stay in the same ratio, no glow.
  readonly property real tintLuma: 0.2126 * tintColor.r + 0.7152 * tintColor.g + 0.0722 * tintColor.b
  readonly property bool tintIsDark: tintLuma < 0.5
  readonly property color effectiveTint: (root.monochrome && root.transparent && root.tintIsDark) ? Qt.lighter(root.tintColor, 2.4) : root.tintColor

  width: iconSize
  height: iconSize
  implicitWidth: iconSize
  implicitHeight: iconSize

  Image {
    id: logoImage
    anchors.fill: parent
    source: Qt.resolvedUrl("assets/logo.png")
    fillMode: Image.PreserveAspectFit
    mipmap: true
    smooth: true
    opacity: root.monochrome ? 0 : 1
  }

  MultiEffect {
    anchors.fill: logoImage
    source: logoImage
    opacity: root.monochrome ? 1 : 0
    colorization: 1.0
    colorizationColor: root.effectiveTint
    brightness: (root.monochrome && root.transparent && root.tintIsDark) ? 0.08 : 0.0
    contrast: (root.monochrome && root.transparent && root.tintIsDark) ? -0.25 : 0.0
  }

  Rectangle {
    visible: root.showStatusBadge
    anchors.right: parent.right
    anchors.bottom: parent.bottom
    width: Math.max(4, root.iconSize * 0.28)
    height: width
    radius: width / 2
    color: root.statusColor
  }
}
