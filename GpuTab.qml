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

  readonly property var gpu: d && d.gpu ? d.gpu : ({})
  readonly property var modes: gpu.working_modes || []
  readonly property var processes: gpu.processes || []

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  Text {
    textFormat: Text.PlainText
    text: "GPU Working Mode"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Text {
    textFormat: Text.PlainText
    width: parent.width
    text: gpu.working_note || "Hybrid uses the iGPU for the panel and wakes the dGPU on demand."
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
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
      enabled: modelData.selected === true || modelData.switchable === true
      actionTip: modelData.selected ? "Active" : "Requires BIOS reboot on this kernel"
      onActivated: root.run(["--set-gpu-mode", modelData.id])
    }
  }

  Text {
    textFormat: Text.PlainText
    text: "Discrete GPU"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  BorderSurface {
    width: parent.width
    implicitHeight: dgpuCol.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      id: dgpuCol
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(6)

      Item {
        width: parent.width
        implicitHeight: dgpuName.implicitHeight

        Text {
          id: dgpuName
          textFormat: Text.PlainText
          width: parent.width - (dgpuBadge.visible ? dgpuBadge.implicitWidth + Style.space(8) : 0)
          text: gpu.name || "NVIDIA GPU"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
          elide: Text.ElideRight
        }

        BorderSurface {
          id: dgpuBadge
          visible: !!gpu.status
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          implicitWidth: badgeText.implicitWidth + Style.space(8)
          implicitHeight: badgeText.implicitHeight + Style.space(4)
          color: "transparent"
          borderSpec: Border.controlSpec("normal", root.foreground, root.accentColor)
          radius: Style.cornerRadius

          Text {
            id: badgeText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: gpu.status || ""
            color: root.accentColor
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }
        }
      }

      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: {
          var bits = []
          if (gpu.pstate) bits.push(gpu.pstate)
          if (gpu.power_state) bits.push(gpu.power_state)
          if (gpu.runtime) bits.push(gpu.runtime)
          if (gpu.temp) bits.push(Math.round(gpu.temp) + "°C")
          if (gpu.utilization !== undefined && gpu.utilization !== null) bits.push(gpu.utilization + "%")
          if (gpu.power_draw_w) bits.push(gpu.power_draw_w + " W")
          return bits.length ? bits.join(" · ") : "Waiting for telemetry"
        }
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }

      Text {
        visible: gpu.external_display === true
        textFormat: Text.PlainText
        width: parent.width
        text: "External display connected on dGPU — disconnect it before deactivating."
        color: root.urgent
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }

      Column {
        visible: root.processes.length > 0
        width: parent.width
        spacing: Style.space(2)

        Text {
          textFormat: Text.PlainText
          text: "Processes on dGPU"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        Repeater {
          model: root.processes
          delegate: Text {
            required property var modelData
            textFormat: Text.PlainText
            width: parent.width
            text: modelData.name + " · PID " + modelData.pid + (modelData.mem_mb ? " · " + modelData.mem_mb + " MiB" : "")
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            elide: Text.ElideRight
          }
        }
      }

      Row {
        spacing: Style.space(8)
        anchors.right: parent.right

        PanelActionButton {
          visible: gpu.can_kill_processes === true && gpu.can_deactivate !== true && root.processes.length > 0
          iconText: "󰅖"
          tooltipText: "End dGPU apps and deactivate"
          foreground: root.urgent
          onClicked: root.run(["--deactivate-dgpu", "force"])
        }

        PanelActionButton {
          visible: gpu.can_deactivate === true
          iconText: "󰐥"
          tooltipText: root.processes.length > 0 ? "End dGPU apps and deactivate" : "Deactivate dGPU"
          foreground: root.accentColor
          onClicked: root.run(root.processes.length > 0
            ? ["--deactivate-dgpu", "force"]
            : ["--deactivate-dgpu"])
        }
      }
    }
  }

  ToggleRow {
    foreground: root.foreground
    dim: root.dim
    accentColor: root.accentColor
    fontFamily: root.fontFamily
    title: "Overclock GPU"
    description: gpu.overclock_available
      ? "Locks NVIDIA core clocks to the firmware maximum while the dGPU is awake."
      : "Saved for the next time the dGPU wakes. Enable GPU OC in BIOS if nothing changes."
    checked: gpu.overclock === true
    onToggled: root.run(["--set-gpu-oc", gpu.overclock ? "0" : "1"])
  }
}
