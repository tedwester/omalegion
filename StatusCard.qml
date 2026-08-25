import QtQuick
import qs.Commons
import qs.Ui

BorderSurface {
  id: root

  property string label: ""
  property string value: "--"
  property string subtitle: ""
  property color foreground: Color.foreground
  property color dim: Qt.darker(foreground, 1.45)
  property color valueColor: foreground
  property color accentColor: Color.accent
  property string fontFamily: Style.font.family

  color: Style.hoverFillFor(foreground, foreground)
  borderSpec: Border.controlSpec("normal", dim, accentColor)
  radius: Style.cornerRadius
  implicitHeight: col.implicitHeight + Style.space(16)

  Column {
    id: col
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    spacing: Style.space(4)

    Text {
      textFormat: Text.PlainText
      text: root.label
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: root.value
      color: root.valueColor
      font.family: root.fontFamily
      font.pixelSize: Style.font.title
      font.bold: true
      elide: Text.ElideRight
    }

    Text {
      visible: root.subtitle !== ""
      textFormat: Text.PlainText
      width: parent.width
      text: root.subtitle
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }
  }
}
