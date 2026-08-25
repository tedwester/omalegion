import QtQuick
import qs.Commons
import qs.Ui

Column {
  id: root

  property bool monochromeBarIcon: false
  property var d: null
  property color foreground
  property color dim
  property color accentColor: Color.accent
  property string fontFamily

  signal monochromeBarIconToggled()
  signal commandRequested(var args)

  readonly property var input: d && d.input ? d.input : ({})

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  Text {
    textFormat: Text.PlainText
    text: "Appearance"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  ToggleRow {
    width: parent.width
    title: "Monochrome bar icon"
    description: "Tint the bar logo to match other shell icons. The power-mode indicator dot stays colored."
    checked: root.monochromeBarIcon
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    onToggled: root.monochromeBarIconToggled()
  }

  Text {
    textFormat: Text.PlainText
    text: "Input"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  ToggleRow {
    width: parent.width
    title: "Trackpad"
    description: "Same control as the laptop touchpad key — uses Omarchy's touchpad toggle."
    checked: input.enabled === true
    enabled: input.available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    onToggled: root.commandRequested(["--set-touchpad", input.enabled ? "0" : "1"])
  }
}
