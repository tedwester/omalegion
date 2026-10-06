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
  signal commandRequested(var args)

  readonly property var power: d && d.power ? d.power : ({})
  readonly property var custom: power.custom || ({})
  readonly property var caps: d && d.capabilities ? d.capabilities : ({})

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  Text {
    textFormat: Text.PlainText
    text: "Legion Power Mode"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Text {
    textFormat: Text.PlainText
    width: parent.width
    text: {
      var bits = ["Same thermal mode as Fn+Q. Quiet, Balanced, and Performance stay synced with the Omarchy battery profile."]
      if (power.ppd_label)
        bits.push("Battery panel: " + power.ppd_label + ".")
      if (power.ppd_in_sync === false)
        bits.push("Power-profiles-daemon is out of sync — Legion mode is still applied in firmware.")
      return bits.join(" ")
    }
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  Text {
    visible: caps.supports_its_mode === true
    textFormat: Text.PlainText
    width: parent.width
    text: "ITS machine (ThinkBook/IdeaPad class): LLT drives these through the ITS stack (Intelligent Cooling / Battery Saving / Extreme / Geek), not SmartFan modes. Fn+Q behavior stays firmware-owned; the modes above reflect platform_profile where exposed."
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  Repeater {
    model: power.available_modes || []
    delegate: OptionCard {
      required property var modelData
      width: parent.width
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      title: modelData.label
      description: modelData.blocked_on_battery
        ? modelData.desc + " Requires AC power."
        : modelData.desc
      selected: modelData.selected === true
      enabled: !modelData.blocked_on_battery
      actionTip: modelData.blocked_on_battery
        ? "Plug in AC power"
        : (modelData.selected ? "Active" : "Apply " + modelData.label)
      onActivated: root.commandRequested(["--set-power", modelData.profile])
    }
  }

  Column {
    visible: power.supports_custom === true && !!(custom && custom.available)
    width: parent.width
    spacing: Style.space(10)

    Text {
      textFormat: Text.PlainText
      text: "Custom Power (GodMode)"
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: {
        var plat = power.godmode_platform || "legion"
        var base = power.is_custom
          ? "Firmware power limits for Custom mode (" + plat + "). Min/Max come from firmware, like LLT StepperValue. Applies immediately."
          : "Switch to Custom mode to edit firmware power limits."
        if (power.ac_connected === false) base += " Requires AC power."
        return base
      }
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }

    Repeater {
      model: {
        var out = []
        var lims = (custom && custom.limits) || {}
        for (var k in lims) out.push(lims[k])
        out.sort(function(a, b) { return (a.label || "").localeCompare(b.label || "") })
        return out
      }
      delegate: PptLimitCard {
        required property var modelData
        width: parent.width
        limit: modelData || ({})
        enabled: power.is_custom === true && power.ac_connected !== false
        foreground: root.foreground
        dim: root.dim
        accentColor: root.accentColor
        fontFamily: root.fontFamily
        onPicked: function(watts) {
          if (modelData && modelData.id)
            root.commandRequested(["--set-ppt", String(modelData.id), String(watts)])
        }
      }
    }

    Text {
      textFormat: Text.PlainText
      text: "Presets"
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "LLT GodMode presets. Saving stores current firmware values; applying writes them back in Custom mode."
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }

    Repeater {
      model: {
        var out = []
        var presets = power.godmode_presets || {}
        for (var n in presets) out.push({ name: n, values: presets[n], active: power.godmode_active_preset === n })
        return out
      }
      delegate: OptionCard {
        required property var modelData
        width: parent.width
        foreground: root.foreground
        dim: root.dim
        accentColor: root.accentColor
        fontFamily: root.fontFamily
        title: (modelData.active ? "● " : "") + modelData.name
        description: {
          var bits = []
          for (var k in (modelData.values || {})) bits.push(k + "=" + modelData.values[k])
          return bits.slice(0, 3).join(", ") + (bits.length > 3 ? "…" : "")
        }
        selected: modelData.active === true
        actionTip: modelData.active ? "Active" : "Apply preset"
        onActivated: root.commandRequested(["--apply-preset", modelData.name])
      }
    }

    OptionCard {
      visible: power.is_custom === true && !!(custom && custom.limits)
      width: parent.width
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      title: "Save current as new preset"
      description: "Stores live firmware values. Rename/delete via CLI (--save-preset/--delete-preset)."
      selected: false
      actionTip: "Save"
      onActivated: {
        var vals = {}
        var lims = (custom && custom.limits) || {}
        for (var k in lims) {
          if (lims[k] && lims[k].current !== undefined && lims[k].current !== null)
            vals[lims[k].id || k] = lims[k].current
        }
        var existing = power.godmode_presets || {}
        var n = 1
        while (existing["Custom " + n]) n++
        root.commandRequested(["--save-preset", "Custom " + n, JSON.stringify(vals)])
      }
    }

    Repeater {
      model: {
        var out = []
        var presets = power.godmode_presets || {}
        for (var n in presets) out.push(n)
        return out
      }
      delegate: OptionCard {
        required property var modelData
        width: parent.width
        foreground: root.foreground
        dim: root.dim
        accentColor: root.accentColor
        fontFamily: root.fontFamily
        title: "Delete '" + modelData + "'"
        description: "Removes this preset."
        selected: false
        actionTip: "Delete"
        onActivated: root.commandRequested(["--delete-preset", modelData])
      }
    }
  }

  BorderSurface {
    visible: power.supports_custom !== true
    width: parent.width
    implicitHeight: noCustom.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(root.foreground, root.foreground)
    borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)
    radius: Style.cornerRadius

    Column {
      id: noCustom
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        text: "Custom mode unavailable"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: "No firmware power limits exposed (needs lenovo-wmi + Custom in platform_profile_choices). LLT would hide GodMode here too."
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        wrapMode: Text.Wrap
      }
    }
  }

  component PptLimitCard: BorderSurface {
    id: ppt
    property var limit: ({})
    property bool enabled: true
    property color foreground
    property color dim
    property color accentColor
    property string fontFamily
    signal picked(int watts)

    implicitHeight: pptCol.implicitHeight + Style.space(16)
    color: Style.hoverFillFor(foreground, foreground)
    borderSpec: Border.controlSpec("normal", dim, accentColor)
    radius: Style.cornerRadius
    opacity: enabled ? 1 : 0.55

    Column {
      id: pptCol
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.margins: Style.space(8)
      spacing: Style.space(6)

      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: ppt.limit && ppt.limit.label ? ppt.limit.label : ""
        color: ppt.foreground
        font.family: ppt.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        wrapMode: Text.Wrap
        elide: Text.ElideRight
        maximumLineCount: 2
      }

      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: (ppt.limit && ppt.limit.current !== undefined ? ppt.limit.current : "--")
          + (ppt.limit && ppt.limit.unit ? " " + ppt.limit.unit : "")
          + "  ·  "
          + (ppt.limit && ppt.limit.min !== undefined ? ppt.limit.min : "--")
          + "–"
          + (ppt.limit && ppt.limit.max !== undefined ? ppt.limit.max : "--")
          + (ppt.limit && ppt.limit.unit ? " " + ppt.limit.unit : "")
        color: ppt.dim
        font.family: ppt.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
        maximumLineCount: 1
      }

      Row {
        spacing: Style.space(6)

        PptChip {
          label: "Min"
          watts: ppt.limit && ppt.limit.min !== undefined ? ppt.limit.min : -1
          enabled: ppt.enabled
          foreground: ppt.foreground
          dim: ppt.dim
          accentColor: ppt.accentColor
          fontFamily: ppt.fontFamily
          onClicked: if (watts >= 0) ppt.picked(watts)
        }
        PptChip {
          label: "Stock"
          watts: ppt.limit && ppt.limit.default_watts !== undefined ? ppt.limit.default_watts : -1
          enabled: ppt.enabled
          foreground: ppt.foreground
          dim: ppt.dim
          accentColor: ppt.accentColor
          fontFamily: ppt.fontFamily
          onClicked: if (watts >= 0) ppt.picked(watts)
        }
        PptChip {
          label: "Max"
          watts: ppt.limit && ppt.limit.max !== undefined ? ppt.limit.max : -1
          enabled: ppt.enabled
          foreground: ppt.foreground
          dim: ppt.dim
          accentColor: ppt.accentColor
          fontFamily: ppt.fontFamily
          onClicked: if (watts >= 0) ppt.picked(watts)
        }
      }
    }
  }

  component PptChip: BorderSurface {
    id: chip
    property string label: ""
    property int watts: -1
    property bool enabled: true
    property color foreground
    property color dim
    property color accentColor
    property string fontFamily
    signal clicked

    implicitWidth: chipText.implicitWidth + Style.space(14)
    implicitHeight: chipText.implicitHeight + Style.space(8)
    radius: Style.cornerRadius
    color: "transparent"
    borderSpec: Border.controlSpec("normal", dim, accentColor)
    opacity: enabled ? 1 : 0.55

    Text {
      id: chipText
      textFormat: Text.PlainText
      anchors.centerIn: parent
      text: chip.label
      color: chip.foreground
      font.family: chip.fontFamily
      font.pixelSize: Style.font.caption
      font.bold: true
    }

    MouseArea {
      anchors.fill: parent
      enabled: chip.enabled
      cursorShape: Qt.PointingHandCursor
      onClicked: chip.clicked()
    }
  }
}
