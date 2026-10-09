import QtQuick
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

  readonly property var input: d && d.input ? d.input : ({})
  readonly property var touchpad: input.touchpad || ({})
  readonly property var microphone: input.microphone || ({})
  readonly property var speaker: input.speaker || ({})
  readonly property var flip: input.flip_to_start || ({})
  readonly property var instantBoot: input.instant_boot || ({})
  readonly property var itsMode: input.its_mode || ({})

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  Text {
    textFormat: Text.PlainText
    text: "Keyboard & Touchpad"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  ToggleRow {
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Fn Lock"
    description: "When on, F1–F12 act as function keys without holding Fn."
    checked: input.fn_lock === true
    onToggled: root.run(["--set-fn-lock", input.fn_lock ? "0" : "1"])
  }

  ToggleRow {
    visible: touchpad.available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Touchpad"
    description: touchpad.source === "firmware"
      ? "Disables the touchpad in firmware."
      : "Disable the touchpad in Hyprland (re-apply after a Hyprland reload)."
    checked: touchpad.locked !== true
    onToggled: root.run(["--set-touchpad", touchpad.locked ? "0" : "1"])
  }

  Text {
    textFormat: Text.PlainText
    text: "Audio"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  ToggleRow {
    visible: microphone.available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Microphone"
    description: microphone.inputs > 1
      ? ("Mutes all " + microphone.inputs + " capture inputs via PipeWire.")
      : "Mutes the capture input via PipeWire."
    checked: microphone.muted !== true
    onToggled: root.run(["--set-mic-mute", microphone.muted ? "0" : "1"])
  }

  ToggleRow {
    visible: speaker.available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Speakers"
    description: speaker.volume !== undefined && speaker.volume !== null
      ? ("Output volume " + speaker.volume + "%. Mutes all outputs via PipeWire.")
      : "Mutes all outputs via PipeWire."
    checked: speaker.muted !== true
    onToggled: root.run(["--set-speaker-mute", speaker.muted ? "0" : "1"])
  }

  Row {
    visible: speaker.available === true
    spacing: Style.space(6)

    Repeater {
      model: [25, 50, 75, 100]
      delegate: BorderSurface {
        required property var modelData
        implicitWidth: volText.implicitWidth + Style.space(14)
        implicitHeight: volText.implicitHeight + Style.space(8)
        radius: Style.cornerRadius
        color: "transparent"
        borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

        Text {
          id: volText
          textFormat: Text.PlainText
          anchors.centerIn: parent
          text: modelData + "%"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: root.run(["--set-speaker-volume", String(modelData)])
        }
      }
    }
  }

  Text {
    textFormat: Text.PlainText
    text: "Firmware"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  ToggleRow {
    visible: flip.available === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Flip to Start"
    description: "Opening the lid boots the laptop (same UEFI setting as Legion Toolkit)."
    checked: flip.enabled === true
    onToggled: root.run(["--set-flip-to-start", flip.enabled ? "0" : "1"])
  }

  Text {
    textFormat: Text.PlainText
    text: "Not on Linux"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  ToggleRow {
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Instant Boot"
    description: instantBoot.reason || "Firmware-only in Legion Toolkit."
    checked: false
    enabled: false
  }

  ToggleRow {
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "ITS thermal modes"
    description: itsMode.reason || "Needs Windows services; use Power modes."
    checked: false
    enabled: false
  }
}
