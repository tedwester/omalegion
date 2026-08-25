import QtQuick
import qs.Commons
import qs.Ui

BorderSurface {
  id: root

  property string title: ""
  property string description: ""
  property bool checked: false
  property bool enabled: true
  property color foreground: Color.foreground
  property color dim: Qt.darker(foreground, 1.45)
  property color accentColor: Color.accent
  property string fontFamily: Style.font.family

  signal toggled

  width: parent ? parent.width : implicitWidth
  implicitHeight: row.implicitHeight + Style.space(12)
  color: Style.hoverFillFor(foreground, foreground)
  borderSpec: Border.controlSpec("normal", dim, accentColor)
  radius: Style.cornerRadius
  opacity: enabled ? 1 : 0.55

  Item {
    id: row
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    implicitHeight: Math.max(labels.implicitHeight, toggle.implicitHeight)

    Column {
      id: labels
      anchors.left: parent.left
      anchors.right: toggle.left
      anchors.rightMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: root.title
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        elide: Text.ElideRight
        maximumLineCount: 1
      }

      Text {
        visible: root.description !== ""
        textFormat: Text.PlainText
        width: parent.width
        text: root.description
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
        elide: Text.ElideRight
        maximumLineCount: 2
      }
    }

    ToggleSwitch {
      id: toggle
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      checked: root.checked
      foreground: root.foreground
      accent: root.accentColor
      interactive: false
    }
  }

  MouseArea {
    anchors.fill: parent
    enabled: root.enabled
    cursorShape: Qt.PointingHandCursor
    onClicked: root.toggled()
  }
}
