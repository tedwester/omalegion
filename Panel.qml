import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root

  moduleName: "tedwester.legion"
  ipcTarget: "tedwester.legion"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.45)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string enginePath: Qt.resolvedUrl("scripts/legion_engine.py").toString().replace(/^file:\/\//, "")

  property var currentData: null
  property bool isUpdating: false
  property string lastUpdateTime: ""
  property string activeTab: "overview"
  property string notice: ""
  property bool noticeIsError: false

  readonly property var tabList: [
    { label: "Overview", key: "overview" },
    { label: "Power", key: "power" },
    { label: "GPU", key: "gpu" },
    { label: "Battery", key: "battery" },
    { label: "Cooling", key: "cooling" },
    { label: "Misc.", key: "misc" }
  ]

  readonly property bool monochromeBarIcon: setting("monochromeBarIcon", false) === true

  function persistPluginSetting(name, value) {
    if (!root.bar || !root.bar.shell || typeof root.bar.shell.updateEntryInline !== "function") return
    var entry = { id: root.moduleName }
    for (var key in settings) if (key !== "id" && key !== name) entry[key] = settings[key]
    entry[name] = value
    root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function toggleMonochromeBarIcon() {
    persistPluginSetting("monochromeBarIcon", !root.monochromeBarIcon)
  }

  function refresh() {
    if (pollProc.running) return
    root.isUpdating = true
    pollProc.running = true
  }

  function execCommand(args) {
    var tail = []
    if (Array.isArray(args)) {
      for (var i = 0; i < args.length; i++)
        tail.push(String(args[i]))
    } else if (args !== undefined && args !== null) {
      tail.push(String(args))
    }
    controlProc.command = ["python3", root.enginePath].concat(tail)
    controlProc.running = true
  }

  function parseOutput(text) {
    root.isUpdating = false
    if (!text || text.trim() === "") return
    try {
      root.currentData = JSON.parse(text)
      root.lastUpdateTime = root.currentData.timestamp || ""
    } catch (e) {
      console.log("legion JSON parse error:", e)
    }
  }

  function flash(text, isError) {
    root.notice = text
    root.noticeIsError = isError === true
    noticeTimer.interval = 2500
    noticeTimer.restart()
  }

  function copyToClipboard(text) {
    if (!text) return
    Quickshell.execDetached(["wl-copy", "--", text])
    root.notice = "Copied to clipboard"
    root.noticeIsError = false
    noticeTimer.interval = 1200
    noticeTimer.restart()
  }

  Timer {
    id: liveTimer
    interval: 3000
    running: root.opened
    repeat: true
    onTriggered: root.refresh()
  }

  Timer {
    id: noticeTimer
    interval: 2500
    running: false
    repeat: false
    onTriggered: root.notice = ""
  }

  Process {
    id: pollProc
    command: ["python3", root.enginePath]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.parseOutput(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) console.log("legion stderr:", text)
    }
    onExited: function() { root.isUpdating = false }
  }

  Process {
    id: controlProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        if (!text || text.trim() === "") return
        try {
          var res = JSON.parse(text)
          if (res.status === "success") {
            root.flash(res.mode || res.battery_mode || res.message
              || (res.overnight !== undefined ? (res.overnight ? "Overnight charging on" : "Overnight charging off")
              : res.usb_charging !== undefined ? (res.usb_charging ? "Always On USB on" : "Always On USB off")
              : res.fn_lock !== undefined ? (res.fn_lock ? "Fn Lock on" : "Fn Lock off")
              : res.gpu_oc !== undefined ? (res.gpu_oc ? "GPU overclock on" : "GPU overclock off")
              : res.dgpu ? "dGPU suspend requested"
              : res.watts !== undefined ? res.watts + " W"
              : res.percent !== undefined ? "Fan " + res.percent + "%"
              : "Applied")
            )
            Qt.callLater(root.refresh)
          } else if (res.status === "error") {
            root.flash(res.message || "Unable to apply", true)
          }
        } catch (e) {
          console.log("legion control parse error:", e)
        }
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text) console.log("legion control stderr:", text)
    }
  }

  onOpenedChanged: {
    if (opened) {
      root.refresh()
      Qt.callLater(function() {
        if (keyCatcher) keyCatcher.forceActiveFocus()
      })
    }
  }

  Component.onCompleted: root.refresh()

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(520))
    contentHeight: panel.fittedContentHeight(mainLayout.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) {
        if (t === "r" || t === "R") root.refresh()
      }

      Column {
        id: mainLayout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(10)

        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight)

          LegionIcon {
            id: heroIcon
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            iconSize: Style.space(24)
            showStatusBadge: false
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(12)
            anchors.right: heroAction.left
            anchors.rightMargin: Style.space(8)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Row {
              spacing: Style.space(8)
              Text {
                textFormat: Text.PlainText
                text: (root.currentData && root.currentData.system && (root.currentData.system.family || root.currentData.system.product)) || "Legion Toolkit"
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.title
                font.bold: true
                elide: Text.ElideRight
                width: Math.min(implicitWidth, Style.space(260))
              }

              BorderSurface {
                visible: !!(root.currentData && root.currentData.power && root.currentData.power.current_label)
                implicitWidth: modeBadge.implicitWidth + Style.space(8)
                implicitHeight: modeBadge.implicitHeight + Style.space(4)
                anchors.verticalCenter: parent.verticalCenter
                color: "transparent"
                borderSpec: Border.controlSpec("normal", root.foreground, Color.accent)
                radius: Style.cornerRadius

                Text {
                  id: modeBadge
                  textFormat: Text.PlainText
                  anchors.centerIn: parent
                  text: root.currentData && root.currentData.power ? (root.currentData.power.current_label || "") : ""
                  color: Color.accent
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
              }
            }

            Text {
              textFormat: Text.PlainText
              text: {
                var bits = []
                if (root.currentData && root.currentData.system && root.currentData.system.product)
                  bits.push(root.currentData.system.product)
                if (root.lastUpdateTime) bits.push(root.lastUpdateTime)
                return bits.length ? bits.join(" · ") : "Loading hardware…"
              }
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideRight
            }
          }

          Item {
            id: refreshHost
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            width: heroAction.implicitWidth
            height: heroAction.implicitHeight
            transformOrigin: Item.Center

            PanelActionButton {
              id: heroAction
              anchors.fill: parent
              iconText: ""
              tooltipText: root.isUpdating ? "Updating…" : "Refresh ('R')"
              foreground: root.isUpdating ? Color.accent : root.foreground
              onClicked: root.refresh()
            }

            RotationAnimator on rotation {
              running: root.isUpdating
              from: 0
              to: 360
              duration: 900
              loops: Animation.Infinite
              easing.type: Easing.Linear
              onRunningChanged: if (!running) refreshHost.rotation = 0
            }
          }
        }

        BorderSurface {
          visible: root.notice !== ""
          width: parent.width
          implicitHeight: noticeText.implicitHeight + Style.space(12)
          color: "transparent"
          borderSpec: Border.controlSpec("focus", root.noticeIsError ? root.urgent : Color.accent, root.noticeIsError ? root.urgent : Color.accent)
          radius: Style.cornerRadius

          Text {
            id: noticeText
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Style.space(6)
            width: parent.width - Style.space(12)
            text: root.notice
            color: root.noticeIsError ? root.urgent : Color.accent
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            font.bold: true
            wrapMode: Text.Wrap
            horizontalAlignment: Text.AlignHCenter
          }

          MouseArea {
            anchors.fill: parent
            enabled: root.noticeIsError
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: root.copyToClipboard(root.notice)
          }
        }

        Row {
          width: parent.width
          spacing: Style.space(6)

          Repeater {
            model: root.tabList
            delegate: BorderSurface {
              readonly property bool isSelected: root.activeTab === modelData.key
              implicitWidth: tabText.implicitWidth + Style.space(14)
              implicitHeight: tabText.implicitHeight + Style.space(8)
              radius: Style.cornerRadius
              color: isSelected ? Style.selectedFillFor(root.foreground, root.foreground) : "transparent"
              borderSpec: isSelected
                ? Border.controlSpec("selected", Color.accent, Color.accent)
                : Border.controlSpec("normal", root.dim, Color.accent)

              Text {
                id: tabText
                textFormat: Text.PlainText
                anchors.centerIn: parent
                text: modelData.label
                color: isSelected ? root.foreground : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                font.bold: isSelected
              }

              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.activeTab = modelData.key
              }
            }
          }
        }

        PanelSeparator {
          width: parent.width
        }

        OverviewTab {
          visible: root.activeTab === "overview"
          height: visible ? implicitHeight : 0
          width: parent.width
          d: root.currentData
          foreground: root.foreground
          dim: root.dim
          urgent: root.urgent
          fontFamily: root.fontFamily
          run: root.execCommand
        }

        PowerTab {
          visible: root.activeTab === "power"
          height: visible ? implicitHeight : 0
          width: parent.width
          d: root.currentData
          foreground: root.foreground
          dim: root.dim
          urgent: root.urgent
          fontFamily: root.fontFamily
          onCommandRequested: function(args) { root.execCommand(args) }
        }

        GpuTab {
          visible: root.activeTab === "gpu"
          height: visible ? implicitHeight : 0
          width: parent.width
          d: root.currentData
          foreground: root.foreground
          dim: root.dim
          urgent: root.urgent
          fontFamily: root.fontFamily
          run: root.execCommand
        }

        BatteryTab {
          visible: root.activeTab === "battery"
          height: visible ? implicitHeight : 0
          width: parent.width
          d: root.currentData
          foreground: root.foreground
          dim: root.dim
          urgent: root.urgent
          fontFamily: root.fontFamily
          run: root.execCommand
        }

        CoolingTab {
          visible: root.activeTab === "cooling"
          height: visible ? implicitHeight : 0
          width: parent.width
          d: root.currentData
          foreground: root.foreground
          dim: root.dim
          urgent: root.urgent
          fontFamily: root.fontFamily
          run: root.execCommand
        }

        MiscTab {
          visible: root.activeTab === "misc"
          height: visible ? implicitHeight : 0
          width: parent.width
          monochromeBarIcon: root.monochromeBarIcon
          foreground: root.foreground
          dim: root.dim
          fontFamily: root.fontFamily
          onMonochromeBarIconToggled: root.toggleMonochromeBarIcon()
        }

        Text {
          textFormat: Text.PlainText
          width: parent.width
          text: "Press R to refresh · Tab switches panels"
          color: Qt.darker(root.dim, 1.3)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.Wrap
        }
      }
    }
  }
}
