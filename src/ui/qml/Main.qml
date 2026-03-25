import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    width: 900
    height: 600
    title: "Rclone Manager"
    visible: true
    
    // Property to hold remote to delete
    property string remoteToDelete: ""

    onClosing: (close) => {
        if (!mainViewModel.is_quitting) {
            close.accepted = false;
            mainViewModel.hide_window();
        }
    }

    Component.onCompleted: {
        mainViewModel.refresh_remotes()
    }

    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            ToolButton {
                text: "☰"
                onClicked: drawer.open()
            }
            Label {
                text: stackView.currentItem ? stackView.currentItem.title : "Rclone Manager"
                elide: Label.ElideRight
                horizontalAlignment: Qt.AlignHCenter
                verticalAlignment: Qt.AlignVCenter
                Layout.fillWidth: true
            }

        }
    }

    Drawer {
        id: drawer
        width: Math.min(root.width * 0.66, 300)
        height: root.height
        
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            
            Item { 
                Layout.fillWidth: true 
                Layout.preferredHeight: 150
                Rectangle { color: "lightgray"; anchors.fill: parent }
                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 5
                    Image {
                        source: "../assets/rclone_isologo.png"
                        sourceSize.width: 64
                        sourceSize.height: 64
                        fillMode: Image.PreserveAspectFit
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Label { 
                        text: "Rclone Manager"
                        font.pixelSize: 18
                        font.bold: true
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }
            
            Button {
                text: "Dashboard"
                Layout.fillWidth: true
                onClicked: {
                    stackView.replace(dashboardPage)
                    drawer.close()
                }
            }

            Button {
                text: "Activity Monitor"
                Layout.fillWidth: true
                onClicked: {
                    stackView.push(Qt.resolvedUrl("ActivityView.qml"))
                    drawer.close()
                }
            }

            Button {
                text: "Sync Tasks (Bisync)"
                Layout.fillWidth: true
                onClicked: {
                    stackView.push(Qt.resolvedUrl("SyncView.qml"))
                    drawer.close()
                }
            }

            Button {
                text: "Settings"
                Layout.fillWidth: true
                onClicked: {
                    stackView.push(Qt.resolvedUrl("SettingsView.qml"))
                    drawer.close()
                }
            }
            
            Item { Layout.fillHeight: true }
        }
    }

    StackView {
        id: stackView
        anchors.fill: parent
        initialItem: dashboardPage
    }
    
    // Confirmation Dialog
    MessageDialog {
        id: deleteConfirmDialog
        title: "Delete Connection?"
        text: "Are you sure you want to delete '" + root.remoteToDelete + "'?\nThis action cannot be undone."
        buttons: MessageDialog.Yes | MessageDialog.No
        onButtonClicked: function(button, role) {
            if (button === MessageDialog.Yes) {
                mainViewModel.delete_remote(root.remoteToDelete)
            }
        }
    }

    Component {
        id: dashboardPage
        Page {
            title: "Remotes Dashboard"
            
            // Add Button (Floating-like logic via Toolbar)
            footer: ToolBar {
                RowLayout {
                    anchors.fill: parent
                    Item { Layout.fillWidth: true }
                    Button {
                        text: "Add New Drive"
                        onClicked: stackView.push(Qt.resolvedUrl("Dialogs/NewDriveWizard.qml"))
                    }
                }
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 10
                anchors.margins: 20

                Label {
                    text: "Active Connections"
                    font.pixelSize: 20
                    Layout.alignment: Qt.AlignHCenter
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: mainViewModel.remotes_model 
                    delegate: Rectangle {
                        width: parent.width
                        height: 60  // Aumentar altura para dos líneas
                        color: "transparent"
                        
                        // Status Indicator
                        Rectangle {
                            width: 10
                            height: 10
                            radius: 5
                            color: modelData.status_color || "gray"
                            anchors.left: parent.left
                            anchors.leftMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                        }

                        ColumnLayout {
                            anchors.left: parent.left
                            anchors.leftMargin: 30
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            
                            Label {
                                text: modelData.display || modelData.name
                                color: "white"
                                font.pixelSize: 16
                                font.bold: true
                            }
                            // Row 2: Detail + Strategy Chip
                            RowLayout {
                                spacing: 8
                                
                                Label {
                                    text: modelData.detail || "Google Drive"
                                    color: "#AAA"
                                    font.pixelSize: 12
                                }
                                
                                // Strategy Chip
                                Rectangle {
                                    visible: modelData.sync_strategy !== undefined && modelData.sync_strategy !== ""
                                    color: "#333"
                                    radius: 4
                                    width: strategyLabelMain.width + 10
                                    height: 16
                                    Label {
                                        id: strategyLabelMain
                                        anchors.centerIn: parent
                                        text: (modelData.sync_strategy || "").toUpperCase()
                                        font.pixelSize: 8
                                        font.bold: true
                                        color: "#DDD"
                                    }
                                }
                            }
                            
                            // Row 3: Quota
                            RowLayout {
                                visible: modelData.quota !== undefined && modelData.quota !== ""
                                spacing: 5
                                
                                Rectangle {
                                    width: 100
                                    height: 4
                                    color: "#444"
                                    radius: 2
                                    
                                    Rectangle {
                                        width: parent.width * (modelData.storage_percent || 0.0)
                                        height: parent.height
                                        color: (modelData.storage_percent || 0) > 0.9 ? "#EF5350" : "#4CAF50"
                                        radius: 2
                                    }
                                }
                                
                                Label {
                                    text: "Storage: " + modelData.quota
                                    color: "#888"
                                    font.pixelSize: 11
                                }
                            }
                        }
                        
                        RowLayout {
                            anchors.right: parent.right
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.rightMargin: 10
                            spacing: 10

                            // LOADING SPINNER
                            BusyIndicator {
                                running: modelData.is_loading
                                visible: modelData.is_loading
                                Layout.alignment: Qt.AlignVCenter
                            }

                            // Button 1: Mount / Open
                            Button {
                                visible: !modelData.is_loading
                                text: modelData.is_mounted ? "Open" : "Mount"
                                onClicked: {
                                    if (modelData.is_mounted) {
                                        Qt.openUrlExternally("file://" + "/home/ciex/RcloneMounts/" + modelData.name)
                                    } else {
                                        // Default mount (RW)
                                        mainViewModel.mount_remote(modelData.name, false, false)
                                    }
                                }
                            }

                            // Settings Button (Mount Options) - Only if NOT mounted
                            Button {
                                visible: !modelData.is_mounted && !modelData.is_loading
                                text: "⚙️"
                                ToolTip.visible: hovered
                                ToolTip.text: "Advanced Mount Options"
                                onClicked: {
                                    mountOptionsDialog.remoteName = modelData.name
                                    mountOptionsDialog.open()
                                }
                            }
                            
                            // Button 2: Unmount (Only if mounted)
                            Button {
                                visible: modelData.is_mounted && !modelData.is_loading
                                text: "Unmount"
                                onClicked: mainViewModel.unmount_remote(modelData.name)
                            }
                            
                            Button {
                                visible: !modelData.is_loading
                                text: "🗑️" // Trash Icon
                                onClicked: {
                                    root.remoteToDelete = modelData.name
                                    deleteConfirmDialog.open()
                                }
                            }
                        }
                        
                        // Separator line
                        Rectangle {
                            width: parent.width
                            height: 1
                            color: "#333"
                            anchors.bottom: parent.bottom
                        }
                    }
                }
            }
        }
    }
    MountOptionsDialog {
        id: mountOptionsDialog
        anchors.centerIn: parent
    }
}
