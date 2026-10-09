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
  readonly property bool monochromeBarIcon: setting("monochromeBarIcon", false) === true

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

  readonly property var legionData: panelItem ? panelItem.currentData : null

  readonly property color badgeColor: {
    if (!root.legionData) return root.bar ? root.bar.barForeground : Color.foreground
    var mode = root.legionData.power && root.legionData.power.current_id ? root.legionData.power.current_id : ""
    if (mode === "performance") return "#e67e80"
    if (mode === "extreme" || mode === "custom") return "#b57bff"
    if (mode === "quiet") return "#4d9fff"
    if (mode === "balanced") return "#ffffff"
    return root.bar ? root.bar.barForeground : Color.foreground
  }

  readonly property string tipText: {
    if (!root.legionData) return "Legion Toolkit"
    var p = root.legionData.power || {}
    var t = root.legionData.thermals || {}
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

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    active: root.opened
    tooltipText: root.tipText
    iconComponent: Component {
      LegionIcon {
        iconSize: Style.bar.iconCanvas
        statusColor: root.badgeColor
        monochrome: root.monochromeBarIcon
        tintColor: root.bar ? root.bar.barForeground : Color.foreground
      }
    }

    onPressed: function(b) {
      if (!root.bar) return
      if (b === Qt.MiddleButton) root.refresh()
      else root.toggle()
    }
  }
}
