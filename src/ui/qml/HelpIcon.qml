import QtQuick
import QtQuick.Controls

Item {
    id: root
    width: 20
    height: 20
    property string text: ""

    // Círculo de fondo
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "#555"
        border.color: "#888"
        border.width: 1

        Label {
            text: "?"
            anchors.centerIn: parent
            color: "white"
            font.bold: true
            font.pixelSize: 12
        }
    }

    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        onClicked: toolTip.visible = !toolTip.visible // Toggle on click for touch screens
    }

    ToolTip {
        id: toolTip
        visible: ma.containsMouse
        delay: 500
        text: root.text
        contentItem: Text {
            text: toolTip.text
            color: "#FFFFFF"
            font.pixelSize: 12
        }
        background: Rectangle {
            color: "#333333"
            border.color: "#666666"
            radius: 4
        }
    }
}
