import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Column {
  id: root

  property var d: ({})
  property color foreground
  property color dim
  property color urgent
  property color accentColor: Color.accent
  property string fontFamily
  property var run

  readonly property var power: d && d.power ? d.power : ({})
  readonly property var thermals: d && d.thermals ? d.thermals : ({})
  readonly property var fans: d && d.fans ? d.fans : ({})
  readonly property var gpu: d && d.gpu ? d.gpu : ({})
  readonly property var battery: d && d.battery ? d.battery : ({})
  readonly property var input: d && d.input ? d.input : ({})

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  GridLayout {
    columns: 2
    width: parent.width
    columnSpacing: Style.space(8)
    rowSpacing: Style.space(8)

    StatusCard {
      Layout.fillWidth: true
      Layout.fillHeight: true
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      label: "Power Mode"
      value: power.current_label || "--"
      subtitle: power.ppd_label ? ("Omarchy · " + power.ppd_label) : (power.ppd ? ("Omarchy · " + power.ppd) : (power.source || ""))
    }

    StatusCard {
      Layout.fillWidth: true
      Layout.fillHeight: true
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      label: "CPU"
      value: thermals.cpu_package ? Math.round(thermals.cpu_package) + "°C" : "--"
      valueColor: (thermals.cpu_package || 0) >= 90 ? root.urgent : ((thermals.cpu_package || 0) >= 80 ? root.accentColor : root.foreground)
      subtitle: d && d.system && d.system.cpu_model ? d.system.cpu_model.replace("Intel(R) Core(TM) ", "") : ""
    }

    StatusCard {
      Layout.fillWidth: true
      Layout.fillHeight: true
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      label: "Fan"
      value: fans.rpm ? fans.rpm + " RPM" : "--"
      subtitle: fans.mode ? (fans.mode.charAt(0).toUpperCase() + fans.mode.slice(1)) : ""
    }

    StatusCard {
      Layout.fillWidth: true
      Layout.fillHeight: true
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      label: "GPU"
      value: gpu.temp ? Math.round(gpu.temp) + "°C" : (gpu.status || "--")
      subtitle: gpu.working_label ? (gpu.working_label + (gpu.name ? " · " + gpu.name : "")) : (gpu.name || "")
    }
  }

  BorderSurface {
    width: parent.width
    implicitHeight: batCol.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      id: batCol
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(6)

      Item {
        width: parent.width
        implicitHeight: batLabel.implicitHeight

        Text {
          id: batLabel
          textFormat: Text.PlainText
          text: "Battery"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }

        Text {
          anchors.right: parent.right
          anchors.left: batLabel.right
          anchors.leftMargin: Style.space(8)
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          horizontalAlignment: Text.AlignRight
          text: (battery.ac_connected ? "Plugged in · " : "On battery · ") + (battery.mode_label || "") + " · " + (battery.percent !== undefined && battery.percent !== null ? battery.percent + "%" : "--")
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
          wrapMode: Text.Wrap
          elide: Text.ElideRight
          maximumLineCount: 2
        }
      }

      Rectangle {
        width: parent.width
        height: Style.space(6)
        radius: Style.cornerRadius
        color: Qt.darker(root.dim, 2.0)

        Rectangle {
          width: parent.width * Math.min(1.0, (battery.percent || 0) / 100.0)
          height: parent.height
          radius: Style.cornerRadius
          color: (battery.percent || 100) <= 15 ? root.urgent : ((battery.percent || 100) <= 30 ? root.accentColor : "#87c095")
        }
      }
    }
  }

  ToggleRow {
    visible: input.fn_lock_available !== false
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Fn Lock"
    description: "When on, F1–F12 act as function keys without holding Fn."
    checked: input.fn_lock === true
    onToggled: root.run(["--set-fn-lock", input.fn_lock ? "0" : "1"])
  }

  Repeater {
    model: input.backlight_levels || []
    delegate: OptionCard {
      required property var modelData
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      title: "Keyboard backlight · " + modelData.label
      description: "LLT WhiteKeyboard Off/Low/High via leds."
      selected: modelData.selected === true
      onActivated: root.run(["--set-backlight", String(modelData.id)])
    }
  }

  ToggleRow {
    visible: input.touchpad_available === true && input.touchpad_enabled !== undefined && input.touchpad_enabled !== null
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Touchpad"
    description: "LLT TouchpadLock via gsettings/hyprctl."
    checked: input.touchpad_enabled === true
    onToggled: root.run(["--set-touchpad", input.touchpad_enabled ? "0" : "1"])
  }

  ToggleRow {
    visible: input.mic_available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Microphone mute"
    description: "LLT Microphone mute via wpctl/pactl."
    checked: input.mic_muted === true
    onToggled: root.run(["--set-mic-mute", input.mic_muted ? "0" : "1"])
  }

  ToggleRow {
    visible: input.speaker_available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Speaker mute"
    description: "LLT Speaker mute" + (input.speaker_volume !== undefined && input.speaker_volume !== null ? " · " + input.speaker_volume + "%" : "") + " via wpctl/pactl."
    checked: input.speaker_muted === true
    onToggled: root.run(["--set-speaker-mute", input.speaker_muted ? "0" : "1"])
  }
}
