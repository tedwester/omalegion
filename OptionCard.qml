import QtQuick
import qs.Commons
import qs.Ui

BorderSurface {
  id: root

  property string title: ""
  property string description: ""
  property bool selected: false
  property bool enabled: true
  property color foreground: Color.foreground
  property color dim: Qt.darker(foreground, 1.45)
  property color accentColor: Color.accent
  property string fontFamily: Style.font.family
  property string actionIcon: selected ? "" : "󰑕"
  property string actionTip: selected ? "Active" : "Apply " + title

  signal activated

  width: parent ? parent.width : implicitWidth
  implicitHeight: body.implicitHeight + Style.space(14)
  radius: Style.cornerRadius
  color: selected ? Style.selectedFillFor(foreground, foreground) : "transparent"
  borderSpec: selected
    ? Border.controlSpec("selected", accentColor, accentColor)
    : Border.controlSpec("normal", dim, accentColor)
  opacity: enabled ? 1 : 0.55

  MouseArea {
    anchors.fill: parent
    enabled: root.enabled
    cursorShape: Qt.PointingHandCursor
    onClicked: root.activated()
  }

  Column {
    id: body
    anchors.left: parent.left
    anchors.right: applyBtn.left
    anchors.rightMargin: Style.space(8)
    anchors.top: parent.top
    anchors.margins: Style.space(8)
    spacing: Style.space(2)

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: root.title
      color: root.selected ? root.accentColor : root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
      wrapMode: Text.Wrap
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
    }
  }

  PanelActionButton {
    id: applyBtn
    anchors.right: parent.right
    anchors.rightMargin: Style.space(8)
    anchors.verticalCenter: parent.verticalCenter
    iconText: root.actionIcon
    tooltipText: root.actionTip
    foreground: root.selected ? root.accentColor : root.foreground
    enabled: root.enabled
    onClicked: root.activated()
  }
}
