import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: root
    title: "Activity Monitor"
    
    // Injected: activityViewModel
    
    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            ToolButton {
                text: "Back"
                onClicked: StackView.view.pop()
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
        spacing: 0
        
        // Header Stats (Optional, maybe for total speed?)
        Rectangle {
            Layout.fillWidth: true
            height: 40
            color: "#252525"
            visible: false // TODO: Bind to global speed if available
            Label {
                text: "Total Speed: 0 B/s"
                anchors.centerIn: parent
                color: "#CCC"
            }
        }
        
        ListView {
            id: activityList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: activityViewModel.activity_model
            spacing: 1
            
            delegate: Rectangle {
                width: parent.width
                height: 60
                color: "transparent"
                
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 15
                    
                        Rectangle {
                        width: 40
                        height: 40
                        color: {
                             switch(modelData.type) {
                                 case "image-x-generic": return "#E1BEE7"; // Purple
                                 case "application-pdf": return "#FFCDD2"; // Red
                                 case "video-x-generic": return "#FFCCBC"; // Orange
                                 case "audio-x-generic": return "#C5CAE9"; // Blue
                                 default: return "#F5F5F5"; // Grey
                             }
                        }
                        radius: 20
                        
                        Label {
                            text: {
                                 switch(modelData.type) {
                                     case "image-x-generic": return "🖼️";
                                     case "application-pdf": return "📄";
                                     case "video-x-generic": return "🎬";
                                     case "audio-x-generic": return "🎵";
                                     case "package-x-generic": return "📦";
                                     default: return "📄";
                                 }
                            }
                            anchors.centerIn: parent
                            font.pixelSize: 20
                        }
                    }
                    
                    // Info & Progress
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: modelData.name
                                font.bold: true
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                                color: "white"
                            }
                            Label {
                                text: modelData.size
                                font.pixelSize: 11
                                color: "#AAA"
                            }
                        }
                        
                        RowLayout {
                            Layout.fillWidth: true
                            
                            // Progress Bar for syncing items
                            ProgressBar {
                                Layout.fillWidth: true
                                visible: modelData.status === "syncing"
                                value: modelData.progress / 100
                                height: 6
                            }
                            
                            Label {
                                text: modelData.status === "syncing" ? "Syncing... " + (modelData.speed || "") : modelData.timestamp
                                color: "#888"
                                font.pixelSize: 11
                                visible: modelData.status !== "syncing"
                            }
                        }
                    }
                    
                    // Status Icon
                    Item {
                        width: 30
                        height: 30
                        
                        Label {
                            anchors.centerIn: parent
                            font.pixelSize: 16
                            text: {
                                switch(modelData.status) {
                                    case "syncing": return ""; // Handled by progress
                                    case "success": return "✅";
                                    case "error": return "❌";
                                    case "deleted": return "🗑️";
                                    default: return "Unknown";
                                }
                            }
                        }
                        
                        BusyIndicator {
                            anchors.centerIn: parent
                            running: modelData.status === "syncing"
                            width: 24; height: 24
                        }
                    }
                }
                
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
