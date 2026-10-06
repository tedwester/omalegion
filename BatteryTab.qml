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

  readonly property var battery: d && d.battery ? d.battery : ({})
  readonly property var modes: battery.available_modes || []

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  BorderSurface {
    width: parent.width
    implicitHeight: hero.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      id: hero
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(6)

      Text {
        textFormat: Text.PlainText
        text: "Battery"
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }

      Item {
        width: parent.width
        implicitHeight: Math.max(pct.implicitHeight, meta.implicitHeight)

        Text {
          id: pct
          textFormat: Text.PlainText
          text: (battery.percent !== undefined && battery.percent !== null) ? battery.percent + "%" : "--"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.displayLarge
          font.bold: true
        }

        Column {
          id: meta
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          width: Math.max(Style.space(80), parent.width - pct.implicitWidth - Style.space(12))
          spacing: Style.space(2)

          Text {
            textFormat: Text.PlainText
            width: parent.width
            text: battery.status || "Unknown"
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignRight
            elide: Text.ElideRight
            maximumLineCount: 1
          }
          Text {
            textFormat: Text.PlainText
            text: battery.ac_connected ? "Plugged in" : "On battery"
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            horizontalAlignment: Text.AlignRight
          }
        }
      }

      Rectangle {
        width: parent.width
        height: Style.space(8)
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

  Text {
    textFormat: Text.PlainText
    text: "Battery Mode"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Repeater {
    model: root.modes
    delegate: OptionCard {
      required property var modelData
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      title: modelData.label
      description: modelData.desc
      selected: modelData.selected === true
      enabled: modelData.available !== false
      onActivated: root.run(["--set-battery-mode", modelData.id])
    }
  }

  ToggleRow {
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Overnight Battery Charging"
    description: battery.overnight_active
      ? ("Holding conservation overnight (" + (battery.overnight_start ?? 22) + ":00–" + (battery.overnight_end ?? 7) + ":00). Software hold while running — LLT firmware Night Charge persists without OS.")
      : ("Holds Long_Life " + (battery.overnight_start ?? 22) + ":00–" + (battery.overnight_end ?? 7) + ":00 while running. Firmware Night Charge is a Windows EnergyDrv IOCTL.")
    checked: battery.overnight === true
    onToggled: root.run(["--set-overnight", battery.overnight ? "0" : "1"])
  }

  Text {
    visible: (battery.usb_modes || []).length > 0
    textFormat: Text.PlainText
    text: "Always On USB"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Text {
    visible: (battery.usb_modes || []).length > 0
    textFormat: Text.PlainText
    width: parent.width
    text: battery.usb_supports_always
      ? "LLT 3-state: Off / On-when-sleeping / On-always."
      : "This firmware exposes Off / On-when-sleeping only (ideapad_acpi). LLT OnAlways needs EnergyDrv."
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  Repeater {
    model: battery.usb_modes || []
    delegate: OptionCard {
      required property var modelData
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      title: modelData.label
      description: modelData.desc
      selected: modelData.selected === true
      onActivated: root.run(["--set-usb-mode", modelData.id])
    }
  }

  GridLayout {
    columns: 2
    width: parent.width
    columnSpacing: Style.space(8)
    rowSpacing: Style.space(8)

    Repeater {
      model: [
        { label: "Capacity", value: battery.capacity_wh ? battery.capacity_wh + " Wh" : "--" },
        { label: "Design", value: battery.design_wh ? battery.design_wh + " Wh" : "--" },
        { label: "Health", value: battery.health_percent ? battery.health_percent + "%" : "--" },
        { label: "Cycles", value: battery.cycle_count !== undefined && battery.cycle_count !== null ? String(battery.cycle_count) : "--" },
        { label: "Voltage", value: battery.voltage_now ? battery.voltage_now + " V" : "--" },
        { label: "Power", value: battery.power_now_w !== undefined && battery.power_now_w !== null ? battery.power_now_w + " W" : "--" },
        { label: "Temp", value: battery.temp_c !== undefined && battery.temp_c !== null ? battery.temp_c + "°C" : "--" },
        { label: "Cell", value: battery.model || battery.technology || "Li-poly" }
      ]
      delegate: StatusCard {
        required property var modelData
        Layout.fillWidth: true
        Layout.fillHeight: true
        foreground: root.foreground
        dim: root.dim
        accentColor: root.accentColor
        fontFamily: root.fontFamily
        label: modelData.label
        value: modelData.value
      }
    }
  }

  Text {
    visible: d && d.boot && (d.boot.flip_to_start ? d.boot.flip_to_start.supported : false)
    textFormat: Text.PlainText
    text: "Boot"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  ToggleRow {
    visible: d && d.boot && d.boot.flip_to_start && d.boot.flip_to_start.supported === true
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Flip To Start"
    description: "Boot by opening the lid (UEFI FBSWIF). LLT FlipToStart."
    checked: d.boot.flip_to_start.enabled === true
    onToggled: root.run(["--set-flip-to-start", d.boot.flip_to_start.enabled ? "0" : "1"])
  }
}
