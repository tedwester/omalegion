import QtQuick
import qs.Commons
import qs.Ui

Column {
  id: root

  property var d: ({})
  property bool monochromeBarIcon: false
  property color foreground
  property color dim
  property color accentColor: Color.accent
  property string fontFamily
  property var run

  signal monochromeBarIconToggled()

  readonly property var display: d && d.display ? d.display : ({})
  readonly property var lighting: d && d.lighting ? d.lighting : ({})
  readonly property var boot: d && d.boot ? d.boot : ({})
  readonly property var caps: d && d.capabilities ? d.capabilities : ({})

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
    visible: display.brightness_available === true
    textFormat: Text.PlainText
    text: "Display"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  ToggleRow {
    visible: display.brightness_available === true
    width: parent.width
    title: "Display brightness · " + (display.brightness !== undefined && display.brightness !== null ? display.brightness + "%" : "--")
    description: "Internal panel via sysfs backlight, else brightnessctl/ddcutil. LLT DisplayBrightness 0–100."
    checked: (display.brightness || 0) >= 50
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    onToggled: root.run(["--set-brightness", String((display.brightness || 50) >= 50 ? 30 : 80)])
  }

  Text {
    visible: (display.panels || []).length > 0
    textFormat: Text.PlainText
    width: parent.width
    text: {
      var panels = display.panels || []
      return panels.filter(function(p) { return p.status === "connected" }).map(function(p) {
        return p.connector + (p.current_mode ? " · " + p.current_mode : "")
      }).join("\n") || "No connected outputs detected."
    }
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  Text {
    textFormat: Text.PlainText
    text: "Lighting"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  ToggleRow {
    visible: lighting.ylogo && lighting.ylogo.supported === true
    width: parent.width
    title: "Y-logo light"
    description: "LLT PanelLogo via legion-laptop ylogo_light."
    checked: lighting.ylogo.enabled === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    onToggled: root.run(["--set-logo-light", lighting.ylogo.enabled ? "0" : "1"])
  }

  ToggleRow {
    visible: lighting.ports && lighting.ports.supported === true
    width: parent.width
    title: "Ports backlight"
    description: "LLT PortsBacklight via legion-laptop ioport_light."
    checked: lighting.ports.enabled === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    onToggled: root.run(["--set-ports-light", lighting.ports.enabled ? "0" : "1"])
  }

  Text {
    textFormat: Text.PlainText
    width: parent.width
    text: "RGB 4-zone / Spectrum per-key / LampArray are HID-proprietary (LLT RGB/Spectrum controllers). Unsupported on Linux — use OpenRGB where your model is supported."
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  Text {
    textFormat: Text.PlainText
    text: "Device"
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  Text {
    textFormat: Text.PlainText
    width: parent.width
    text: {
      var bits = []
      if (caps.series) bits.push(String(caps.series).replace(/_/g, " "))
      if (caps.generation) bits.push("Gen " + caps.generation)
      if (caps.godmode_platform) bits.push("Custom:" + caps.godmode_platform)
      if (caps.has_legion_module) bits.push("legion-laptop")
      return bits.length ? bits.join(" · ") : "Probing capabilities…"
    }
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }
}
