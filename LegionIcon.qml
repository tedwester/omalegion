import QtQuick
import QtQuick.Effects
import qs.Commons

Item {
  id: root

  property real iconSize: Style.bar.iconCanvas
  property color statusColor: Color.foreground
  property bool showStatusBadge: true
  property bool monochrome: false
  property color tintColor: Color.foreground

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
    colorizationColor: root.tintColor
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
