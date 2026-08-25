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

  readonly property var fans: d && d.fans ? d.fans : ({})
  readonly property var thermals: d && d.thermals ? d.thermals : ({})
  readonly property var history: d && d.history ? d.history : ({})
  readonly property var power: d && d.power ? d.power : ({})

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  Grid {
    columns: 2
    width: parent.width
    spacing: Style.space(8)

    Repeater {
      model: {
        var items = []
        if (thermals.cpu_package) items.push({ label: "CPU Package", value: Math.round(thermals.cpu_package) + "°C", temp: thermals.cpu_package })
        if (thermals.gpu_temp) items.push({ label: "GPU", value: Math.round(thermals.gpu_temp) + "°C", temp: thermals.gpu_temp })
        if (thermals.nvme_temp) items.push({ label: "NVMe", value: Math.round(thermals.nvme_temp) + "°C", temp: thermals.nvme_temp })
        if (thermals.memory_temp) items.push({ label: "Memory", value: Math.round(thermals.memory_temp) + "°C", temp: thermals.memory_temp })
        var fanList = fans.fans || []
        if (fanList.length > 0) {
          for (var i = 0; i < fanList.length; i++) {
            var f = fanList[i]
            items.push({
              label: fanList.length > 1 ? ("Fan " + (f.index || (i + 1))) : "Fan",
              value: f.rpm ? f.rpm + " RPM" : "--",
              temp: 0,
              subtitle: f.hwmon_name || ""
            })
          }
        } else {
          items.push({ label: "Fan", value: fans.rpm ? fans.rpm + " RPM" : "--", temp: 0, subtitle: fans.hwmon_name || fans.mode || "" })
        }
        return items
      }
      delegate: StatusCard {
        required property var modelData
        width: (parent.width - parent.spacing) / 2
        foreground: root.foreground
        dim: root.dim
        accentColor: root.accentColor
        fontFamily: root.fontFamily
        label: modelData.label
        value: modelData.value
        subtitle: modelData.subtitle || ""
        valueColor: (modelData.temp || 0) >= 85 ? root.urgent : ((modelData.temp || 0) >= 75 ? root.accentColor : root.foreground)
      }
    }
  }

  BorderSurface {
    width: parent.width
    implicitHeight: Style.space(130)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      anchors.fill: parent
      anchors.margins: Style.space(8)
      spacing: Style.space(4)

      Text {
        textFormat: Text.PlainText
        text: "CPU temperature · Fan RPM"
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
      }

      Canvas {
        id: histCanvas
        width: parent.width
        height: Style.space(85)
        property var temps: history.temps || []
        property var fans: history.fan_rpm || []
        onTempsChanged: requestPaint()
        onFansChanged: requestPaint()

        onPaint: {
          var ctx = getContext("2d")
          ctx.reset()
          var w = width
          var h = height
          ctx.strokeStyle = "rgba(255,255,255,0.06)"
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(0, h * 0.5)
          ctx.lineTo(w, h * 0.5)
          ctx.stroke()

          function draw(values, color, minV, range) {
            if (!values || values.length < 2) return
            ctx.strokeStyle = color
            ctx.lineWidth = 2
            ctx.beginPath()
            var step = w / Math.max(1, values.length - 1)
            for (var i = 0; i < values.length; i++) {
              var norm = Math.max(0, Math.min(1, (values[i] - minV) / range))
              var y = h - (norm * h)
              if (i === 0) ctx.moveTo(0, y)
              else ctx.lineTo(i * step, y)
            }
            ctx.stroke()
          }

          draw(temps, Color.accent.toString(), 30, 60)
          draw(fans, "rgba(255,255,255,0.45)", 0, 5000)
        }
      }
    }
  }

  Grid {
    visible: fans.manual_available === true
    columns: 2
    width: parent.width
    spacing: Style.space(8)

    Repeater {
      model: [
        { label: "Automatic", value: "auto", desc: "EC firmware fan curve." },
        { label: "35% Silent", value: "35", desc: "Quiet desktop airflow." },
        { label: "60% Balanced", value: "60", desc: "Steady cooling for light load." },
        { label: "100% Maximum", value: "100", desc: "Full duty cycle." }
      ]
      delegate: BorderSurface {
        required property var modelData
        width: (parent.width - parent.spacing) / 2
        implicitHeight: fanCol.implicitHeight + Style.space(14)
        radius: Style.cornerRadius
        color: Style.hoverFillFor(root.foreground, root.foreground)
        borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

        Column {
          id: fanCol
          anchors.left: parent.left
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.margins: Style.space(8)
          spacing: Style.space(4)

          Text {
            textFormat: Text.PlainText
            text: modelData.label
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            font.bold: true
          }
          Text {
            textFormat: Text.PlainText
            width: parent.width
            text: modelData.desc
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }
        }

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: {
            if (modelData.value === "auto")
              root.run(["--set-fan-mode", "auto"])
            else
              root.run(["--set-fan-speed", modelData.value])
          }
        }
      }
    }
  }

  BorderSurface {
    visible: fans.has_control === true && fans.manual_available !== true
    width: parent.width
    implicitHeight: customNotice.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      id: customNotice
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        text: "Manual fans require Custom mode"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: "Legion Toolkit only allows manual fan curves in Custom power mode. Switch to Custom on the Power tab."
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }
    }
  }

  BorderSurface {
    visible: fans.has_control !== true
    width: parent.width
    implicitHeight: notice.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      id: notice
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        text: "Manual fan curve unavailable"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: "This kernel exposes fan RPM only. Install the legion-laptop module for PWM curves."
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }
    }
  }
}
