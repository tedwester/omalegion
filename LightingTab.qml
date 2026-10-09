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

  property var selectedKeys: []
  property string paintColor: "red"
  property var keyRows: []

  readonly property var lighting: d && d.lighting ? d.lighting : ({})
  readonly property var kbd: lighting.keyboard || ({})
  readonly property var kbdLast: root.kbd.last || ({})
  readonly property var keymap: kbd.keymap || ({})

  readonly property var keyLabels: ({
    1: "Esc", 2: "F1", 3: "F2", 4: "F3", 5: "F4", 6: "F5", 7: "F6",
    8: "F7", 9: "F8", 10: "F9", 11: "F10", 12: "F11", 13: "F12",
    22: "`", 23: "1", 24: "2", 25: "3", 26: "4", 27: "5", 28: "6",
    29: "7", 30: "8", 31: "9", 32: "0", 33: "-", 34: "=",
    56: "Bksp", 64: "Tab", 66: "Q", 67: "W", 68: "E", 69: "R",
    70: "T", 71: "Y", 72: "U", 73: "I", 74: "O", 75: "P",
    76: "[", 77: "]", 78: "\\",
    85: "Caps", 109: "A", 110: "S", 88: "D", 89: "F", 90: "G",
    113: "H", 114: "J", 91: "K", 92: "L", 93: ";", 95: "'",
    119: "Enter",
    106: "Shift", 130: "Z", 131: "X", 111: "C", 112: "V", 135: "B",
    136: "N", 115: "M", 116: ",", 117: ".", 118: "/",
    141: "Shift", 127: "Ctrl", 128: "Win", 150: "Alt", 152: "",
    154: "Alt", 155: "Fn", 157: "Ctrl", 156: "◀", 159: "▼", 161: "▶"
  })

  readonly property var kbdLayout: root.kbd.layout || ({})
  readonly property bool useLayout: root.kbdLayout.matches === true
  readonly property var layoutName: root.kbdLayout.name || "unknown"

  readonly property var keyWidths: ({
    1: 0.9, 2: 0.9, 3: 0.9, 4: 0.9, 5: 0.9, 6: 0.9, 7: 0.9,
    8: 0.9, 9: 0.9, 10: 0.9, 11: 0.9, 12: 0.9, 13: 0.9,
    14: 0.9, 15: 0.9, 16: 0.9, 17: 0.9, 18: 0.9, 19: 0.9, 20: 0.9,
    22: 0.75, 56: 1.6, 64: 1.4, 76: 1.1, 77: 1.1,
    85: 1.75, 119: 2.0, 106: 2.4, 141: 2.3, 127: 1.2,
    128: 1.0, 150: 1.0, 152: 5.5, 154: 1.0, 155: 1.0, 157: 1.0, 163: 2.0
  })

  function unitWidth(code) {
    return root.keyWidths[code] || 1.0
  }

  readonly property var islandLabels: ({
    38: "Num", 39: "/", 40: "*", 41: "-",
    79: "7", 80: "8", 81: "9", 104: "+",
    121: "4", 123: "5", 124: "6",
    142: "1", 144: "2", 146: "3", 167: "Enter",
    163: "0", 165: "."
  })

  function labelFor(code) {
    var numpad = root.islandLabels[code]
    if (numpad !== undefined) return numpad
    if (root.layoutName !== "ansi" && root.useLayout) return ""
    var label = root.keyLabels[code]
    return label !== undefined ? label : ""
  }

  function syncGrid() {
    if (root.useLayout) {
      if (root.keyRows.length) return
      var display = []
      var rows = root.kbdLayout.rows || []
      for (var r = 0; r < rows.length; r++) {
        var out = []
        for (var c = 0; c < rows[r].length; c++) {
          var code = rows[r][c][1]
          out.push({ code: code, units: rows[r][c][0] / 32.0 })
        }
        display.push(out)
      }
      root.keyRows = display
      return
    }
    var live = (root.keymap && root.keymap.rows) || []
    if (live.length === root.keyRows.length && root.keyRows.length) return
    var fallback = []
    for (var i = 0; i < live.length; i++) {
      var row = []
      var j = 0
      while (j < live[i].length) {
        var cd = live[i][j]
        if (cd <= 0) {
          row.push({ code: 0 })
          j++
          continue
        }
        var n = 1
        while (j + n < live[i].length && live[i][j + n] === cd) n++
        row.push({ code: cd, units: n * (root.unitWidth(cd)) })
        j += n
      }
      while (row.length && row[row.length - 1].code <= 0) row.pop()
      if (row.length) fallback.push(row)
    }
    root.keyRows = fallback
  }

  onDChanged: root.syncGrid()

  function allKeycodes() {
    var out = []
    var rows = root.keymap.rows || []
    for (var r = 0; r < rows.length; r++)
      for (var c = 0; c < rows[r].length; c++)
        if (rows[r][c] > 0) out.push(rows[r][c])
    return out
  }

  function toggleKey(kc) {
    var next = root.selectedKeys.slice()
    var i = next.indexOf(kc)
    if (i >= 0) next.splice(i, 1)
    else next.push(kc)
    root.selectedKeys = next
  }

  function paintSelection() {
    var keys = root.selectedKeys.length ? root.selectedKeys : root.allKeycodes()
    if (!keys.length) return
    root.run(["--set-kbd-keys", keys.join(","), root.paintColor])
  }

  width: parent ? parent.width : implicitWidth
  spacing: Style.space(10)

  Text {
    textFormat: Text.PlainText
    text: "Lighting"
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    font.bold: true
  }

  Text {
    textFormat: Text.PlainText
    width: parent.width
    visible: root.kbd.available !== true
    text: "No controllable keyboard lighting on this machine."
    color: root.dim
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
    wrapMode: Text.Wrap
  }

  Column {
    visible: root.kbd.available === true
    width: parent.width
    spacing: Style.space(6)

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "Keyboard · brightness " + (root.kbd.brightness !== undefined ? root.kbd.brightness : "--")
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
      elide: Text.ElideRight
      maximumLineCount: 1
    }

    ToggleRow {
      foreground: root.foreground
      dim: root.dim
      accentColor: root.accentColor
      fontFamily: root.fontFamily
      title: "Keyboard lighting"
      description: root.kbd.on === true ? "On" : "Off"
      checked: root.kbd.on === true
      onToggled: root.run(["--set-kbd-power", root.kbd.on ? "0" : "1"])
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: [1, 3, 5, 7, 9]
        delegate: BorderSurface {
          required property var modelData
          implicitWidth: kbdLevelText.implicitWidth + Style.space(14)
          implicitHeight: kbdLevelText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.kbd.brightness === modelData ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
          borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

          Text {
            id: kbdLevelText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: String(modelData)
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.run(["--set-kbd-brightness", String(modelData)])
          }
        }
      }
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "Lighting slot (same as Fn+Space)"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: [1, 2, 3, 4, 5, 6]
        delegate: BorderSurface {
          required property var modelData
          implicitWidth: kbdSlotText.implicitWidth + Style.space(14)
          implicitHeight: kbdSlotText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.kbd.profile === modelData ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
          borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

          Text {
            id: kbdSlotText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: String(modelData)
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.run(["--set-kbd-slot", String(modelData)])
          }
        }
      }
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "Per-key color · tap keys, pick a color"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: (root.kbd.colors || [])
        delegate: BorderSurface {
          required property var modelData
          implicitWidth: kbdPaintText.implicitWidth + Style.space(14)
          implicitHeight: kbdPaintText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.paintColor === modelData ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
          borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

          Text {
            id: kbdPaintText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: modelData
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              root.paintColor = modelData
              root.paintSelection()
            }
          }
        }
      }
    }

    Row {
      spacing: Style.space(6)

      Text {
        textFormat: Text.PlainText
        anchors.verticalCenter: parent.verticalCenter
        text: root.selectedKeys.length ? root.selectedKeys.length + " selected" : "Tap keys below"
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }

    Row {
      width: parent.width
      spacing: Style.space(12)

      Column {
        spacing: Style.space(4)

        Repeater {
          model: root.keyRows
          delegate: Row {
            required property var modelData
            property var keyRow: modelData
            spacing: Style.space(4)

            Repeater {
              model: parent.keyRow
            delegate: Item {
              required property var modelData
              property int keycode: modelData.code || 0
              property real units: modelData.units || 0.5
              width: keycode > 0 ? units * Style.space(20) : Style.space(10)
              height: Style.space(22)

                Rectangle {
                  anchors.fill: parent
                  visible: parent.keycode > 0
                  radius: Style.space(4)
                  color: "transparent"
                  border.width: root.selectedKeys.indexOf(parent.keycode) >= 0 ? 2 : 1
                  border.color: root.selectedKeys.indexOf(parent.keycode) >= 0 ? root.accentColor : root.dim
                }

                Text {
                  anchors.centerIn: parent
                  visible: parent.keycode > 0
                  textFormat: Text.PlainText
                  text: root.labelFor(parent.keycode)
                  color: root.selectedKeys.indexOf(parent.keycode) >= 0 ? root.accentColor : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: false
                  elide: Text.ElideRight
                }

                MouseArea {
                  anchors.fill: parent
                  enabled: parent.keycode > 0
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.toggleKey(parent.keycode)
                }
              }
            }
          }
        }
      }

      Column {
        spacing: Style.space(4)

        Item {
          width: Style.space(20)
          height: Style.space(26)
        }

        GridLayout {
        visible: root.useLayout
        columns: 4
        rowSpacing: Style.space(4)
        columnSpacing: Style.space(4)

        Repeater {
          model: (root.kbdLayout && root.kbdLayout.island) || []
          delegate: Item {
            required property var modelData
            property int keycode: modelData.code || 0
            Layout.row: modelData.row || 0
            Layout.column: modelData.col || 0
            Layout.rowSpan: modelData.rowspan || 1
            Layout.columnSpan: modelData.colspan || 1
            Layout.preferredWidth: Style.space(20)
            Layout.preferredHeight: Style.space(22)
            Layout.fillWidth: (modelData.colspan || 1) <= 1
            Layout.fillHeight: (modelData.rowspan || 1) <= 1

            Rectangle {
              anchors.fill: parent
              radius: Style.space(4)
              color: "transparent"
              border.width: root.selectedKeys.indexOf(parent.keycode) >= 0 ? 2 : 1
              border.color: root.selectedKeys.indexOf(parent.keycode) >= 0 ? root.accentColor : root.dim
            }

            Text {
              anchors.centerIn: parent
              textFormat: Text.PlainText
              text: root.labelFor(parent.keycode)
              color: root.selectedKeys.indexOf(parent.keycode) >= 0 ? root.accentColor : root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: false
              elide: Text.ElideRight
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.toggleKey(parent.keycode)
            }
          }
        }
        }
      }
    }

    Row {
      spacing: Style.space(6)

      BorderSurface {
        implicitWidth: selAllText.implicitWidth + Style.space(14)
        implicitHeight: selAllText.implicitHeight + Style.space(8)
        radius: Style.cornerRadius
        color: "transparent"
        borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

        Text {
          id: selAllText
          textFormat: Text.PlainText
          anchors.centerIn: parent
          text: "Select all"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: root.selectedKeys = root.allKeycodes()
        }
      }

      BorderSurface {
        implicitWidth: selClearText.implicitWidth + Style.space(14)
        implicitHeight: selClearText.implicitHeight + Style.space(8)
        radius: Style.cornerRadius
        color: "transparent"
        borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

        Text {
          id: selClearText
          textFormat: Text.PlainText
          anchors.centerIn: parent
          text: "Clear"
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: root.selectedKeys = []
        }
      }
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "Effects"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: (root.kbd.effects || [])
        delegate: BorderSurface {
          required property var modelData
          implicitWidth: kbdEffectText.implicitWidth + Style.space(14)
          implicitHeight: kbdEffectText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.kbdLast.effect === modelData ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
          borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

          Text {
            id: kbdEffectText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: modelData
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.run(["--set-kbd-effect", modelData])
          }
        }
      }
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "Effect speed"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: [1, 2, 3]
        delegate: BorderSurface {
          required property var modelData
          implicitWidth: kbdSpeedText.implicitWidth + Style.space(14)
          implicitHeight: kbdSpeedText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.kbdLast.speed === modelData ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
          borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

          Text {
            id: kbdSpeedText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: String(modelData)
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.run(["--set-kbd-speed", String(modelData)])
          }
        }
      }
    }

    Text {
      textFormat: Text.PlainText
      width: parent.width
      text: "Effect direction"
      color: root.dim
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Flow {
      width: parent.width
      spacing: Style.space(6)

      Repeater {
        model: [["None", 0], ["Up", 1], ["Down", 2], ["Right", 4], ["Left", 3]]
        delegate: BorderSurface {
          required property var modelData
          implicitWidth: kbdDirText.implicitWidth + Style.space(14)
          implicitHeight: kbdDirText.implicitHeight + Style.space(8)
          radius: Style.cornerRadius
          color: root.kbdLast.direction === modelData[1] ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
          borderSpec: Border.controlSpec("normal", root.dim, root.accentColor)

          Text {
            id: kbdDirText
            textFormat: Text.PlainText
            anchors.centerIn: parent
            text: modelData[0]
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
          }

          MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: root.run(["--set-kbd-direction", String(modelData[1])])
          }
        }
      }
    }
  }
}
