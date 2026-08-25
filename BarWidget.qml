import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "tedwester.legion"

  readonly property var panelItem: panelLoader.item
  readonly property bool opened: panelItem ? panelItem.opened === true : false
  readonly property bool popoutSwitchClosing: panelItem
    ? panelItem.popoutSwitchClosing === true
    : false

  function injectPanel() {
    var target = panelItem
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  function open() {
    if (panelItem) panelItem.open()
  }

  function close() {
    if (panelItem) panelItem.close()
  }

  function toggle() {
    if (panelItem) panelItem.toggle()
  }

  function togglePanel() {
    root.toggle()
  }

  function refresh() {
    if (panelItem && panelItem.refresh) panelItem.refresh()
  }

  function closeForPopoutSwitch() {
    if (panelItem) panelItem.closeForPopoutSwitch()
  }

  function statusColor() {
    var data = panelItem ? panelItem.currentData : null
    if (!data) return root.bar ? root.bar.barForeground : Color.foreground
    var temp = data.thermals && data.thermals.cpu_package ? data.thermals.cpu_package : 0
    var mode = data.power && data.power.current_id ? data.power.current_id : ""
    if (temp >= 90) return root.bar ? root.bar.urgent : Color.urgent
    if (mode === "performance" || mode === "extreme") return Color.accent
    if (mode === "quiet") return "#87c095"
    return root.bar ? root.bar.barForeground : Color.foreground
  }

  function tooltipText() {
    if (!panelItem || !panelItem.currentData) return "Legion Toolkit"
    var p = panelItem.currentData.power || {}
    var t = panelItem.currentData.thermals || {}
    var mode = p.current_label || "Unknown"
    var temp = t.cpu_package ? Math.round(t.cpu_package) + "°C" : "--"
    var ppd = p.ppd_label || p.ppd || ""
    return ppd ? ("Legion · " + mode + " · " + ppd + " · " + temp) : ("Legion · " + mode + " · " + temp)
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
      Qt.callLater(root.refresh)
    }
  }

  Timer {
    interval: 8000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "Legion"
    fontSize: Style.font.bodySmall
    active: root.opened
    tooltipText: root.tooltipText()
    horizontalMargin: 8
    foreground: root.statusColor()

    onPressed: function(b) {
      if (!root.bar) return
      if (b === Qt.MiddleButton) root.refresh()
      else root.toggle()
    }
  }
}
