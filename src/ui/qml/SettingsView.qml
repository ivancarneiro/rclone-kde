import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    title: "Global Settings"

    Component.onCompleted: {
        settingsViewModel.load_remotes()
    }

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            ToolButton {
                text: "Back"
                onClicked: stackView.pop()
            }
            Label {
                text: root.title
                elide: Text.ElideRight
                horizontalAlignment: Qt.AlignHCenter
                verticalAlignment: Qt.AlignVCenter
                Layout.fillWidth: true
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 20
        spacing: 20

        Label {
            text: "General"
            font.bold: true
            font.pixelSize: 16
            color: "white"
        }

        CheckBox {
            text: "Run Application on System Startup"
            checked: settingsViewModel.run_on_startup
            onToggled: settingsViewModel.set_run_on_startup(checked)
        }

        CheckBox {
            text: "Start Minimized to Tray"
            checked: settingsViewModel.start_minimized
            onToggled: settingsViewModel.set_start_minimized(checked)
        }

        Rectangle { height: 1; width: parent.width; color: "#333" }

        Label {
            text: "Auto-Mount on Startup"
            font.bold: true
            font.pixelSize: 16
            color: "white"
        }
        
        Label {
            text: "Select which drives to mount automatically when the application starts."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
            color: "#AAA"
        }

        ListView {
            id: remotesList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: settingsViewModel.remotes_settings_model

            delegate: Item {
                width: parent.width
                height: 50
                
                RowLayout {
                    anchors.fill: parent
                    spacing: 10
                    
                    Label {
                        text: modelData.name
                        color: "white"
                        font.pixelSize: 14
                        Layout.fillWidth: true
                    }
                    
                    Switch {
                        checked: modelData.auto_mount
                        onToggled: {
                            settingsViewModel.toggle_auto_mount(modelData.name, checked)
                        }
                    }
                }
                
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: "#333"
                }
            }
        }
    }
}
